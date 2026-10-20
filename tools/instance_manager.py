"""Local ComfyUI instance CLI. Visible consoles; explicit, verified targets only.

Uses the project's existing Python/ComfyUI runtime and psutil (already installed).
Registry is local configuration, not a port-to-model mapping. Never force-kills.
"""
from __future__ import annotations
import argparse
import contextlib
import configparser
import ctypes
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import psutil

ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY = ROOT / 'instances'

def atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def valid_port(port):
    if isinstance(port, bool) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('TCP port must be an integer from 1 through 65535')
    return int(port)

def free_port(host='127.0.0.1', port=None):
    with socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET, socket.SOCK_STREAM) as s:
        if os.name == 'nt': s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind((host, valid_port(port) if port is not None else 0))
        return s.getsockname()[1]

def listeners(port):
    return [{'pid': c.pid, 'address': c.laddr.ip, 'port': c.laddr.port}
            for c in psutil.net_connections('tcp')
            if c.status == psutil.CONN_LISTEN and c.laddr.port == int(port)]

def fingerprint(pid):
    p = psutil.Process(int(pid))
    return {'pid': p.pid, 'created': p.create_time(), 'exe': p.exe(),
            'cwd': p.cwd(), 'argv': p.cmdline(), 'username': p.username()}

def same_process(expected):
    try: return fingerprint(expected['pid']) == expected
    except (psutil.Error, KeyError): return False

def request(url, path, body=None, timeout=10, identity=None):
    # No implicit redirects, proxy or default target (including a redirected POST).
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers={'Content-Type':'application/json'}
    if identity and identity.get('generation'):
        headers.update({'X-H3-Instance':identity['id'],'X-H3-Generation':identity['generation']})
    req = urllib.request.Request(url + path, data=data, headers=headers)
    with opener.open(req, timeout=timeout) as f: return json.load(f)

class Manager:
    def __init__(self, registry=DEFAULT_REGISTRY):
        self.root = Path(registry).resolve(); self.root.mkdir(parents=True, exist_ok=True)
        policy = self.root / 'policy.json'
        self.policy = read(policy) if policy.exists() else {'protected_instances': []}

    def path(self, name):
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
            raise ValueError('Invalid instance ID')
        return self.root / name / 'instance.json'

    @contextlib.contextmanager
    def lock(self, name):
        # One mutation per instance across independent agent/CLI processes.
        import msvcrt
        p=self.path(name).with_name('mutation.lock'); p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a+b') as f:
            f.seek(0)
            if not f.read(1): f.write(b'0'); f.flush()
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            try: yield
            finally: f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)

    def get(self, target):
        if str(target).isdigit():
            hits=[read(p) for p in self.root.glob('*/instance.json') if read(p)['port']==int(target)]
            if len(hits)!=1: raise ValueError('Port is unknown or ambiguous; select an instance ID')
            return hits[0]
        return read(self.path(target))

    def save(self, cfg): atomic(self.path(cfg['id']), cfg)

    def permitted(self, cfg):
        # Protection belongs to an instance/source identity, not to a port number.
        for p in self.policy.get('protected_instances',[]):
            if cfg['id']==p.get('id') or os.path.normcase(cfg['source'])==os.path.normcase(p.get('source','')):
                raise PermissionError('Protected production instance: '+cfg['id'])

    def create(self, name, source, python, port=None, host='127.0.0.1', data=None,
               extra=None, models=None, allow_lan=False, existing_dirs=False):
        with self.lock(name):
            if self.path(name).exists(): raise ValueError('Instance ID already registered')
            source=str(Path(source).resolve()); python=str(Path(python).resolve())
            if not (Path(source)/'main.py').is_file() or not Path(python).is_file():
                raise ValueError('Missing ComfyUI main.py or Python executable')
            ip=ipaddress.ip_address(host)
            if not ip.is_loopback and not allow_lan: raise ValueError('LAN listening requires --allow-lan')
            if port is not None and listeners(valid_port(port)):
                raise RuntimeError('Requested port occupied: '+json.dumps(listeners(port)))
            port=free_port(host, port)
            d=Path(data or self.path(name).parent/'data').resolve()
            dirs={k:str(d/k) for k in ('input','output','temp','user')}
            if existing_dirs: dirs={k:str(Path(source)/k) for k in dirs}
            for value in dirs.values(): Path(value).mkdir(parents=True,exist_ok=True)
            http_host=('::1' if ip.version==6 else '127.0.0.1') if ip.is_unspecified else host
            authority=f'[{http_host}]' if ip.version==6 else http_host
            cfg={'id':name,'host':host,'port':port,'url':f'http://{authority}:{port}',
                 'source':source,'python':python,'dirs':dirs,'extra':extra or [],
                 'models':str(Path(models).resolve()) if models else None,
                 'log':str(self.path(name).parent/'console.log'),'state':'STOPPED',
                 'managed':True,'generation':None,'listener':None,'host_process':None}
            self.permitted(cfg)
            adapter=Path(source)/'custom_nodes/h3_instance_identity/__init__.py'
            if not adapter.exists():
                candidates=[ROOT/'runtime/custom_nodes/h3_instance_identity/__init__.py',
                            ROOT.parent/'custom_nodes/local_author/h3_instance_identity/__init__.py']
                template=next((p for p in candidates if p.is_file()),None)
                if template is None:raise ValueError('Bundled read-only instance adapter not found')
                adapter.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(template,adapter)
            reserved={'--port','--listen','--input-directory','--output-directory','--temp-directory',
                      '--user-directory','--base-directory','--extra-model-paths-config'}
            if any(str(v).split('=')[0] in reserved for v in cfg['extra']):
                raise ValueError('Use instance fields for target/directory arguments')
            self.save(cfg); return cfg

    def verify(self, cfg):
        f=cfg.get('listener')
        if not f or not same_process(f): raise RuntimeError('Instance process identity changed or stopped')
        owned=listeners(cfg['port'])
        if not owned or any(c['pid']!=f['pid'] for c in owned):
            raise RuntimeError('Port ownership changed; refusing target operation')
        s=request(cfg['url'],'/system_stats')
        if not isinstance(s.get('system'),dict): raise RuntimeError('Not a ComfyUI endpoint')
        if cfg.get('generation'):
            ident=request(cfg['url'],'/h3/instance')
            if (ident.get('id'),ident.get('generation'),ident.get('pid')) != (cfg['id'],cfg['generation'],f['pid']):
                raise RuntimeError('HTTP instance identity mismatch')
        return s

    def status(self, target):
        c=self.get(target)
        try:
            self.verify(c); q=request(c['url'],'/queue')
            return dict(c,health='HEALTHY',queue_running=len(q['queue_running']),queue_pending=len(q['queue_pending']))
        except Exception as e: return dict(c,health='UNAVAILABLE_OR_IDENTITY_MISMATCH',error=str(e))

    def refresh(self, target):
        """Explicitly rebind a registered profile after an external compatible restart.

        No process signal, queue change or source write. A changed source, owner,
        argv, data root or HTTP identity is an error, never another target.
        """
        with self.lock(self.get(target)['id']):
            c=self.get(target); self.permitted(c)
            owners=listeners(c['port'])
            if len(owners)!=1 or owners[0]['address'] not in ('127.0.0.1','::1'):
                raise RuntimeError('Refresh requires one loopback listener')
            f=fingerprint(owners[0]['pid']); args=f['argv']
            if f['username']!=psutil.Process().username(): raise PermissionError('Different process owner')
            if os.path.normcase(f['cwd'])!=os.path.normcase(c['source']) or 'main.py' not in args or '--port' not in args:
                raise RuntimeError('Refresh source/argv mismatch')
            if args[args.index('--port')+1]!=str(c['port']): raise RuntimeError('Refresh port mismatch')
            stats=request(c['url'],'/system_stats')
            if stats['system']['argv'][1:]!=args[args.index('main.py')+1:]:
                raise RuntimeError('HTTP argv does not match listener')
            for k,v in c['dirs'].items():
                flag='--'+k+'-directory'
                actual=args[args.index(flag)+1] if flag in args else str(Path(c['source'])/k)
                if os.path.normcase(str(Path(actual).resolve()))!=os.path.normcase(str(Path(v).resolve())):
                    raise RuntimeError('Refresh data root mismatch: '+k)
            ident=request(c['url'],'/h3/instance')
            if ident.get('pid')!=f['pid'] or os.path.normcase(ident.get('source',''))!=os.path.normcase(c['source']):
                raise RuntimeError('Refresh HTTP identity mismatch')
            if ident.get('id') not in (None,c['id']): raise RuntimeError('Different instance ID')
            atomic(self.path(c['id']).parent/('rebind-'+str(time.time_ns())+'.json'),{'previous':c,'verified_listener':f})
            c.update(listener=f,generation=ident.get('generation'),state='RUNNING',managed=False,host_process=None)
            self.save(c); self.verify(c); return c

    def adopt(self, name, port, source, python):
        """Explicit adoption of the verified current-user legacy visible process."""
        with self.lock(name):
            if self.path(name).exists(): raise ValueError('ID already exists')
            port=valid_port(port); owners=listeners(port)
            if len(owners)!=1 or owners[0]['address'] not in ('127.0.0.1','::1'):
                raise RuntimeError('Legacy adoption requires one loopback listener')
            f=fingerprint(owners[0]['pid']); source=str(Path(source).resolve())
            if os.path.normcase(f['cwd'])!=os.path.normcase(source) or '--port' not in f['argv']:
                raise RuntimeError('Legacy source/argv identity mismatch')
            if f['argv'][f['argv'].index('--port')+1]!=str(port) or 'main.py' not in f['argv']:
                raise RuntimeError('Legacy ComfyUI argv mismatch')
            if f['username']!=psutil.Process().username(): raise PermissionError('Different process owner')
            stats=request(f'http://127.0.0.1:{port}','/system_stats')
            if stats['system']['argv'][1:]!=f['argv'][f['argv'].index('main.py')+1:]:
                raise RuntimeError('HTTP argv does not match listener process')
            args=f['argv'][f['argv'].index('main.py')+1:]; dirs={}; extra=[]
            i=0
            while i<len(args):
                k=args[i]
                if k in ('--listen','--port'): i+=2; continue
                if k in ('--input-directory','--output-directory','--temp-directory','--user-directory'):
                    dirs[k[2:].split('-')[0]]=args[i+1]; i+=2; continue
                extra.append(k); i+=1
            for k in ('input','output','temp','user'): dirs.setdefault(k,str(Path(source)/k))
            cfg={'id':name,'host':'127.0.0.1','port':port,'url':f'http://127.0.0.1:{port}',
                 'source':source,'python':str(Path(python).resolve()),'dirs':dirs,'extra':extra,
                 'models':str(Path(source)/'extra_model_paths.yaml') if (Path(source)/'extra_model_paths.yaml').exists() else None,
                 'log':str(self.path(name).parent/'console.log'),'state':'RUNNING','managed':False,
                 'generation':None,'listener':f,'host_process':None}
            self.permitted(cfg); self.save(cfg); return cfg

    def start(self, target, wait=120):
        with self.lock(self.get(target)['id']):
            c=self.get(target); self.permitted(c)
            if listeners(c['port']): raise RuntimeError('Port occupied: '+json.dumps(listeners(c['port'])))
            free_port(c['host'],c['port'])
            c.setdefault('env',{}).setdefault('H3_DIRECTOR_STATE_ROOT',str(Path(c['dirs']['user'])/'director_common'))
            c['env'].setdefault('H3_SIDECAR_DATA',str(Path(c['dirs']['user'])/'director_data'))
            c['env'].setdefault('H3_GEMMA_PORT',str(free_port()))
            # Reuse the existing Sidecar; isolate its config/logs and select its
            # own OS-assigned port, independently of the ComfyUI service port.
            template=Path(c['source'])/'custom_nodes/H3_Prompt_Sidecar/sidecar.ini'
            if template.exists() and not c.get('env',{}).get('H3_SIDECAR_CONFIG'):
                ini=self.path(c['id']).parent/'sidecar.ini'
                if not ini.exists():
                    cp=configparser.ConfigParser(interpolation=None);cp.read(template,encoding='utf-8-sig')
                    sideport=free_port()
                    cp['local_llamacpp']['port']=str(sideport)
                    cp['local_llamacpp']['base_url']=f'http://127.0.0.1:{sideport}'
                    cp['local_llamacpp']['log_path']=str(self.path(c['id']).parent/'sidecar.log')
                    with ini.open('w',encoding='utf-8') as f:cp.write(f)
                c.setdefault('env',{})['H3_SIDECAR_CONFIG']=str(ini)
            c.update(generation=uuid.uuid4().hex,state='STARTING',managed=True,listener=None,host_process=None)
            c['command']=[c['python'],'-u','main.py','--listen',c['host'],'--port',str(c['port']),
                          '--disable-auto-launch']
            for k,v in c['dirs'].items(): c['command'] += ['--'+k+'-directory',v]
            if c['models']: c['command']+=['--extra-model-paths-config',c['models']]
            c['command']+=c['extra']; self.save(c)
            p=subprocess.Popen([c['python'],'-u',str(Path(__file__).resolve()),'--registry',str(self.root),'_host',c['id']],
                               cwd=c['source'],creationflags=subprocess.CREATE_NEW_CONSOLE)
            deadline=time.monotonic()+min(wait,120)
            while time.monotonic()<deadline:
                if p.poll() is not None: raise RuntimeError('Visible supervisor exited '+str(p.returncode))
                try:
                    c=self.get(target); self.verify(c)
                except Exception:
                    time.sleep(.3); continue
                if c.get('preflight'):
                    result=subprocess.run(c['preflight']+['--endpoint',c['url']],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
                    atomic(self.path(c['id']).parent/'preflight.json',{'code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                    if result.returncode:raise RuntimeError('Instance route preflight failed: '+result.stdout+result.stderr)
                return c
            raise TimeoutError('Readiness timeout; visible console retained: '+c['log'])

    def stop(self, target, timeout=45):
        with self.lock(self.get(target)['id']):
            c=self.get(target); self.permitted(c); self.verify(c)
            q=request(c['url'],'/queue')
            if q['queue_running'] or q['queue_pending']: raise RuntimeError('Active or queued tasks; stop refused')
            snapshot={'instance':c,'history':request(c['url'],'/history'),'queue':q,'at':time.time()}
            atomic(self.path(c['id']).parent/('snapshot-'+str(time.time_ns())+'.json'),snapshot)
            # Recheck identity and queue immediately before any process signal.
            self.verify(c); q=request(c['url'],'/queue')
            if q['queue_running'] or q['queue_pending']: raise RuntimeError('Queue changed; stop refused')
            if c['managed']:
                if not same_process(c['host_process']): raise RuntimeError('Supervisor identity changed')
                atomic(self.path(c['id']).parent/'stop.json',{'generation':c['generation'],'listener':c['listener']})
            else:
                # Normal console Ctrl+C only, in a dedicated short-lived helper.
                subprocess.run([c['python'],str(Path(__file__).resolve()),'_signal',str(c['listener']['pid'])],check=True,timeout=10)
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                supervisor_done=not c['managed'] or not same_process(c['host_process'])
                if supervisor_done and not same_process(c['listener']) and not listeners(c['port']):
                    current=self.get(target); current['state']='STOPPED'; self.save(current); return current
                time.sleep(.25)
            raise TimeoutError('Graceful exit unconfirmed; no force kill performed')

    def restart(self,target):
        self.stop(target); return self.start(target)

    def submit(self,target,body,route='/prompt'):
        c=self.get(target)
        with self.lock(c['id']):
            self.permitted(c); self.verify(c)
            if route not in ('/prompt','/h3/prebake/submit'): raise ValueError('Unsupported submission route')
            if route=='/prompt':
                graph=body.get('prompt',{})
                if any(n.get('class_type') in ('H3AttemptGuard','H3ConditioningLoad') for n in graph.values()):
                    raise ValueError('Controlled H3 graph requires /h3/prebake/submit')
                body.setdefault('extra_data',{}).setdefault('extra_pnginfo',{}).setdefault('workflow',{})
                body.setdefault('client_id',c['id']+'-'+str(c['generation'] or c['listener']['created']))
            rid=uuid.uuid4().hex; rp=self.path(c['id']).parent/'receipts'/f'{rid}.json'
            receipt={'instance_id':c['id'],'generation':c['generation'],'url':c['url'],'listener':c['listener'],
                     'route':route,'request':body,'state':'DISPATCHING','at':time.time()}
            atomic(rp,receipt) # ambiguous transport errors must not be auto-retried
            try:
                reply=request(c['url'],route,body,timeout=60,identity=c)
                receipt.update(state='SUBMITTED',response=reply,prompt_id=reply.get('prompt_id'))
                atomic(rp,receipt); return receipt
            except Exception as e:
                receipt.update(state='UNCONFIRMED_DO_NOT_RETRY',error=str(e)); atomic(rp,receipt); raise

    def history(self,target,prompt_id):
        c=self.get(target)
        matches=[read(p) for p in (self.path(c['id']).parent/'receipts').glob('*.json')
                 if read(p).get('prompt_id')==prompt_id]
        if len(matches)!=1: raise RuntimeError('Prompt receipt missing or ambiguous for this instance')
        if matches[0]['generation']!=c['generation']:
            for p in sorted(self.path(c['id']).parent.glob('snapshot-*.json'),reverse=True):
                snap=read(p)
                if snap['instance']['generation']==matches[0]['generation'] and prompt_id in snap['history']:
                    return {'source':'saved_history_snapshot','instance_id':c['id'],
                            'generation':matches[0]['generation'],'history':{prompt_id:snap['history'][prompt_id]}}
            raise RuntimeError('Prompt belongs to a different generation without a saved snapshot; never reroute')
        self.verify(c)
        result=request(c['url'],'/history/'+prompt_id)
        atomic(self.path(c['id']).parent/'receipts'/('history-'+prompt_id+'.json'),
               {'instance_id':c['id'],'generation':c['generation'],'history':result})
        return result

    def discover(self):
        """Read OS metadata only; never contact, stop or silently adopt a server."""
        out=[]
        for p in psutil.process_iter(['pid','cmdline','cwd','create_time','exe']):
            try:
                args=p.info['cmdline'] or []
                if 'main.py' not in args or '--port' not in args: continue
                port=valid_port(args[args.index('--port')+1]); owners=listeners(port)
                if not any(x['pid']==p.pid for x in owners): continue
                out.append(dict(p.info,port=port,listeners=owners))
            except (psutil.Error,ValueError,IndexError): continue
        return out

def host(manager,name):
    c=manager.get(name); ctypes.windll.kernel32.SetConsoleTitleW('ComfyUI '+c['id']+' - '+c['url'])
    env=dict(os.environ,PYTHONUNBUFFERED='1',H3_INSTANCE_ID=c['id'],H3_INSTANCE_GENERATION=c['generation'],
             H3_COMFY_ROOT=c['source'],H3_V28_PROJECTS=str(Path(c['dirs']['user'])/'director_projects'))
    env.update(c.get('env',{}))
    # Real child output is both visible immediately and append-only logged.
    log=Path(c['log']); log.parent.mkdir(parents=True,exist_ok=True)
    with log.open('a',encoding='utf-8',buffering=1) as f:
        header=f'\nINSTANCE {name} {c["url"]} generation={c["generation"]}\n'
        print(header,flush=True); f.write(header)
        p=subprocess.Popen(c['command'],cwd=c['source'],env=env,stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1)
        # Install our handler after spawn so the child keeps Python's normal Ctrl+C.
        signal.signal(signal.SIGINT,lambda *_:None)
        # Ctrl+Break escalation is a console signal to this group; the host must
        # survive it (the child has no SIGBREAK handler and terminates).
        signal.signal(signal.SIGBREAK,lambda *_:None)
        def tee():
            for line in p.stdout: print(line,end='',flush=True); f.write(line)
        t=threading.Thread(target=tee,daemon=True); t.start()
        sent=False
        while p.poll() is None:
            owners=listeners(c['port'])
            owned=[x for x in owners if x['pid'] and (x['pid']==p.pid or psutil.Process(x['pid']).ppid()==p.pid)]
            if owned and not c.get('listener'):
                c.update(listener=fingerprint(owned[0]['pid']),host_process=fingerprint(os.getpid()),state='RUNNING')
                manager.save(c)
            stop=manager.path(name).parent/'stop.json'
            if stop.exists() and not sent:
                cmd=read(stop)
                if cmd.get('generation')==c['generation'] and cmd.get('listener')==c['listener']:
                    manager.verify(c); q=request(c['url'],'/queue')
                    if not q['queue_running'] and not q['queue_pending']:
                        print('Normal Ctrl+C requested',flush=True)
                        ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0,0); sent=True
                        # On this host Ctrl+C is not delivered to the pipe-stdio
                        # child; escalate to console Ctrl+Break after a grace
                        # window. Still a console signal - no kill, no force.
                        deadline=time.monotonic()+15
                        while p.poll() is None and time.monotonic()<deadline: time.sleep(.25)
                        if p.poll() is None:
                            print('Ctrl+C undelivered to child; escalating to console Ctrl+Break',flush=True)
                            subprocess.run([c['python'],str(Path(__file__).resolve()),'_break',str(p.pid)],timeout=20)
                            deadline=time.monotonic()+15
                            while p.poll() is None and time.monotonic()<deadline: time.sleep(.25)
            time.sleep(.25)
        t.join(timeout=5); c.update(state='STOPPED',exit_code=p.returncode); manager.save(c)
        print('Service exited',p.returncode,'; console retained on startup/error failure',flush=True)
        if not sent:
            try: input('Press Enter to close this console. ')
            except EOFError: pass

def console_signal(pid):
    """Graceful-first console signal to a visible legacy (unmanaged) process.

    Ctrl+C first; if the target survives, escalate to Ctrl+Break. On this host
    Windows does not deliver console Ctrl+C to pipe-stdio children (verified
    experimentally 2026-10-18), so escalation is the norm, not the exception.
    Ctrl+Break cannot be suppressed by SetConsoleCtrlHandler(None, True); this
    short-lived helper therefore ignores SIGBREAK itself. Always console
    signals - never a process kill.
    """
    k=ctypes.WinDLL('kernel32',use_last_error=True); k.FreeConsole()
    if not k.AttachConsole(int(pid)): raise ctypes.WinError(ctypes.get_last_error())
    k.SetConsoleCtrlHandler(None,True)
    signal.signal(signal.SIGBREAK,lambda *_:None)
    if not k.GenerateConsoleCtrlEvent(0,0): raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(3)
    try:
        if psutil.pid_exists(int(pid)):
            k.GenerateConsoleCtrlEvent(1,0); time.sleep(.5)
    except psutil.Error: pass
    k.FreeConsole()

def console_break(pid):
    """Console Ctrl+Break to a child, from a short-lived helper process.

    On this host Windows does NOT deliver console Ctrl+C to pipe-stdio children
    (verified experimentally 2026-10-18: CTRL_C_EVENT group 0 and the
    AttachConsole+CTRL_C path both left the child alive, while CTRL_BREAK_EVENT
    terminated it). Ctrl+Break cannot be suppressed with SetConsoleCtrlHandler
    (None, True), so the helper ignores SIGBREAK itself and keeps running long
    enough to return normally. Still a console signal; never a process kill.
    """
    k=ctypes.WinDLL('kernel32',use_last_error=True); k.FreeConsole()
    if not k.AttachConsole(int(pid)): raise ctypes.WinError(ctypes.get_last_error())
    k.SetConsoleCtrlHandler(None,True)
    signal.signal(signal.SIGBREAK,lambda *_:None)
    if not k.GenerateConsoleCtrlEvent(1,0): raise ctypes.WinError(ctypes.get_last_error())
    time.sleep(.5); k.FreeConsole()

def main():
    p=argparse.ArgumentParser(); p.add_argument('--registry',default=str(DEFAULT_REGISTRY))
    p.add_argument('action',choices=['create','adopt','refresh','start','stop','restart','status','list','health','submit','_host','_signal','_break'])
    p.add_argument('target',nargs='?'); p.add_argument('--port',type=int); p.add_argument('--source');p.add_argument('--python')
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--data');p.add_argument('--models');p.add_argument('--allow-lan',action='store_true')
    p.add_argument('--extra-json',default='[]');p.add_argument('--body');p.add_argument('--route',default='/prompt');p.add_argument('--prompt-id')
    a=p.parse_args(); m=Manager(a.registry)
    if a.action=='_signal': console_signal(int(a.target)); return
    if a.action=='_break': console_break(int(a.target)); return
    if a.action=='_host': host(m,a.target); return
    if a.action=='create': r=m.create(a.target,a.source,a.python,a.port,a.host,a.data,json.loads(a.extra_json),a.models,a.allow_lan)
    elif a.action=='adopt': r=m.adopt(a.target,a.port,a.source,a.python)
    elif a.action=='list': r={'registered':[m.status(read(f)['id']) for f in m.root.glob('*/instance.json')], 'discovered':m.discover()}
    elif a.action in ('health','status'): r=m.history(a.target,a.prompt_id) if a.prompt_id else m.status(a.target)
    elif a.action=='submit': r=m.submit(a.target,read(a.body),a.route)
    else: r=getattr(m,a.action)(a.target)
    print(json.dumps(r,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(json.dumps({'ok':False,'error':type(e).__name__,'detail':str(e)},ensure_ascii=False),flush=True);sys.exit(1)
