"""Backend owned attempt reconciliation and exact-ID stop loss; no model imports.
All deadlines and submission intent survive browser closure. Unknown identity blocks.
"""
import asyncio,copy,json,time,uuid,logging,hashlib
from . import production as p
ACTIVE={'PREPARED','PENDING','CANCELLING','BLOCKED'}
TERMINAL={'SUCCESS','REJECTED','FAILED','INTERRUPTED','CANCELLED','TIMED_OUT','RECOVERY_FAILED','STALE'}
class AttemptManager:
 def __init__(self,server,submit,cancel,clock=time.time,state_lock=None,monotonic=None):
  self.server,self.submit_job,self.cancel_job,self.clock,self.state_lock=server,submit,cancel,clock,state_lock
  self.inflight=set();self.progress={};self.submit_locks={}
  # Worker-level ground truth for "this exact task is out of the queue and not
  # yet done". Installed by wrapping prompt_queue.get/task_done (see install()).
  # Independent of get_current_queue snapshots, which have been observed to miss
  # a running task on this instance and caused a live attempt to be closed as
  # 'absent from queue/history' (RECOVERY_FAILED) mid-execution on 2026-10-19.
  self.executing_pids=set();self.executing_items={}
  self.monotonic=monotonic or (time.monotonic if clock is time.time else clock)
  self.timers={};self.cancel_timers={};self.identity_audit_fingerprint=None;self.parent_identity_cache={}
 def elapsed(self,a):
  if a.get('timing_basis')=='execution_start' and not a.get('execution_start_time'):return 0
  aid=a['attempt_id'];now=self.monotonic()
  if aid not in self.timers:
   # Restart cannot grant a new 300 seconds. Durable wall deadline and elapsed
   # floor conservatively retain time spent before this process observed it.
   floor=max(float(a.get('runtime_seconds',0)),max(0,self.clock()-a.get('execution_start_time',a.get('submitted_at_epoch',self.clock()))))
   self.timers[aid]=(now,floor)
  anchor,floor=self.timers[aid]
  now=min(now,self.progress.get(a.get('prompt_id'),{}).get('ended_monotonic',now))
  return max(float(a.get('runtime_seconds',0)),floor+max(0,now-anchor))
 def global_stop_block(self):
  for ctx in p.execution_state.bindings():
   ledger=p.read_state(p.ledger_path(ctx)) or {}
   for entry in ledger.get('segments',{}).values():
    a=entry.get('attempt',{})
    if a.get('stop_reason') and a.get('status') in ('CANCELLING','BLOCKED'):
     raise ValueError('Safety blocked: exact cancelled task has not been confirmed ended')
 def load(self,context,index,attempt_id=None):
  binding,data=p.bound_context(context);entry=data['segments'][str(index)];a=entry.get('attempt',{})
  if attempt_id is not None and a.get('attempt_id')!=attempt_id:raise ValueError('STALE attempt_id')
  return data,entry,a
 def save(self,context,index,data):
  path=p.ledger_path(context);receipts=p.read_state(path.parent/'six_acceptance.json') or {};a=data['segments'][str(index)]['attempt']
  old=receipts.get(str(index),{})
  if old and old.get('attempt_id') not in (None,a['attempt_id']):raise ValueError('Receipt attempt changed')
  receipts[str(index)]={**old,**a}
  p.atomic_json(path,data);p.atomic_json(path.parent/'six_acceptance.json',receipts)
 def queue_items(self):
  running,queued=self.server.prompt_queue.get_current_queue();return running,queued
 def history(self,pid):return self.server.prompt_queue.get_history(prompt_id=pid).get(pid) if pid else None
 def belongs(self,item,a):
  if item[1]!=a.get('prompt_id'):return False
  claims=[json.loads(n['inputs']['execution_json']) for n in item[2].values() if n.get('class_type') in ('H3ConditioningLoad','H3AttemptGuard') and n['inputs'].get('execution_json')]
  context=claims[0].get('context',{}) if len(claims)==1 else {}
  return len(claims)==1 and claims[0].get('attempt_id')==a['attempt_id'] and all(context.get(k)==a.get(k) for k in ('group_id','project_id','execution_version'))
 def close(self,ctx,i,data,status,reason,evidence):
  entry=data['segments'][str(i)];a=entry['attempt']
  if a['status'] in TERMINAL:return
  a.update(status=status,terminal_status=status,terminal_reason=reason,terminal_epoch=self.clock(),execution_end_time=a.get('execution_end_time') or self.clock(),end_evidence=evidence)
  if a.get('submitted_at_epoch'):a['runtime_seconds']=self.elapsed(a)
  entry.update(video_status=status,receipt_status=status)
  self.save(ctx,i,data)
 def status(self,payload):
  ctx=payload['context'];i=int(payload['index'])
  self.recover(ctx['project_id'],i)
  with p.LOCK,self.state_lock or p.nullcontext():
   _,_,a=self.load(ctx,i,payload['attempt_id'])
   if payload.get('prompt_id') and payload['prompt_id']!=a.get('prompt_id'):raise ValueError('Wrong task ID')
   return copy.deepcopy(a)
 async def submit(self,payload):
  ctx=payload['context'];i=int(payload['index']);aid=payload['attempt_id']
  lock=self.submit_locks.setdefault(aid,asyncio.Lock())
  async with lock:
   with p.LOCK,self.state_lock or p.nullcontext():
    data,entry,a=self.load(ctx,i,aid)
    self.global_stop_block()
    if a.get('dispatch_started'):raise ValueError('Attempt already dispatched; no retry')
    p.attempt_check(ctx,i,data,a)
    graph=p.clean_graph(payload['graph']);p.native_graph_check(graph,ctx,i);claims=[json.loads(n['inputs']['execution_json']) for n in graph.values() if n['class_type'] in ('H3ConditioningLoad','H3AttemptGuard') and n['inputs'].get('execution_json')]
    if len(claims)!=1 or claims[0]!={'context':ctx,'index':i,'attempt_id':aid}:raise ValueError('Submission graph claim mismatch')
    cross=a.get('snapshot',{}).get('cross_group')
    if cross or graph.get('LONG_SONG',{}).get('inputs',{}).get('cross_group_json') or 'CROSS_GROUP_PREVIOUS' in graph:
     actual=p.cross_group_gate(graph,ctx,i)
     if actual!=cross or a.get('graph_sha256')!=p.graph_digest(graph):raise ValueError('跨组提交图或前驱绑定在准备后被修改，未提交GPU')
    from .user_guides import submission_check
    submission_check(graph,ctx,i,a)
    a['prepared_graph_sha256']=a.get('graph_sha256')
    a['graph_changed_since_prepare']=a.get('graph_sha256')!=p.graph_digest(graph)
    now=self.clock();pid=str(uuid.uuid4());a.update(prompt_id=pid,status='PENDING',dispatch_started=True,submitted_at_epoch=now,deadline_epoch=None,graph_sha256=p.graph_digest(graph))
    a.update(timing_basis='execution_start',deadline_epoch=None)
    a.update(runtime_seconds=0,queue_submit_time=now,terminal_status=None)
    from .adaptive_bridge import capture
    capture(pid,graph,a)
    controller=getattr(self.server,'h3_native_merge_control',None)
    if controller:
     state=controller.read(ctx['project_id']).get('_native_merge',{})
     if not state:
      controller.settings(ctx['project_id'],ctx.get('auto_merge_enabled',True))
     controller.begin(ctx['project_id'],ctx['group_id'])
     controller.update(ctx['project_id'],lambda st:st['groups'][ctx['group_id']]['prompt_ids'].update({str(i):pid}))
    self.save(ctx,i,data);self.inflight.add(aid)
   body={'prompt':graph,'prompt_id':pid,'client_id':payload.get('client_id'),'extra_data':{'extra_pnginfo':{'workflow':payload.get('workflow')}}}
   try:
    code,result=await self.submit_job(body)
    if code>=400:
     with p.LOCK,self.state_lock or p.nullcontext():
      data,_,a=self.load(ctx,i,aid);running,queued=self.queue_items()
      if any(x[1]==pid for x in running+queued) or self.history(pid):a.update(status='BLOCKED',terminal_reason='Rejected response but server task exists');self.save(ctx,i,data)
      else:self.close(ctx,i,data,'REJECTED',str(result),{'queue_absent':True,'http_status':code})
     raise ValueError('Submission rejected: '+str(result))
    if result.get('prompt_id')!=pid:raise ValueError('Submission response ID mismatch; reconciliation required')
    return result
   except Exception:
    # A transport failure is ambiguous; durable exact ID is reconciled, never retried.
    raise
   finally:self.inflight.discard(aid)
 def request_cancel(self,payload,reason='USER_CANCEL'):
  ctx=payload['context'];i=int(payload['index'])
  with p.LOCK,self.state_lock or p.nullcontext():
   data,entry,a=self.load(ctx,i,payload['attempt_id']);pid=a.get('prompt_id')
   if not pid or payload.get('prompt_id')!=pid:raise ValueError('Cancellation identity unproven; no global interrupt')
   if a['status'] in TERMINAL:return copy.deepcopy(a)
   running,queued=self.queue_items();matches=[x for x in running+queued if x[1]==pid];h=self.history(pid)
   if any(not self.belongs(x,a) for x in matches) or (h and not self.belongs(h['prompt'],a)):
    a.update(status='BLOCKED',terminal_reason='Cancellation ownership mismatch');self.save(ctx,i,data);raise ValueError('Wrong task identity; cancellation blocked')
   a.update(status='CANCELLING',stop_reason=a.get('stop_reason') or reason,cancel_requested_epoch=a.get('cancel_requested_epoch') or self.clock(),progress_at_cancel=self.progress.get(pid),below_80_percent_at_deadline=reason=='TIMEOUT_300S' and self.progress.get(pid,{}).get('ratio',0)<.8)
   self.cancel_timers.setdefault(a['attempt_id'],self.monotonic())
   self.save(ctx,i,data)
   # Same local core atomic primitive as /api/jobs/{id}/cancel. Never global /interrupt.
   result=self.cancel_job(pid);a['cancel_dispatch_result']=bool(result);self.save(ctx,i,data)
  self.recover(ctx['project_id'],i);return self.status(payload)
 def recover(self,project,index):
  with p.LOCK,self.state_lock or p.nullcontext():
   bindings=[b for b in p.execution_state.bindings() if b['project_id']==project]
   if len(bindings)!=1:return False
   ctx=bindings[0];data,entry,a=self.load(ctx,index)
   if not a:return False
   frozen=a.get('snapshot',{}).get('context')
   if frozen:
    if any(frozen.get(k)!=ctx.get(k) for k in ('story_id','project_id','group_id','execution_version')):raise ValueError('Recovery snapshot ownership mismatch')
    # Registry bindings omit execution-only fields such as fps. Reconcile the
    # exact task with its immutable submitted context, not a lossy UI binding.
    ctx=copy.deepcopy(frozen)
   if a['status']=='STALE' and a.get('prompt_id'):
    running,queued=self.queue_items()
    if any(x[1]==a['prompt_id'] for x in running+queued):
     a.update(status='CANCELLING',stop_reason='EDIT_INVALIDATION');self.save(ctx,index,data)
     self.request_cancel({'context':ctx,'index':index,'attempt_id':a['attempt_id'],'prompt_id':a['prompt_id']},'EDIT_INVALIDATION');return True
   if a['status'] in TERMINAL:
    # Repair a crash between terminal ledger and receipt writes from durable evidence.
    r=(p.read_state(p.ledger_path(ctx).parent/'six_acceptance.json') or {}).get(str(index),{})
    if a['status']!='SUCCESS' and r.get('status')!=a['status']:self.save(ctx,index,data)
    elif a['status']=='SUCCESS' and r.get('status')!='SUCCESS':p.accepted({'context':ctx,'index':index,'prompt_id':a['prompt_id'],'cache_key':entry['cache_key']},self.server,self.state_lock)
    return True
   pid=a.get('prompt_id')
   running,queued=self.queue_items();matches=[x for x in running+queued if x[1]==pid] if pid else [];h=self.history(pid)
   if any(not self.belongs(x,a) for x in matches) or (h and not self.belongs(h['prompt'],a)):
    a.update(status='BLOCKED',terminal_reason='Server ownership mismatch');self.save(ctx,index,data);return True
   if pid:
    record=self.progress.get(pid,{})
    a.update(record.get('timing',{}))
    if a.get('timing_basis')=='execution_start':
     if not a.get('execution_start_time'):
      starts=[float(d['timestamp'])/1000 for event,d in (h or {}).get('status',{}).get('messages',[]) if event=='execution_start' and 'timestamp' in d]
      if starts:a['execution_start_time']=min(starts)
      elif any(x[1]==pid for x in running):a['execution_start_time']=self.clock()
      elif h:a['execution_start_time']=a['submitted_at_epoch'] # Legacy terminal evidence: conservative.
     if a.get('execution_start_time'):
      a['deadline_epoch']=None
      if a['attempt_id'] not in self.timers and record.get('started_monotonic') is not None:
       self.timers[a['attempt_id']]=(record['started_monotonic'],0)
    a['runtime_seconds']=self.elapsed(a)
   if a.get('stop_reason'):
    if matches:
     anchor=self.cancel_timers.setdefault(a['attempt_id'],self.monotonic()-max(0,self.clock()-a.get('cancel_requested_epoch',self.clock())))
     if self.monotonic()-anchor>=30:
      a.update(status='BLOCKED',terminal_reason='Cancellation confirmation exceeded 30 seconds; task still present')
     self.save(ctx,index,data);return True # Acknowledgement is not GPU-stop proof.
    self.close(ctx,index,data,'TIMED_OUT' if a['stop_reason']=='TIMEOUT_300S' else 'CANCELLED',a['stop_reason'],{'queue_absent':True,'history_status':h.get('status') if h else None,'cancel_dispatch_result':a.get('cancel_dispatch_result')});return True
   if h:
    ended=self.progress.get(pid,{}).get('ended_monotonic')
    if ended is not None:a['monotonic_completion_proven']=True
    else:
     stamps=[float(d['timestamp'])/1000 for e,d in h['status'].get('messages',[]) if e=='execution_success' and 'timestamp' in d]
     if stamps:a['runtime_seconds']=max(stamps)-a.get('execution_start_time',a['submitted_at_epoch'])
    self.save(ctx,index,data)
    if h['status'].get('status_str')=='success' and h['status'].get('completed') is True:
     try:p.accepted({'context':ctx,'index':index,'prompt_id':pid,'cache_key':entry['cache_key']},self.server,self.state_lock)
     except Exception as ex:
      self.close(ctx,index,data,'TIMED_OUT' if '300 second' in str(ex) else 'RECOVERY_FAILED',str(ex),{'queue_absent':not matches,'history_status':h['status']})
    else:
     interrupted=any(e=='execution_interrupted' for e,_ in h['status'].get('messages',[]))
     if not matches:self.close(ctx,index,data,'INTERRUPTED' if interrupted else 'FAILED','Server terminal failure',{'queue_absent':True,'history_status':h['status']})
    return True
   # No automatic generation deadline. User cancellation and ownership checks remain.
   if not pid and self.clock()-a.get('prepared_at_epoch',self.clock())>=30:
    self.close(ctx,index,data,'REJECTED','Preparation expired before submission',{'not_dispatched':True});return True
   if pid and (pid in self.executing_pids or (getattr(self.server,'last_prompt_id',None)==pid and not self.history(pid))):
    # The worker popped this exact task and task_done has not released it:
    # it is executing right now, whatever a queue snapshot claims. Never close
    # a running attempt as 'absent from queue/history' (see 2026-10-19 incident).
    self.save(ctx,index,data);return True
   if pid and not matches and a['attempt_id'] not in self.inflight and self.clock()-a.get('submitted_at_epoch',self.clock())>=5:
    self.close(ctx,index,data,'RECOVERY_FAILED','Exact submitted task absent from queue/history',{'queue_absent':True,'history_absent':True});return True
   if pid:self.save(ctx,index,data)
   return True
 def record_progress(self,event,data):
  pid=data.get('prompt_id')
  if not pid:return
  record=self.progress.setdefault(pid,{'timing':{}});timing=record.setdefault('timing',{})
  if event=='execution_start':
   timing.setdefault('execution_start_time',self.clock());record.setdefault('started_monotonic',self.monotonic())
  if event=='progress' and data.get('max',0)>0:
   timing.setdefault('sampling_start_time',self.clock())
   record.update(value=data.get('value',0),max=data['max'],ratio=data.get('value',0)/data['max'],node=data.get('node'),epoch=self.clock())
  if event in ('execution_success','execution_error','execution_interrupted'):
   record.setdefault('ended_monotonic',self.monotonic())
   timing.setdefault('execution_end_time',self.clock())
   if event=='execution_success':timing.setdefault('video_save_end_time',self.clock())
 def inherited_attempt_class(self,ctx,index,attempt,entry,parent_cache,ancestor_projects):
  """Classify only immutable, parent-ledger-proven copies as history.

  An inherited attempt is never recovered from the child ledger. It is treated
  as historical only when the child's provenance, the immutable parent ledger,
  and the parent's receipt all agree on the exact attempt and prompt IDs.
  """
  provenance=entry.get('inherited_from') or {}
  source=(provenance.get('project_id'),provenance.get('execution_version'),
          attempt.get('group_id'))
  identity=(attempt.get('project_id'),attempt.get('execution_version'),attempt.get('group_id'))
  source_key=(*source,attempt.get('attempt_id'),attempt.get('prompt_id'))
  evidence={'source':source_key,'attempt_status':attempt.get('status'),
            'provenance_attempt_id':provenance.get('attempt_id'),
            'provenance_prompt_id':provenance.get('prompt_id')}
  if (not all(source) or identity!=source or
      provenance.get('parent_project_id') not in ancestor_projects or
      provenance.get('prompt_id')!=attempt.get('prompt_id') or
      provenance.get('project_id')!=attempt.get('project_id') or
      provenance.get('execution_version')!=attempt.get('execution_version')):
   evidence['classification']='unconfirmed'
   return 'unconfirmed',evidence
  parent_key=source
  cached=parent_cache.get(parent_key)
  if cached is None:
   parent_ctx={'story_id':ctx['story_id'],'group_id':source[2],
               'project_id':source[0],'execution_version':source[1]}
   parent_path=p.ledger_path(parent_ctx);receipt_path=parent_path.parent/'six_acceptance.json'
   ledger_sig=self._state_signature(parent_path);receipt_sig=self._state_signature(receipt_path)
   previous=self.parent_identity_cache.get(parent_key)
   if previous and ledger_sig is not None and receipt_sig is not None and previous[:2]==(ledger_sig,receipt_sig):
    ledger,receipts=previous[2],previous[3]
   else:
    ledger=p.read_state(parent_path) or {};receipts=p.read_state(receipt_path) or {}
    self.parent_identity_cache[parent_key]=(ledger_sig,receipt_sig,ledger,receipts)
   parent_cache[parent_key]=(ledger,receipts)
  ledger,receipts=parent_cache[parent_key];receipt=receipts.get(str(index),{})
  execution=ledger.get('execution') or {}
  parent_attempt=(ledger.get('segments',{}).get(str(index),{}).get('attempt') or {})
  parent_identity=all(execution.get(k)==source_value for k,source_value in zip(
      ('project_id','execution_version','group_id'),source))
  exact_attempt=all(parent_attempt.get(k)==attempt.get(k) for k in
      ('attempt_id','prompt_id','project_id','execution_version','group_id'))
  exact_receipt=all(receipt.get(k)==attempt.get(k) for k in
      ('attempt_id','prompt_id','project_id','execution_version','group_id'))
  terminal=(parent_attempt.get('status') in TERMINAL and
            receipt.get('status')==parent_attempt.get('status'))
  evidence.update(parent_status=parent_attempt.get('status'),receipt_status=receipt.get('status'),
                  parent_ledger_execution=parent_identity,parent_attempt_match=exact_attempt,
                  parent_receipt_match=exact_receipt)
  if parent_identity and exact_attempt and exact_receipt and terminal:
   evidence['classification']='verified-parent-terminal'
   return 'verified-parent-terminal',evidence
  evidence['classification']='unconfirmed'
  return 'unconfirmed',evidence
 def _state_signature(self,path):
  try:
   stat=path.stat()
   return (getattr(stat,'st_ino',None),stat.st_size,stat.st_mtime_ns)
  except FileNotFoundError:return None # Missing evidence is never a reusable identity proof.
  except OSError:return None
 async def tick(self):
  bindings=p.execution_state.bindings();parent_cache={};identity_audit=[]
  by_version={b.get('execution_version'):b for b in bindings}
  for ctx in bindings:
   ancestor_projects=set();cursor=ctx;seen_versions=set()
   while cursor and cursor.get('execution_version') not in seen_versions:
    seen_versions.add(cursor.get('execution_version'));ancestor_projects.add(cursor.get('project_id'))
    cursor=by_version.get(cursor.get('parent_execution_version'))
   data=p.read_state(p.ledger_path(ctx)) or {}
   for i,entry in list(data.get('segments',{}).items()):
    # A successful fork keeps the parent's receipt and provenance separately;
    # only a live attempt owned by this exact execution is eligible for recovery.
    attempt=entry.get('attempt')
    if not attempt:
     continue
    if any(attempt.get(k)!=ctx.get(k) for k in ('project_id','group_id','execution_version')):
     classification,evidence=self.inherited_attempt_class(ctx,int(i),attempt,entry,parent_cache,ancestor_projects)
     key=(ctx.get('project_id'),ctx.get('execution_version'),int(i),attempt.get('attempt_id'),classification,evidence)
     identity_audit.append(key)
     continue
    try:self.recover(ctx['project_id'],int(i))
    except Exception:logging.exception('H3 attempt recovery blocked for %s/%s',ctx['project_id'],i)
  if identity_audit:
   fingerprint=hashlib.sha256(json.dumps(identity_audit,sort_keys=True,default=str,separators=(',',':')).encode()).hexdigest()
   if fingerprint!=self.identity_audit_fingerprint:
    historical=sum(1 for x in identity_audit if x[4]=='verified-parent-terminal')
    unconfirmed=len(identity_audit)-historical
    if unconfirmed:
     logging.warning('H3 inherited attempt audit changed: verified_parent_terminal=%d unconfirmed=%d fingerprint=%s; mismatched child attempts remain isolated from recovery',historical,unconfirmed,fingerprint[:16])
    else:
     logging.info('H3 inherited attempt audit changed: verified_parent_terminal=%d unconfirmed=0 fingerprint=%s; historical attempts isolated from recovery',historical,fingerprint[:16])
    self.identity_audit_fingerprint=fingerprint
  else:self.identity_audit_fingerprint=None
  controller=getattr(self.server,'h3_native_merge_control',None)
  if controller:
   for ctx in bindings:
    selected=p.execution_state.selected_story(ctx['story_id'])
    if not selected or selected['execution_version']!=ctx['execution_version']:continue
    state=controller.read(ctx['project_id']).get('_native_merge',{})
    if state.get('active_group_id')==ctx['group_id'] and ctx['group_id'] in state.get('groups',{}):await controller.complete(ctx['project_id'],ctx['group_id'])
 async def run(self):
  while True:
   try:await self.tick()
   except Exception:logging.exception('H3 durable watchdog recovery blocked')
   await asyncio.sleep(.25)

def install(server):
 if getattr(server,'h3_attempt_manager',None):return server.h3_attempt_manager
 from aiohttp import web,ClientSession
 async def submit(body):
  async with ClientSession(trust_env=False) as session:
   async with session.post(f'http://127.0.0.1:{server.port}/prompt',json=body) as r:return r.status,await r.json()
 def cancel(pid):
  q=server.prompt_queue
  removed=q.delete_queue_item(lambda item:item[1]==pid)
  return q.interrupt_if_running(pid) or removed
 manager=AttemptManager(server,submit,cancel,state_lock=getattr(server,'h3_acceptance_state_lock',None));server.h3_attempt_manager=manager
 # Worker-level liveness tracking: wrap the exact queue object the execution
 # worker uses, so the manager knows which prompt_ids are out of the queue and
 # not yet done, independent of any queue snapshot (additive; no behavior change).
 _pq=server.prompt_queue
 _orig_get=_pq.get
 def _traced_get(*args,**kwargs):
  result=_orig_get(*args,**kwargs)
  try:
   if result:
    _item,_item_id=result
    _pid=str(_item[1]);manager.executing_items[int(_item_id)]=_pid;manager.executing_pids.add(_pid)
  except Exception:pass
  return result
 _pq.get=_traced_get
 _orig_done=_pq.task_done
 def _traced_done(*args,**kwargs):
  # Publish History before dropping the worker liveness proof. Removing it
  # first leaves a queue-to-History handoff race for the watchdog.
  result=_orig_done(*args,**kwargs)
  try:
   _pid=manager.executing_items.pop(int(args[0]),None)
   if _pid is not None:manager.executing_pids.discard(_pid)
  except Exception:pass
  return result
 _pq.task_done=_traced_done
 import hashlib
 logging.info('H3_ATTEMPT_LIFECYCLE_LOADED module=%s sha256=%s monotonic=true cancel_confirmation_seconds=30',__file__,hashlib.sha256(open(__file__,'rb').read()).hexdigest())
 for name,fn in (('submit',manager.submit),('attempt-status',manager.status),('cancel',manager.request_cancel)):
  async def handler(request,fn=fn):
   try:
    origin=request.headers.get('Origin')
    if origin and origin!=f'{request.scheme}://{request.host}':raise ValueError('Origin rejected')
    payload=await request.json();result=fn(payload)
    if asyncio.iscoroutine(result):result=await result
    return web.json_response(result)
   except Exception as ex:return web.json_response({'error':str(ex)},status=409)
  server.routes.post('/h3/prebake/'+name)(handler)
 original=server.send_sync
 def send(event,data,*args,**kwargs):manager.record_progress(event,data or {});return original(event,data,*args,**kwargs)
 server.send_sync=send
 async def start(app):
  manager.state_lock=getattr(server,'h3_acceptance_state_lock',None)
  p.STATE_LOCK=manager.state_lock
  app['h3_attempt_watchdog']=asyncio.create_task(manager.run())
 async def stop(app):
  task=app.get('h3_attempt_watchdog')
  if task:
   task.cancel()
   try:await task
   except asyncio.CancelledError:pass
 server.app.on_startup.append(start);server.app.on_cleanup.append(stop)
 return manager
