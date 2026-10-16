"""Dynamic CPU contracts using real cache/state/attempt code.
Transport, folder roots and host registration metadata are CPU fixtures.
No ComfyUI service, model, video or GPU is started.
The --rpc mode lets the real frontend adapter call the real Python state logic over JSON pipes.
"""
from pathlib import Path
import argparse,asyncio,copy,hashlib,importlib,json,os,sys,tempfile,types,unittest
os.environ['CUDA_VISIBLE_DEVICES']='-1'
ARGS=argparse.ArgumentParser();ARGS.add_argument('--host',required=True);ARGS.add_argument('--rpc',action='store_true');opts,remaining=ARGS.parse_known_args()
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(opts.host).resolve()))
import torch
assert not torch.cuda.is_initialized()
PKG='_h3_prebake_cpu_contract';pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT/'custom_nodes/local_author/h3_conditioning_prebake')];sys.modules[PKG]=pkg
C=importlib.import_module(PKG+'.cache_codec');P=importlib.import_module(PKG+'.production');L=importlib.import_module(PKG+'.attempt_lifecycle')
class Queue:
 def __init__(self):self.items=[];self.hist={}
 def get_current_queue(self):return [],list(self.items)
 def get_history(self,prompt_id=None,**kw):return {prompt_id:self.hist[prompt_id]} if prompt_id in self.hist else {}
class Harness:
 def __init__(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);C.ROOT=self.root/'cache';C.MODEL_REGISTRY={};P.STATE_LOCK=None
  paths=types.ModuleType('folder_paths');paths.get_output_directory=lambda:str(self.root/'output');paths.get_input_directory=lambda:str(self.root/'input');sys.modules['folder_paths']=paths
  self.queue=Queue();self.server=types.SimpleNamespace(prompt_queue=self.queue);self.clock=1000.;self.submissions=[];self.cancelled=[];self.restart()
  # Adaptive capture/recovery now reads live host registration and singleton.
  # Provide an empty synthetic host rather than importing CUDA-owning server/nodes.
  server=types.ModuleType('server');server.PromptServer=types.SimpleNamespace(instance=self.server);sys.modules['server']=server
  nodes=types.ModuleType('nodes');nodes.NODE_CLASS_MAPPINGS={};sys.modules['nodes']=nodes
 def restart(self):self.manager=L.AttemptManager(self.server,self.submit,self.cancel,clock=lambda:self.clock,monotonic=lambda:self.clock)
 async def submit(self,body):
  self.submissions.append(copy.deepcopy(body));self.queue.items.append((0,body['prompt_id'],copy.deepcopy(body['prompt']),{},[]));return 200,{'prompt_id':body['prompt_id']}
 def cancel(self,pid):self.cancelled.append(pid);self.queue.items=[x for x in self.queue.items if x[1]!=pid];return True
 def bind(self):return P.story({'action':'bind','story_id':'CPU_STORY','group_id':'CPU_GROUP','project_id':'CPU_PROJECT','start_index':0,'start_mode':'independent'})['binding']
 def graph(self):return {'136':{'class_type':'MiniMaxH3ReferenceToVideo','inputs':{'prompt':['138',0]}},'138':{'class_type':'PrimitiveStringMultiline','inputs':{'value':'Synthetic daylight scene'}},'125':{'class_type':'SamplerCustomAdvanced','inputs':{}},'PREP':{'class_type':'H3ContinuationPrepare','inputs':{'enabled':False}},'764':{'class_type':'CreateVideo','inputs':{'fps':24,'images':['136',0]}}}
 def plan(self,ctx):
  texts=['Synthetic daylight scene '+str(i) for i in range(6)];result=P.plan({'graph':self.graph(),'context':ctx,'texts':texts});return texts,result
 def prepare(self):
  ctx=self.bind();texts,planned=self.plan(ctx);result=P.fallback({'graph':self.graph(),'context':ctx,'index':0,'text':texts[0],'cache_key':planned['plans'][0]['cache_key']});return {'context':ctx,'index':0,'attempt_id':result['attempt_id'],'graph':result['graph']}
 def close(self):self.temp.cleanup()
 async def rpc(self,cmd,payload):
  if cmd=='story':return P.story(payload)
  if cmd=='execution':return P.execution_state.prepare(payload)
  if cmd=='draft':return P.execution_state.draft(payload)
  if cmd=='plan':return P.plan(payload)
  if cmd=='fallback':return P.fallback(payload)
  if cmd=='invalidate':
   result=P.invalidate_texts(payload);await self.manager.tick();return result
  if cmd=='submit':return await self.manager.submit(payload)
  if cmd=='attempt-status':return self.manager.status(payload)
  if cmd=='cancel':return self.manager.request_cancel(payload)
  if cmd=='restart':self.restart();return {'restarted':True}
  if cmd=='stats':return {'submissions':len(self.submissions),'queued':len(self.queue.items),'cancelled':self.cancelled,'gpu_initialized':torch.cuda.is_initialized()}
  if cmd=='accepted':return P.accepted(payload,self.server)
  raise ValueError('Unsupported test route')
class DynamicContracts(unittest.IsolatedAsyncioTestCase):
 def setUp(self):self.h=Harness()
 def tearDown(self):self.h.close();self.assertFalse(torch.cuda.is_initialized())
 def test_real_safetensors_roundtrip_and_corruption(self):
  dependency=self.h.root/'synthetic-dependency.txt';dependency.write_text('synthetic public fixture')
  text='Synthetic daylight scene';contract={'schema':C.SCHEMA,'prompt_sha256':C.digest(text.encode()),'reference_slots':[],'width':16,'height':16,'frames':1,'fps':24,'h3':{},'te':{},'node136':{},'generation_mode':'CPU_TEST','ref2va_branch':'CPU_TEST','conditioning_parameters':{'prompt':text},'files':[{'role':'reference','path':str(dependency),'sha256':C.file_sha(dependency)}]}
  ct=json.dumps(contract);original={'conditioning':[[torch.arange(12,dtype=torch.float32).reshape(1,3,4),{'pooled_output':torch.zeros(1,4)}]],'latent':{'samples':torch.ones(1,4,1,2,2)}}
  restored,_,manifest=C.save(original,ct);self.assertTrue(C.equivalent(original,restored)['CONDITIONING_NUMERIC_EQUAL'])
  file=C.ROOT/manifest['key']/'tensors.safetensors';b=file.read_bytes();file.write_bytes(b[:-1]+bytes([b[-1]^1]))
  with self.assertRaises(ValueError):C.load(ct,restore_device=False)
 def test_durable_story_restore(self):
  ctx=self.h.bind();restored=P.story({'story_id':'CPU_STORY','action':'restore'})['binding'];self.assertEqual(ctx,restored)
  self.h.restart();self.assertEqual(ctx,P.story({'story_id':'CPU_STORY','action':'restore'})['binding'])
 def test_wrong_execution_version_rejected(self):
  ctx=self.h.bind();ctx={**ctx,'execution_version':'wrong'}
  with self.assertRaises(ValueError):self.h.plan(ctx)
 def test_six_segment_plan_and_edit_invalidation(self):
  ctx=self.h.bind();texts,plans=self.h.plan(ctx);self.assertEqual(len(plans['plans']),6)
  texts[2]='Edited synthetic daylight scene';result=P.invalidate_texts({'context':ctx,'texts':texts});self.assertEqual(result['invalidated_video_from'],2);self.assertEqual(result['binding']['revisions'],[0,0,1,0,0,0])
 async def test_concurrent_submit_once(self):
  payload=self.h.prepare();results=await asyncio.gather(self.h.manager.submit(payload),self.h.manager.submit(payload),return_exceptions=True)
  self.assertEqual(sum(isinstance(r,dict) for r in results),1);self.assertEqual(len(self.h.submissions),1)
 async def test_restart_keeps_exact_pending_identity(self):
  payload=self.h.prepare();result=await self.h.manager.submit(payload);self.h.restart();state=self.h.manager.status({**payload,'prompt_id':result['prompt_id']});self.assertEqual(state['status'],'PENDING');self.assertEqual(state['prompt_id'],result['prompt_id']);self.assertEqual(len(self.h.submissions),1)
 async def test_long_generation_does_not_auto_cancel_at_300_seconds(self):
  payload=self.h.prepare();result=await self.h.manager.submit(payload);self.h.manager.record_progress('execution_start',{'prompt_id':result['prompt_id']});self.h.clock+=301;self.h.manager.recover(payload['context']['project_id'],0);state=self.h.manager.status(payload);self.assertEqual(state['status'],'PENDING');self.assertIsNone(state['deadline_epoch']);self.assertEqual(self.h.cancelled,[])
 async def test_queue_wait_is_not_execution_time(self):
  payload=self.h.prepare();result=await self.h.manager.submit(payload);self.h.clock+=1200;state=self.h.manager.status(payload)
  self.assertEqual(state['status'],'PENDING');self.assertEqual(state['runtime_seconds'],0);self.assertEqual(self.h.cancelled,[])
 def test_arbitrary_independent_stage_start(self):
  for index in (1,3,5):
   ctx=P.execution_state.prepare({'context':{'story_id':'CPU_START_'+str(index),'project_id':'CPU_PROJECT_'+str(index),'group_id':'CPU_GROUP_'+str(index),'fps':24},'graph':self.h.graph(),'texts':['Synthetic scene '+str(i) for i in range(6)],'requested_index':index,'start_index':index,'start_mode':'independent'})['binding']
   self.assertEqual(ctx['start_index'],index);self.assertEqual(ctx['start_mode'],'independent')
 async def test_wrong_cancel_identity_does_not_interrupt(self):
  payload=self.h.prepare();await self.h.manager.submit(payload)
  with self.assertRaises(ValueError):self.h.manager.request_cancel({**payload,'prompt_id':'wrong'})
  self.assertEqual(self.h.cancelled,[])
 async def test_no_history_does_not_mint_success(self):
  payload=self.h.prepare();result=await self.h.manager.submit(payload)
  with self.assertRaises(ValueError):P.accepted({'context':payload['context'],'index':0,'prompt_id':result['prompt_id'],'cache_key':P.read_state(P.ledger_path(payload['context']))['segments']['0']['cache_key']},self.h.server)
  self.assertNotEqual(P.read_state(P.ledger_path(payload['context']))['segments']['0'].get('video_status'),'SUCCESS')
async def rpc_main():
 h=Harness();print(json.dumps({'ready':True}),flush=True)
 try:
  for line in sys.stdin:
   req=json.loads(line)
   try:answer={'id':req['id'],'ok':True,'result':await h.rpc(req['cmd'],req.get('payload',{}))}
   except Exception as ex:answer={'id':req['id'],'ok':False,'error':str(ex)}
   print(json.dumps(answer,ensure_ascii=False),flush=True)
 finally:h.close()
if __name__=='__main__':
 if opts.rpc:asyncio.run(rpc_main())
 else:unittest.main(argv=[sys.argv[0],*remaining])
