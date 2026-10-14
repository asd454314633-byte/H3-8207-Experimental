"""Six-controller transport/state only; official nodes perform all video operations."""
import asyncio
import copy
import json
import hashlib
import logging
import os
import threading
import time
import uuid
from pathlib import Path


class NativeMergeControl:
    def __init__(self, root, template, history, submit, validate, inspect, queue=None, state_lock=None):
        self.root, self.template = Path(root), Path(template)
        self.history, self.submit, self.validate, self.inspect = history, submit, validate, inspect
        self.queue = queue
        self.state_lock = state_lock or threading.RLock()
        self.locks, self.tasks = {}, set()
        self.notify = lambda project: None
        self.reconcile = lambda project,index: None
        self.submit_reserved = None
        self.queue_dedup_enabled = False
        self.merge_jobs = {}

    def path(self, project):
        if not project or len(project) > 64 or any(not (c.isalnum() or c in '-_') for c in project):
            raise ValueError('Invalid project')
        return self.root / 'h3_continuation' / project / 'six_acceptance.json'

    def read(self, project):
        p = self.path(project)
        with self.state_lock:return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}

    def update(self, project, change):
        with self.state_lock:
            data = self.read(project)
            state = data.setdefault('_native_merge', {'auto_merge_enabled': True, 'active_group_id': None, 'groups': {}})
            change(state)
            p = self.path(project)
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_name(p.name + '.native.tmp-' + uuid.uuid4().hex)
            try:
                with tmp.open('wb') as handle:
                    handle.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
                    handle.flush()
                    os.fsync(handle.fileno())
                for retry in range(6):
                    try:
                        os.replace(tmp, p)
                        break
                    except PermissionError:
                        if retry == 5:
                            raise
                        time.sleep(.01 * (retry + 1))
            finally:
                if tmp.exists(): tmp.unlink()
        self.notify(project)
        return state

    def state(self, project):
        state = self.read(project).get('_native_merge', {'auto_merge_enabled': True, 'active_group_id': None, 'groups': {}})
        group = state['groups'].get(state['active_group_id'], {})
        return {'auto_merge_enabled': state['auto_merge_enabled'], 'group_id': state['active_group_id'],
                'merge_status': group.get('merge_status', 'NOT_STARTED' if state['auto_merge_enabled'] else 'DISABLED'),
                'merge_prompt_id': group.get('merge_prompt_id'), 'merge_output': group.get('merge_output')}

    def settings(self, project, enabled):
        if not isinstance(enabled, bool): raise ValueError('auto_merge_enabled must be boolean')
        def change(s):
            s['auto_merge_enabled'] = enabled
            g = s['groups'].get(s['active_group_id'])
            if not enabled and g and g['merge_status'] in ('WAITING_6_OF_6', 'NOT_STARTED'):
                g['eligible'] = False
                g['merge_status'] = 'DISABLED'
            # ON never submits or re-arms an existing disabled group.
        self.update(project, change)
        return self.state(project)

    def begin(self, project, group_id=None):
        group_id = group_id or str(uuid.uuid4())
        if len(group_id) > 160 or any(not (c.isalnum() or c in '-_') for c in group_id):
            raise ValueError('Invalid group identity')
        def change(s):
            s['active_group_id'] = group_id
            if group_id not in s['groups']:
                enabled = s['auto_merge_enabled']
                s['groups'][group_id] = {'eligible': enabled, 'started_at': time.time(), 'prompt_ids': {},
                    'merge_prompt_id': None, 'merge_output': None,
                    'merge_status': 'WAITING_6_OF_6' if enabled else 'DISABLED'}
        self.update(project, change)
        return self.state(project)

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def selected(self, project, group_id):
        root=self.root/'h3_continuation'
        pointers=root/'_prebake_current.json'
        versions=root/'_prebake_executions.json'
        if not pointers.exists() or not versions.exists():return True
        known=json.loads(versions.read_text(encoding='utf-8'))
        candidates=[b for b in known.values() if b['project_id']==project and b['group_id']==group_id]
        if not candidates:return True
        current=json.loads(pointers.read_text(encoding='utf-8'))
        return len(candidates)==1 and current.get(candidates[0]['story_id'])==candidates[0]['execution_version']

    async def complete(self, project, group_id):
        lock = self.locks.setdefault((project, group_id), asyncio.Lock())
        async with lock:
            if not self.selected(project,group_id):return
            s = self.read(project)['_native_merge']; g = s['groups'][group_id]
            if g['merge_status']=='SUBMITTED':
                pid=g.get('merge_prompt_id');h=self.history(pid) if pid else None
                if h:
                    files=h.get('outputs',{}).get('8',{}).get('images',[])
                    if h['status'].get('status_str')=='success' and h['status'].get('completed') is True and len(files)==1 and files[0].get('type')=='output':
                        self.merge_transition(project,group_id,pid,merge_status='SUCCESS',merge_output=files[0])
                    else:self.update(project,lambda st:st['groups'][group_id].update(merge_status='ERROR',merge_error='Exact merge history failed'))
                elif self.queue_dedup_enabled and self.queue is not None and pid and not any(item[1]==pid for item in self.queue()):
                    if g.get('enqueue_phase','INTENT') in ('INTENT','ENQUEUED'):
                        try:await self.resume_unstarted(project,group_id,g)
                        except Exception as ex:self.update(project,lambda st:st['groups'][group_id].update(merge_status='ERROR',merge_error=str(ex)))
                    elif g.get('enqueue_phase')=='STARTED':
                        self.update(project,lambda st:st['groups'][group_id].update(merge_status='ERROR',merge_error='Started merge lost on server restart; no automatic GPU retry'))
                return # Reuse an unstarted durable job ID; never replay a started job.
            if not s['auto_merge_enabled'] or not g['eligible'] or g['merge_status'] != 'WAITING_6_OF_6': return
            ids = g['prompt_ids']
            if s.get('active_group_id')!=group_id:return
            if set(ids) != {'0','1','2','3','4','5'} or len(set(ids.values())) != 6: return
            try:
                # Acceptance is independently durable. A delayed notification is WAITING,
                # never a terminal merge error. Reconciliation uses exact history only.
                for i in range(6):self.reconcile(project,i)
                receipts=self.read(project)
                for i in range(6):
                    r=receipts.get(str(i),{})
                    if r.get('status')!='SUCCESS' or r.get('prompt_id')!=ids[str(i)] or r.get('group_id') not in (None,group_id):return
                template = json.loads(self.template.read_text(encoding='utf-8-sig'))
                graph = template['output']
                assert len(graph) == 8 and [graph[str(i)]['class_type'] for i in range(1,9)] == ['LoadVideo']*6 + ['ConcatenateVideo','SaveVideo']
                sources=[]
                for i in range(6):
                    self.inspect(project, i)
                    receipt=receipts[str(i)]
                    h = self.history(ids[str(i)])
                    if h:
                        if h['status']['status_str'] != 'success' or h['status']['completed'] is not True: return
                        native = [n for n in h['prompt'][2].values() if n['class_type']=='H3ContinuationSave' and n['inputs'].get('enabled') is True]
                        source_project=receipt.get('project_id',project)
                        assert len(native)==1 and native[0]['inputs']['project_id']==source_project and native[0]['inputs']['segment_index']==i
                        assert h['prompt'][2]['961']['class_type']=='SaveVideo'
                        output = h['outputs']['961']
                        videos = [v for k in ('images','videos') for v in output.get(k,[]) if Path(v['filename']).suffix.lower() in ('.mp4','.webm','.mov','.mkv')]
                    else:
                        # Only a previously fully accepted, fingerprinted output survives volatile history loss.
                        ref=receipt.get('video_output_ref')
                        if not ref or ref.get('prompt_id')!=ids[str(i)] or not receipt.get('video_sha256'):return
                        videos=[ref]
                    assert len(videos)==1 and videos[0]['type']=='output'
                    v=videos[0]; assert isinstance(v['subfolder'],str) and '/' not in v['filename'] and '\\' not in v['filename']
                    relative=(Path(v['subfolder'])/v['filename']).as_posix()
                    source=(self.root/relative).resolve(); assert source.is_relative_to(self.root.resolve()) and source.is_file()
                    if receipt.get('video_sha256'):
                        assert hashlib.sha256(source.read_bytes()).hexdigest().upper()==receipt['video_sha256'].upper()
                    assert graph['7']['inputs'][f'videos.video{i}']==[str(i+1),0] and graph['8']['inputs']['video']==['7',0]
                    graph[str(i+1)]['inputs']['file']=relative+' [output]'
                    sources.append({'relative':relative,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
                graph['8']['inputs']['filename_prefix']=f'H3_{group_id}_MERGED'
                result=await self.validate(graph)
                assert result[0] is True, result
                # Settings are re-read after every asynchronous gate, immediately before POST.
                latest=self.read(project)['_native_merge']; active=latest['groups'][group_id]
                if not latest['auto_merge_enabled'] or not active['eligible'] or active['merge_status']!='WAITING_6_OF_6': return
                if active.get('prompt_ids')!=ids:return
                if not self.selected(project,group_id):return
                current=self.read(project)
                if any(current.get(str(i),{}).get('status')!='SUCCESS' or current[str(i)].get('prompt_id')!=ids[str(i)] for i in range(6)):return
                for i in range(6):self.inspect(project,i)
                reserved=str(uuid.uuid4()) if self.submit_reserved else None
                self.update(project, lambda s:s['groups'][group_id].update(merge_status='SUBMITTED',merge_prompt_id=reserved,merge_dispatch_epoch=time.time(),enqueue_phase='INTENT',merge_graph=graph,merge_sources=sources))
                if reserved:self.merge_jobs[reserved]=(project,group_id)
                response=await self.submit_reserved(graph,reserved) if self.submit_reserved else await self.submit(graph)
                if reserved and response.get('prompt_id')!=reserved:raise ValueError('Reserved merge prompt_id mismatch')
                assert response.get('prompt_id'), 'Ambiguous submission; do not retry'
                pid=response['prompt_id']
                current=self.read(project)['_native_merge']['groups'][group_id]
                if reserved and (current.get('merge_prompt_id')!=reserved or current.get('merge_status')!='SUBMITTED'):return
                self.update(project, lambda s:s['groups'][group_id].update(merge_prompt_id=pid))
                self.spawn(self.observe_merge(project,group_id,pid))
            except Exception as exc:
                logging.exception('Native Merge isolated failure: %s',exc)
                state=self.read(project)['_native_merge']['groups'][group_id]
                if state.get('merge_status')=='SUBMITTED' and state.get('merge_prompt_id'):
                    self.update(project,lambda s:s['groups'][group_id].update(merge_error=str(exc)))
                else:self.update(project,lambda s:s['groups'][group_id].update(merge_status='ERROR'))

    async def resume_unstarted(self,project,group_id,group):
        # The local queue gate deduplicates overlapping HTTP requests with this same
        # durable ID. A restart may rebuild an unstarted job, never a started one.
        pid=group['merge_prompt_id'];graph=group.get('merge_graph');ids=group.get('prompt_ids',{})
        state=self.read(project);current=state['_native_merge']['groups'][group_id]
        if not state['_native_merge']['auto_merge_enabled'] or not current['eligible'] or state['_native_merge']['active_group_id']!=group_id:return
        if not graph or len(graph)!=8 or set(ids)!=set(map(str,range(6))):return
        for i in range(6):
            r=state.get(str(i),{})
            if r.get('status')!='SUCCESS' or r.get('prompt_id')!=ids[str(i)] or r.get('group_id') not in (None,group_id):return
            self.inspect(project,i)
        for source in group.get('merge_sources',[]):
            path=(self.root/source['relative']).resolve()
            if not path.is_relative_to(self.root.resolve()) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Durable merge source changed')
        if len(group.get('merge_sources',[]))!=6:return
        valid=await self.validate(graph)
        if not valid[0]:raise ValueError('Recovered official merge graph invalid')
        latest=self.read(project);g=latest['_native_merge']['groups'][group_id]
        if not latest['_native_merge']['auto_merge_enabled'] or not g['eligible'] or g.get('merge_prompt_id')!=pid or g.get('prompt_ids')!=ids or g.get('enqueue_phase') not in ('INTENT','ENQUEUED'):return
        if any(latest.get(str(i),{}).get('status')!='SUCCESS' or latest[str(i)].get('prompt_id')!=ids[str(i)] for i in range(6)):return
        self.merge_jobs[pid]=(project,group_id)
        result=await self.submit_reserved(graph,pid)
        if result.get('prompt_id')!=pid:raise ValueError('Recovered merge ID mismatch')
        self.spawn(self.observe_merge(project,group_id,pid))

    def install_queue_gate(self,queue):
        # Only IDs owned by durable merge intents are intercepted. Original queue,
        # worker, model inputs and official eight-node graph remain unchanged.
        owner=getattr(queue,'h3_merge_gate_controller',None)
        if owner is self:return
        if owner is not None:raise ValueError('Another merge queue gate is already installed')
        queue.h3_merge_gate_controller=self
        original_put,original_get=queue.put,queue.get
        registry=self.root/'h3_continuation'/'_prebake_stories.json'
        if registry.is_file():
            for b in json.loads(registry.read_text(encoding='utf-8')).values():
                for gid,g in self.read(b['project_id']).get('_native_merge',{}).get('groups',{}).items():
                    if g.get('merge_prompt_id'):self.merge_jobs[g['merge_prompt_id']]=(b['project_id'],gid)
        def put(item):
            owner=self.merge_jobs.get(item[1])
            if not owner:return original_put(item)
            project,gid=owner
            with self.state_lock,queue.mutex:
                g=self.read(project)['_native_merge']['groups'][gid]
                if g.get('merge_prompt_id')!=item[1] or g.get('merge_status')!='SUBMITTED':raise ValueError('STALE merge intent')
                if g.get('merge_graph')!=item[2]:raise ValueError('Merge intent graph changed')
                running,pending=queue.get_current_queue()
                if any(x[1]==item[1] for x in running+pending) or queue.get_history(prompt_id=item[1]):return
                if g.get('enqueue_phase') in ('STARTED','FINISHED'):return
                original_put(item)
                # Worker cannot acquire queue mutex until ENQUEUED is durable.
                self.update(project,lambda st:st['groups'][gid].update(enqueue_phase='ENQUEUED'))
        def get(*args,**kwargs):
            result=original_get(*args,**kwargs)
            if result:
                item,_=result;owner=self.merge_jobs.get(item[1])
                if owner:
                    project,gid=owner
                    # Outside queue mutex: preserve the state-lock -> queue-lock order.
                    # The worker cannot execute the returned job before this commit.
                    try:
                        with self.state_lock:
                            g=self.read(project)['_native_merge']['groups'][gid]
                            if g.get('merge_prompt_id')!=item[1] or g.get('merge_status')!='SUBMITTED':raise ValueError('STALE queued merge')
                            if not self.selected(project,gid):raise ValueError('Queued merge belongs to a superseded execution')
                            self.update(project,lambda st:st['groups'][gid].update(enqueue_phase='STARTED'))
                    except Exception as ex:
                        logging.exception('Merge start blocked before official nodes execute')
                        status=queue.ExecutionStatus(status_str='error',completed=False,messages=[('execution_error',{'prompt_id':item[1],'exception_message':str(ex)})])
                        queue.task_done(result[1],{},status=status)
                        return None
            return result
        queue.put,queue.get=put,get;self.queue_dedup_enabled=True

    def merge_transition(self,project,group_id,pid,**fields):
        def change(state):
            g=state['groups'][group_id]
            if g.get('merge_prompt_id')==pid and g.get('merge_status')=='SUBMITTED':g.update(fields)
        self.update(project,change)

    async def observe_merge(self, project, group_id, pid):
        try:
            for _ in range(1800):
                state=self.read(project)['_native_merge']['groups'][group_id]
                if state.get('merge_prompt_id')!=pid or state.get('merge_status')!='SUBMITTED':return
                h=self.history(pid)
                if h:
                    assert h['status']['status_str']=='success' and h['status']['completed'] is True, 'Native Merge failed'
                    files=h['outputs'].get('8',{}).get('images',[])
                    assert len(files)==1 and files[0]['type']=='output'
                    self.merge_transition(project,group_id,pid,merge_status='SUCCESS',merge_output=files[0])
                    return
                await asyncio.sleep(2)
            raise TimeoutError('Merge observation timeout; never retry')
        except Exception:
            self.merge_transition(project,group_id,pid,merge_status='ERROR')

    def on_prompt(self, data):
        # Official extension hook. Never mutate generation graph, inputs, or server-minted ids.
        try:
            graph=data.get('prompt',{})
            # Managed attempts are registered durably before submission; the backend
            # attempt watchdog performs exact history/receipt coordination after refresh.
            if any(n.get('class_type') in ('H3ConditioningLoad','H3AttemptGuard') and n.get('inputs',{}).get('execution_json') for n in graph.values()):return data
            native=[n for n in graph.values() if n.get('class_type')=='H3ContinuationSave' and n['inputs'].get('enabled') is True]
            if len(native)!=1: return data
            project=native[0]['inputs']['project_id']; index=int(native[0]['inputs']['segment_index'])
            s=self.read(project).get('_native_merge',{}); gid=s.get('active_group_id'); g=s.get('groups',{}).get(gid)
            if not g or g['merge_status'] not in ('WAITING_6_OF_6','DISABLED') or not 0<=index<6: return data
            token=str(uuid.uuid4())
            data['extra_data']={**data.get('extra_data',{}),'h3_native_merge_receipt':token}
            self.spawn(self.observe_submission(project,gid,index,token))
        except Exception: logging.exception('Native Merge submission observation skipped')
        return data

    async def observe_submission(self, project, group_id, index, token):
        # Runs inside existing 8197 control process, independent of tabs or Agents.
        try:
            pid=None
            for _ in range(100):
                candidates=list(self.queue())+[h['prompt'] for h in self.history(None).values()]
                match=[p for p in candidates if p[3].get('h3_native_merge_receipt')==token]
                if match: pid=match[0][1]; break
                await asyncio.sleep(.1)
            if not pid: return  # Invalid/rejected generation prompt never qualifies.
            self.update(project,lambda s:s['groups'][group_id]['prompt_ids'].update({str(index):pid}))
            for _ in range(7200):
                h=self.history(pid)
                if h:
                    if h['status']['status_str']!='success' or h['status']['completed'] is not True:
                        self.update(project,lambda s:s['groups'][group_id].update(last_segment_failure=pid))
                        return
                    await self.complete(project,group_id)
                    return
                await asyncio.sleep(2)
        except Exception: logging.exception('Native Merge observation isolated from generation')


def register(server):
    import folder_paths
    import execution
    from aiohttp import web, ClientSession
    from .six_resume import inspect_segment
    root=folder_paths.get_output_directory()
    async def submit(graph):
        async with ClientSession(trust_env=False) as session:
            async with session.post(f'http://127.0.0.1:{server.port}/prompt',json={'prompt':graph,'client_id':'h3-native-auto'}) as r:
                r.raise_for_status(); return await r.json()
    async def submit_reserved(graph,pid):
        async with ClientSession(trust_env=False) as session:
            async with session.post(f'http://127.0.0.1:{server.port}/prompt',json={'prompt':graph,'prompt_id':pid,'client_id':'h3-native-auto'}) as r:
                r.raise_for_status();return await r.json()
    async def validate(graph): return await execution.validate_prompt('native-auto-preflight',graph,None)
    from .six_resume import FILE_STATE_LOCK
    controller=NativeMergeControl(root,Path(__file__).parent/'web/h3_native_merge_template.json',
        lambda pid: server.prompt_queue.get_history(prompt_id=pid).get(pid) if pid else server.prompt_queue.get_history(max_items=8),
        submit,validate,lambda project,index:inspect_segment(root,project,index,require_accepted=False),
        lambda:sum(server.prompt_queue.get_current_queue(),[]),state_lock=FILE_STATE_LOCK)
    controller.install_queue_gate(server.prompt_queue)
    controller.submit_reserved=submit_reserved
    controller.reconcile=lambda project,index:getattr(server,'h3_prebake_recover',lambda p,i:None)(project,index)
    controller.notify=lambda project:server.send_sync('h3_native_merge_state',{'project_id':project,**controller.state(project)})
    @server.routes.get('/h3/six/native-merge')
    async def get_state(request):
        try:return web.json_response(controller.state(request.query['project_id']))
        except Exception as e:return web.json_response({'error':str(e)},status=400)
    @server.routes.post('/h3/six/native-merge')
    async def set_state(request):
        try:
            origin=request.headers.get('Origin')
            if origin and origin!=f'{request.scheme}://{request.host}':raise ValueError('Origin rejected')
            d=await request.json();p=d['project_id']
            if d['action']=='settings':result=controller.settings(p,d['auto_merge_enabled'])
            elif d['action']=='begin':result=controller.begin(p,d.get('group_id'))
            else:raise ValueError('Unknown action')
            return web.json_response(result)
        except Exception as e:return web.json_response({'error':str(e)},status=400)
    server.add_on_prompt_handler(controller.on_prompt)
    return controller
