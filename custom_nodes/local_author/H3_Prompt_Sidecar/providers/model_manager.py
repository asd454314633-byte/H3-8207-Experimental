"""Sole owner of the single-model 8095 runtime. GETs never mutate processes."""
import hashlib
import json
import os
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import psutil
from .base import ProviderError


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def normalized(path):
    return os.path.normcase(os.path.abspath(path))


class H3DirectorModelManager:
    ACTORS = {'planner_generate', 'manual_warmup', 'launcher_cold_start', 'recovery'}

    def __init__(self, registry):
        self.registry = registry
        self.root = registry.path.parent
        self.lock = threading.RLock()
        self.local = threading.local()
        self.state = 'STOPPED'
        self.active_planners = 0
        self.spawn_count = self.kill_count = 0
        self.last_error = None

    def _target(self, key):
        if self.registry.catalog().get(key, {}).get('provider') != 'local_llamacpp':
            raise ProviderError('LOCAL_MODEL_REQUIRED')
        return self.registry._provider(key)

    @contextmanager
    def _transaction(self, blocking=True):
        if not self.lock.acquire(blocking=blocking):
            raise ProviderError('DIRECTOR_MODEL_BUSY: active Planner protected')
        nested = getattr(self.local, 'depth', 0)
        handle = None
        try:
            if not nested:
                import msvcrt
                handle = (self.root / 'director_model.lock').open('a+b')
                handle.seek(0)
                if not handle.read(1):
                    handle.write(b'0'); handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    handle.close(); handle = None
                    raise ProviderError('DIRECTOR_MODEL_BUSY: another owner is active') from exc
            self.local.depth = nested + 1
            yield
        finally:
            self.local.depth = nested
            if handle:
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()
            self.lock.release()

    @staticmethod
    def _args(command):
        def value(*flags):
            for flag in flags:
                if flag in command:
                    index = command.index(flag) + 1
                    return command[index] if index < len(command) else None
            return None
        return value('--port'), value('--model', '-m'), value('--alias')

    def _fingerprint(self, process):
        try:
            command = process.cmdline()
            port, model, alias = self._args(command)
            catalog = self.registry.catalog()
            key = next((k for k, c in catalog.items() if c['provider'] == 'local_llamacpp'
                        and model and normalized(c['model']) == normalized(model)
                        and alias == c['alias'] and port == str(c['port'])
                        and normalized(process.exe()) == normalized(Path(c['runtime'])/'llama-server.exe')), None)
            if key is None:
                return None
            return {'pid':process.pid, 'create_time':process.create_time(), 'parent_pid':process.ppid(),
                    'executable':process.exe(), 'command_line':command, 'model_path':model,
                    'alias':alias, 'model_key':key,
                    'command_line_hash':hashlib.sha256(json.dumps(command).encode()).hexdigest()}
        except (psutil.Error, OSError):
            return None

    def _port(self):
        ports={int(c['port']) for c in self.registry.catalog().values() if c['provider']=='local_llamacpp'}
        if len(ports)!=1: raise ProviderError('SINGLE_LOCAL_MODEL_TARGET_REQUIRED')
        return next(iter(ports))

    def _inspect(self):
        listeners = {c.pid for c in psutil.net_connections(kind='tcp')
                     if c.status == psutil.CONN_LISTEN and c.laddr.port == self._port()}
        if len(listeners) > 1:
            raise ProviderError('LOCAL_MODEL_PORT_OCCUPIED_BY_UNKNOWN_PROCESS')
        pid = next(iter(listeners), None)
        owned = []
        for process in psutil.process_iter(['name']):
            if (process.info['name'] or '').lower() == 'llama-server.exe':
                fingerprint = self._fingerprint(process)
                if fingerprint:
                    owned.append(fingerprint)
        if len(owned) > 1 or (pid and pid not in {p['pid'] for p in owned}):
            raise ProviderError('LOCAL_MODEL_PORT_OCCUPIED_BY_UNKNOWN_PROCESS')
        return pid, owned[0] if owned else None

    def get_status(self):
        # No locks that wait for a generation, no preferences writes, no ADOPT mutation.
        try:
            pid, process = self._inspect()
            key = process['model_key'] if process else None
            healthy = busy = False
            model_id = None
            match = False
            if pid and process:
                target = self._target(key)
                healthy = target.health()
                if healthy:
                    props = target._http('/props')
                    ids = target._http('/v1/models').get('data', [])
                    model_id = ids[0].get('id') if ids else None
                    match = (normalized(props.get('model_path', '')) == normalized(process['model_path'])
                             and model_id == process['alias'])
                    busy = any(s.get('is_processing') for s in target._http('/slots'))
                    # Recheck create_time and listener after HTTP to reject mixed snapshots.
                    pid2, process2 = self._inspect()
                    match = match and pid2 == pid and process2 == process
            state = ('BUSY' if busy or self.active_planners else 'READY') if match else ('STARTING' if process else 'STOPPED')
            if self.state in ('STARTING', 'STOPPING', 'FAILED') and not match:
                state = self.state
            return {'state':state, 'selected_model':self.registry.selected, 'running_model':key if match else None,
                    'actual_model_key':key if match else None, 'model_id':model_id, 'pid':pid,
                    'create_time':process['create_time'] if process else None,
                    'fingerprint':process, 'healthy':healthy, 'process_identity_match':bool(process),
                    'model_match':bool(match), 'busy':busy or bool(self.active_planners),
                    'address':f'http://127.0.0.1:{self._port()}', 'last_error':self.last_error}
        except ProviderError as exc:
            return {'state':'FAILED', 'error':str(exc), 'running_model':None,
                    'selected_model':self.registry.selected, 'healthy':False, 'model_match':False, 'pid':None}

    def _event(self, switch_id, actor, reason, before, key, result, after=None):
        after = after or {}
        config = self.registry.catalog()[key]
        fingerprint = after.get('fingerprint') or before.get('fingerprint') or {}
        value = {'timestamp':datetime.now(timezone.utc).isoformat(), 'switch_id':switch_id,
                 'actor':actor, 'reason':reason, 'selected_model':self.registry.selected,
                 'from_model':before.get('running_model'), 'to_model':key,
                 'old_pid':before.get('pid'), 'new_pid':after.get('pid'),
                 'parent_pid':fingerprint.get('parent_pid'), 'command_line_hash':fingerprint.get('command_line_hash'),
                 'model_path':config['model'], 'alias':config['alias'],
                 'health_result':after.get('healthy', False), 'result':result}
        with (self.root/'director_model_events.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(value, ensure_ascii=False)+'\n');handle.flush();os.fsync(handle.fileno())

    def _stop(self, fingerprint):
        # Verify PID reuse and every identity field immediately before touching process.
        process = psutil.Process(fingerprint['pid'])
        if self._fingerprint(process) != fingerprint:
            raise ProviderError('PROCESS_FINGERPRINT_CHANGED: process kept')
        pid, current = self._inspect()
        if current != fingerprint or (pid and pid != process.pid):
            raise ProviderError('PROCESS_FINGERPRINT_CHANGED: process kept')
        target = self._target(fingerprint['model_key'])
        if target.health() and any(s.get('is_processing') for s in target._http('/slots')):
            raise ProviderError('DIRECTOR_MODEL_BUSY: process kept')
        # llama-server handles CTRL_BREAK in its own process group; adopted legacy
        # processes may not have a group. Never image-wide kill or kill children.
        try:
            os.kill(process.pid, __import__('signal').CTRL_BREAK_EVENT)
            process.wait(timeout=10)
        except (OSError, psutil.TimeoutExpired):
            if process.is_running():
                if self._fingerprint(process) != fingerprint:
                    raise ProviderError('PROCESS_FINGERPRINT_CHANGED')
                process.terminate();process.wait(timeout=15)
        self.kill_count += 1
        deadline = time.monotonic()+15
        while time.monotonic() < deadline:
            pid, owned = self._inspect()
            if not pid and not owned:
                return
            time.sleep(.2)
        raise ProviderError('MODEL_PORT_RELEASE_TIMEOUT')

    def _launch(self, key):
        target = self._target(key)
        command = target.launch_command()
        for item in [command[0], target.config['model']]:
            if not Path(item).is_file():
                raise ProviderError('MODEL_FILE_MISSING: '+str(item))
        pid, process = self._inspect()
        if pid or process:
            raise ProviderError('MODEL_START_CONFLICT: existing process kept')
        env = {k:v for k,v in os.environ.items() if not k.startswith('LLAMA_ARG_')
               and k not in {'CUDA_VISIBLE_DEVICES', 'GGML_CUDA_DISABLE'}}
        env['PATH'] = target.config['runtime'] + os.pathsep + env.get('PATH', '')
        # Runtime log is additional to Director console; only this owner can launch.
        with Path(target.config['log_path']).open('a', encoding='utf-8', buffering=1) as log:
            child = subprocess.Popen(command, cwd=target.config['runtime'], env=env,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.spawn_count += 1
        deadline = time.monotonic()+120
        while time.monotonic() < deadline and child.poll() is None:
            status = self.get_status()
            if status.get('running_model') == key and status.get('pid') == child.pid:
                return status
            time.sleep(.5)
        # Only clean up a child proven to be ours.
        if child.poll() is None:
            fingerprint = self._fingerprint(psutil.Process(child.pid))
            if fingerprint:
                self._stop(fingerprint)
        raise ProviderError('MODEL_LOAD_FAILED: '+key)

    def _ensure_locked(self, key, reason):
        if reason not in self.ACTORS:
            raise ProviderError('MODEL_SWITCH_ACTOR_REJECTED')
        target = self._target(key)
        before = self.get_status()
        if before.get('error'):
            raise ProviderError(before['error'])
        if before.get('busy') and not self.active_planners:
            raise ProviderError('DIRECTOR_MODEL_BUSY: external inference protected')
        if before.get('running_model') == key:
            self.state = 'READY'
            return dict(before, result='ALREADY_READY', message='当前模型已就绪；未重启')
        if before.get('state') == 'STARTING':
            # Adopt a known loading process; never spawn a second one.
            deadline = time.monotonic()+120
            while time.monotonic() < deadline:
                before = self.get_status()
                if before.get('running_model'):
                    return self._ensure_locked(key, reason)
                time.sleep(.5)
            raise ProviderError('MODEL_READY_TIMEOUT: existing process kept')
        switch_id = uuid.uuid4().hex
        self._event(switch_id, reason, reason, before, key, 'BEGIN')
        previous = before.get('running_model')
        try:
            if before.get('fingerprint'):
                # No API identity => never stop even a cmdline-matching process.
                if not previous:
                    raise ProviderError('MODEL_IDENTITY_UNVERIFIED: process kept')
                self.state = 'STOPPING';self._stop(before['fingerprint'])
            self.state = 'STARTING'
            after = self._launch(key)
            self.state = 'READY';self.last_error = None
            self._event(switch_id, reason, reason, before, key, 'READY', after)
            return dict(after, result='READY', message='所选模型已就绪')
        except Exception as exc:
            self.state = 'FAILED';self.last_error = str(exc)
            self._event(switch_id, reason, reason, before, key, 'FAILED: '+str(exc))
            pid, owned = self._inspect()
            if owned and owned['model_key'] == key and owned != before.get('fingerprint'):
                self._stop(owned)
            # Restore precisely the previous verified model once, no alternatives.
            if previous and previous != key and not self._inspect()[1]:
                try:
                    self.state = 'STARTING';after = self._launch(previous);self.state = 'READY'
                    self._event(switch_id, 'recovery', 'restore_previous_once', before, previous, 'RESTORED', after)
                except Exception as recovery_error:
                    self.state = 'FAILED'
                    self._event(switch_id, 'recovery', 'restore_previous_once', before, previous, 'FAILED: '+str(recovery_error))
            raise

    def ensure_model(self, model_key, reason):
        with self._transaction():
            return self._ensure_locked(model_key, reason)

    def warm_model(self, model_key):
        with self._transaction(blocking=False):
            return self._ensure_locked(model_key, 'manual_warmup')

    @contextmanager
    def planner_session(self, model_key):
        # Reserve the runtime across all seven calls and gaps in a six-segment job.
        with self._transaction():
            self._ensure_locked(model_key, 'planner_generate')
            self.active_planners += 1
            self.local.planner_model = model_key
            try:
                yield
            finally:
                self.active_planners -= 1
                self.local.planner_model = None

    def generate_with_model(self, model_key, request):
        with self._transaction():
            reserved = getattr(self.local, 'planner_model', None)
            if reserved and reserved != model_key:
                raise ProviderError('SELECTED_MODEL_MISMATCH: Planner reservation protected')
            self._ensure_locked(model_key, 'planner_generate')
            self.state = 'BUSY'
            try:
                return self._target(model_key).generate(request)
            finally:
                self.state = 'READY'
