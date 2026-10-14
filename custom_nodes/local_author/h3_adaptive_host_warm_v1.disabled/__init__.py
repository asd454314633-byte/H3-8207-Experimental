"""Candidate-only official Ref2VA wrapper; cache semantics remain inherited."""
import json,logging,os,sys,time
from pathlib import Path
import comfy.model_management as mm
from comfy_api.latest import ComfyExtension,io
from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo as Official
from comfy_execution.utils import get_executing_context
FOLDER=Path(__file__).resolve().parents[2]/'user'/'h3_adaptive_host_warm'
ACTIVE={}
def audit_module():
 path=Path(__file__).parent.parent/'h3_sampler_to_vae_residency_probe'/'__init__.py'
 for m in tuple(sys.modules.values()):
  if getattr(m,'__file__',None) and Path(m.__file__)==path and hasattr(m,'model_snapshot'):return m
 raise RuntimeError('Read-only observer unavailable')
def write(record,phase):
 record['phase']=phase;record['epoch']=time.time();record['pid']=os.getpid()
 FOLDER.mkdir(parents=True,exist_ok=True)
 (FOLDER/f'{os.getpid()}_{record.get("prompt_id","offline")}_{phase}_{time.time_ns()}.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
 logging.info('H3AdaptiveHostWarm phase=%s prompt=%s epoch=%.6f',phase,record.get('prompt_id'),record['epoch'])
 return record
def verify_graph(prompt):
 refs=[n for n in prompt.values()if n['class_type']=='H3AdaptiveReferenceToVideo']
 loaders=[n for n in prompt.values()if n['class_type']=='UNETLoader']
 pdds=[n for n in prompt.values()if n['class_type']=='MiniMaxH3PDDAccApply']
 if len(refs)!=1 or len(loaders)!=1 or loaders[0]['inputs'].get('unet_name')!='minimax_h3_ref2va_pruned_int8_convrot.safetensors' or len(pdds)!=1 or pdds[0]['inputs'].get('pdd_file')!='MiniMax-H3-Ref2VA-Acc-8Step.safetensors':raise RuntimeError('Candidate unique H3/PDD graph guard failed')
 if sum(n['class_type']=='H3PartialDiffusionEvictBeforeVAE' for n in prompt.values())!=1:raise RuntimeError('Candidate partial evict missing')
def release_exact(record):
 audit=audit_module();targets=[]
 for e in tuple(mm.current_loaded_models):
  p=e.model
  if p is None:continue
  c=type(p.model)
  if c.__name__=='MiniMaxH3':
   if c.__module__!='comfy.model_base' or c.__qualname__!='MiniMaxH3':raise RuntimeError('Wrong H3 class identity')
   targets.append((e,p,p.model))
 record['H3_MATCH_COUNT']=len(targets)
 if len(targets)>1:raise RuntimeError('Multiple H3 targets; fail closed')
 if not targets:
  record.update(status='SAFE_NOOP',H3_HOST_BEFORE_GIB=0,H3_HOST_AFTER_GIB=0)
  return write(record,'H3_RELEASE_COMPLETE')
 e,p,m=targets[0]
 if e.model is not p or e.real_model is None or e.real_model()is not m or not p.is_dynamic() or not 19<=e.model_memory()/audit.shared.GIB<=20.5 or len(p.patches)!=308:raise RuntimeError('Exact H3 model/patcher/PDD guard failed')
 pre=audit.model_snapshot(e)
 if pre['errors']:raise RuntimeError('H3 measurement errors')
 record['before']=pre;record['H3_HOST_BEFORE_GIB']=pre['pins']['TE_HOSTBUFFER_GIB']
 peers=tuple(id(x)for x in mm.current_loaded_models if x is not e)
 if e.model_unload(memory_to_free=None,unpatch_weights=True)is not True:raise RuntimeError('Full lifecycle unload not reported')
 if e.model is not p or p.model is not m:raise RuntimeError('Model identity changed')
 post=audit.model_snapshot(e);record['after']=post
 if post['errors'] or post['pins']['TE_PIN_REGISTERED_GIB']>.05 or post['pins']['TE_HOSTBUFFER_GIB']>.05 or post['loaded_size_gib']>.05:raise RuntimeError('H3 residency not zero; TE blocked')
 for i,x in enumerate(mm.current_loaded_models):
  if x is e:del mm.current_loaded_models[i];break
 if any(x is e for x in mm.current_loaded_models)or tuple(id(x)for x in mm.current_loaded_models)!=peers:raise RuntimeError('Loaded entries invariant failed')
 record.update(status='PASS',H3_HOST_AFTER_GIB=post['pins']['TE_HOSTBUFFER_GIB'])
 return write(record,'H3_RELEASE_COMPLETE')
class H3AdaptiveReferenceToVideo(Official):
 @classmethod
 def define_schema(cls):
  s=Official.define_schema();s.node_id='H3AdaptiveReferenceToVideo';s.display_name='H3 Ref2VA — adaptive host warm candidate'
  s.hidden=[io.Hidden.prompt,io.Hidden.unique_id];return s
 @classmethod
 def execute(cls,**kwargs):
  ctx=get_executing_context();record={'prompt_id':ctx.prompt_id if ctx else None,'node_id':cls.hidden.unique_id,'status':'FAIL_CLOSED'}
  try:
   verify_graph(cls.hidden.prompt)
   ACTIVE[(ctx.prompt_id,ctx.node_id)]=record
   write(dict(record),'NODE136_EXECUTE_ENTER')
   release_exact(record)
   result=Official.execute(**kwargs)
   audit=audit_module();write({'prompt_id':ctx.prompt_id,'te':audit.shared.snapshot(),'models':[audit.model_snapshot(e)for e in tuple(mm.current_loaded_models)if e.model is not None]},'ENCODE_COMPLETE')
   return result
  except Exception as ex:
   write({**record,'error':f'{type(ex).__name__}: {ex}'},'FAIL_CLOSED');raise
  finally:ACTIVE.pop((ctx.prompt_id,ctx.node_id),None)
# Read-only load timestamps; never changes arguments or model lifecycle behavior.
_load=mm.load_models_gpu
def observed_load(models,*args,**kwargs):
 ctx=get_executing_context();record=ACTIVE.get((ctx.prompt_id,ctx.node_id))if ctx else None
 if record and any(type(p.model).__module__=='comfy.text_encoders.minimax' and type(p.model).__qualname__=='te.<locals>.MiniMaxH3TEModel_' for p in models):
  audit=audit_module();write({'prompt_id':ctx.prompt_id,'release_epoch':record['epoch'],'H3_models':[audit.model_snapshot(e)for e in tuple(mm.current_loaded_models)if e.model is not None and type(e.model.model).__name__=='MiniMaxH3']},'TE_LOAD_START')
 return _load(models,*args,**kwargs)
mm.load_models_gpu=observed_load
class Extension(ComfyExtension):
 async def get_node_list(self):return[H3AdaptiveReferenceToVideo]
async def comfy_entrypoint():return Extension()
