"""Independent conditioning persistence. Never loads/unloads models or changes official classes."""
import json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
import folder_paths
import comfy.model_management as mm
from comfy_execution.utils import get_executing_context
from . import cache_codec as codec

def module_at(folder):
 for m in tuple(sys.modules.values()):
  if str(getattr(m,'__file__','')).replace('\\','/').endswith('/'+folder+'/__init__.py'):return m
 raise RuntimeError('Production measurement module absent: '+folder)
def residency(require_te_zero):
 te=module_at('h3_selective_te_unload');entries=te.target_entries();census=None
 if require_te_zero:
  if entries:raise RuntimeError('TE still present; cached generation blocked')
  census=te.zero_target_census()
 audit=module_at('h3_sampler_to_vae_residency_probe')
 models=[]
 for e in mm.current_loaded_models:
  if e.model is not None and type(e.model.model).__module__=='comfy.model_base' and type(e.model.model).__name__=='MiniMaxH3':models.append(audit.model_snapshot(e))
 if len(models)>1:raise RuntimeError('Multiple H3 loaded targets')
 return {'TE_TARGET_COUNT':len(entries),'TE_SNAPSHOT':te.probe.snapshot(),'PREBAKE_TE_RELEASED':not entries if require_te_zero else None,'zero_target_census':census,'H3':models,'system':te.probe._windows_memory()}
def record(kind,data):
 ctx=get_executing_context();data.update(kind=kind,pid=os.getpid(),epoch=time.time(),prompt_id=ctx.prompt_id if ctx else None,node_id=ctx.node_id if ctx else None)
 folder=Path(folder_paths.get_user_directory())/'h3_conditioning_prebake';folder.mkdir(exist_ok=True)
 (folder/(kind+'_'+str(os.getpid())+'_'+str(time.time_ns())+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def clean_rebase_video_mask_is_fresh(latent):
 mask=latent.get('noise_mask')
 if mask is None:return True
 try:
  video_mask,audio_mask=mask.unbind()
  return bool(video_mask.eq(1).all().item()) and bool(audio_mask.eq(0).all().item())
 except Exception:
  return False

class H3ConditioningBake:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'conditioning':('CONDITIONING',),'latent':('LATENT',),'contract_json':('STRING',{'multiline':True}),'require_te_released':('BOOLEAN',{'default':True})}}
 RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='bake';CATEGORY='H3/PreBake';OUTPUT_NODE=True
 @classmethod
 def IS_CHANGED(cls,**kwargs):return float('nan')
 def bake(self,conditioning,latent,contract_json,require_te_released):
  started=time.time();state=residency(require_te_released)
  restored,meta,manifest=codec.save({'conditioning':conditioning,'latent':latent},contract_json)
  eq=codec.equivalent({'conditioning':conditioning,'latent':latent},restored)
  data={'status':'PASS','cache_key':manifest['key'],'equivalence':eq,'residency':state,'seconds':time.time()-started}
  record('BAKE',data)
  # A samples the ORIGINAL output. B will load the independently verified persisted output.
  return {'ui':{'text':[json.dumps(data)]},'result':(conditioning,latent)}

class H3ConditioningLoad:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'contract_json':('STRING',{'multiline':True})},'optional':{'execution_json':('STRING',{'default':''})}}
 RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='load';CATEGORY='H3/PreBake'
 @classmethod
 def IS_CHANGED(cls,**kwargs):return float('nan')
 def load(self,contract_json,execution_json=''):
  if execution_json:
   from .production import claim_prompt
   from server import PromptServer
   ctx=get_executing_context()
   if not ctx or not ctx.prompt_id:raise ValueError('Missing server execution prompt_id')
   claim_prompt(execution_json,ctx.prompt_id,getattr(PromptServer.instance,'h3_acceptance_state_lock',None))
  state=residency(True);started=time.time();output,meta,manifest=codec.load(contract_json)
  eq=codec.equivalent(output,output)
  record('LOAD',{'status':'PASS','cache_key':manifest['key'],'output_hash':eq['output_hash'],'residency':state,'seconds':time.time()-started,'inventory':meta['inventory']})
  return (output['conditioning'],output['latent'])

class H3PreBakeContinuationAudit:
 # Contract: the noise_mask requirement is derived from the segment's REAL
 # continuation state (the H3ContinuationPrepare plan), never from
 # segment_index alone. Clean Rebase has no inherited video prefix; the
 # official audio lock may still attach an all-ones video mask and zero audio mask.
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'conditioning':('CONDITIONING',),'latent':('LATENT',),'project_id':('STRING',),'segment_index':('INT',{'default':0})},'optional':{'plan_json':('STRING',{'forceInput':True}),'guide_guard_json':('STRING',{'default':''}),'guide_image':('IMAGE',)}}
 RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='audit';CATEGORY='H3/PreBake'
 @classmethod
 def IS_CHANGED(cls,**kwargs):return float('nan')
 def audit(self,conditioning,latent,project_id,segment_index,plan_json=None,guide_guard_json='',guide_image=None):
  if guide_guard_json:
   from .production import validate_guide_runtime
   plan=json.loads(plan_json) if plan_json else {}
   policy=json.loads(guide_guard_json)
   if not plan.get('active') or plan.get('segment_index')!=segment_index:raise ValueError('Guide anchor requires the actual continuation plan')
   if policy.get('continuation_kind','clean_rebase')=='native_prefix':
    if plan.get('clean_rebase') is True or plan.get('video_prefix_frames')!=39 or policy.get('frame_idx')!=39:raise ValueError('Native seam Guide must target the first visible frame after the real 39-frame prefix')
    self.audit(conditioning,latent,project_id,segment_index,plan_json)
   elif plan.get('clean_rebase') is not True or not clean_rebase_video_mask_is_fresh(latent):raise ValueError('Guide anchor requires every Clean Rebase video frame to remain regenerable; audio must stay locked')
   if policy.get('index')!=segment_index or policy.get('context',{}).get('project_id')!=project_id:raise ValueError('Guide audit project/segment mismatch')
   ctx=get_executing_context()
   proof=validate_guide_runtime(conditioning,latent,guide_guard_json,guide_image,ctx.prompt_id if ctx else None)
   record('GUIDE_INTEGRITY',{'status':'PASS','segment_index':segment_index,'project_id':project_id,'continuation_plan':plan,'guide_integrity':proof})
   return (conditioning,latent)
  import torch,folder_paths
  from safetensors.torch import load
  video,audio=latent['samples'].unbind()
  plan=json.loads(plan_json) if plan_json else None
  if plan is None and segment_index>0:raise ValueError('Continuation contract undetermined: segment %d carries no continuation plan; audit refuses to infer the contract from segment_index'%segment_index)
  continuation=bool(plan and plan.get('active')) and plan.get('clean_rebase') is not True
  data={'status':'PASS','segment_index':segment_index,'project_id':project_id,'residency':residency(True),'dynamic_predecessor_required':continuation,'noise_mask_required':continuation,'predecessor_read':False,'continuation_plan':plan}
  if continuation:
   vt=plan.get('video_prefix_tokens');at=plan.get('audio_prefix_steps');pf=plan.get('video_prefix_frames')
   if not isinstance(vt,int) or vt<=0 or at is None or not isinstance(pf,int) or pf<=0:raise ValueError('Continuation plan for segment %d lacks a real inherited prefix'%segment_index)
   src=plan.get('prev_source')
   if isinstance(src,str) and src.startswith('store:seg_') and src!='store:seg_%05d'%(segment_index-1):raise ValueError('Continuation plan predecessor %r does not match segment %d predecessor seg_%05d'%(src,segment_index,segment_index-1))
   if 'noise_mask' not in latent:raise ValueError('Continuation segment %d requires an inherited-prefix noise_mask; latent carries none'%segment_index)
   p=Path(folder_paths.get_output_directory())/'h3_continuation'/project_id/('seg_%05d.safetensors'%(segment_index-1))
   data['predecessor_read']=True
   previous=load(p.read_bytes());mask_video,mask_audio=latent['noise_mask'].unbind()
   spatial_transform=plan.get('video_prefix_transform')
   if spatial_transform is not None:
    native=module_at('H3_NativeContinuation')
    expected,actual_transform=native.core.adapt_video_prefix(previous['video'],tuple(video.shape),vt,video.dtype)
    if actual_transform is None or spatial_transform!=actual_transform:raise ValueError('Native spatial prefix transform contract differs from real predecessor')
    assert torch.equal(video[:,:,:vt].cpu(),expected),'Spatially adapted real predecessor prefix differs'
   else:
    assert torch.equal(video[:,:,:vt].cpu(),previous['video'][:,:,-vt:]),'Previous video latent prefix differs'
   if at:
    assert torch.equal(audio[...,:at].cpu(),previous['audio'][...,-at:]),'Previous audio latent prefix differs'
   elif plan.get('branch')!='DRIVING_AUDIO':raise ValueError('Zero inherited audio prefix requires the actual driving-audio branch')
   assert torch.all(mask_video[:,:,:vt]==0) and torch.all(mask_audio[...,:at]==0)
   assert torch.all(mask_video[:,:,vt:]==1) and torch.all(mask_audio[...,at:]==1)
   data.update(previous_path=str(p),previous_sha256=codec.file_sha(p),video_prefix_tokens=vt,audio_prefix_steps=at,video_prefix_frames=pf,protected_frames=plan.get('protected_frames',pf),prev_source=src,reuse_previous_latent=True,previous_video_tail_equal=spatial_transform is None,previous_video_prefix_verified=True,video_prefix_transform=spatial_transform,previous_audio_tail_equal=True if at else None,protected_mask_verified=True)
  else:
   if 'noise_mask' in latent:raise ValueError('Fresh segment %d (no inherited prefix, reason=%s) must not carry a noise_mask'%(segment_index,'clean_rebase' if plan and plan.get('clean_rebase') else 'continuation_off'))
   data.update(noise_mask_present=False,video_prefix_frames=(plan or {}).get('video_prefix_frames',0),protected_frames=0,prev_source=(plan or {}).get('prev_source'),reuse_previous_latent=bool((plan or {}).get('reuse_previous_latent',False)))
  data['sampler_inputs']=codec.equivalent({'conditioning':conditioning,'latent':latent},{'conditioning':conditioning,'latent':latent})
  record('CONTINUATION',data)
  return (conditioning,latent)

class H3PreBakePreviousState:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'project_id':('STRING',),'segment_index':('INT',{'default':1,'min':1})},'optional':{'group_id':('STRING',{'default':''})}}
 RETURN_TYPES=('LATENT',);FUNCTION='load';CATEGORY='H3/PreBake'
 @staticmethod
 def paths(project_id,segment_index):
  import folder_paths
  if not project_id or any(not(c.isalnum()or c in '-_')for c in project_id):raise ValueError('Invalid isolated project')
  root=Path(folder_paths.get_output_directory())/'h3_continuation'/project_id
  return root/('seg_%05d.safetensors'%(segment_index-1)),root/'six_acceptance.json'
 @classmethod
 def IS_CHANGED(cls,project_id,segment_index,group_id=''):
  p,r=cls.paths(project_id,segment_index)
  if group_id:
   from .production import token
   token(group_id)
  if not p.exists()or not r.exists():return float('nan')
  group=p.parent/('prebake_'+group_id+'.json') if group_id else None
  return codec.file_sha(p)+codec.file_sha(r)+(codec.file_sha(group) if group else '')
 def load(self,project_id,segment_index,group_id=''):
  from safetensors.torch import load
  from comfy.nested_tensor import NestedTensor
  p,r=self.paths(project_id,segment_index);prior_index=segment_index-1
  from .production import read_state,verify_predecessor
  verify_predecessor({'project_id':project_id,'group_id':group_id},segment_index)
  receipts=read_state(r);receipt=receipts.get(str(prior_index),{})
  ledger_path=None;ledger={};accepted={}
  if group_id:
   from .production import token
   ledger_path=p.parent/('prebake_'+token(group_id)+'.json')
   if ledger_path.is_file():ledger=read_state(ledger_path) or {}
   accepted=ledger.get('segments',{}).get(str(prior_index),{})
  file_exists=p.is_file();file_stat=p.stat() if file_exists else None
  actual_sha=codec.file_sha(p) if file_exists else None
  legacy_group_proven=ledger.get('group_id')==group_id and receipt.get('prompt_id') is not None and receipts.get('_native_merge',{}).get('groups',{}).get(group_id,{}).get('prompt_ids',{}).get(str(prior_index))==receipt.get('prompt_id')==accepted.get('prompt_id')
  latent_prompt_id=None
  if file_exists:
   from safetensors import safe_open
   with safe_open(str(p),framework='pt',device='cpu') as handle:latent_prompt_id=handle.metadata().get('prompt_id')
  checks={
   'VIDEO_STATUS_CHECK':{'expected':'SUCCESS','actual':accepted.get('video_status')},
   'PROMPT_ID_CHECK':{'expected':receipt.get('prompt_id'),'actual':accepted.get('prompt_id')},
   'LATENT_SHA256_CHECK':{'expected':accepted.get('latent_sha256'),'actual':actual_sha},
   'LATENT_PROMPT_ID_CHECK':{'expected':accepted.get('prompt_id'),'actual':latent_prompt_id},
   'GROUP_ID_CHECK':{'expected':group_id or None,'actual':accepted.get('group_id') or (group_id if legacy_group_proven else None)},
   'RECEIPT_GROUP_CHECK':{'expected':group_id or None,'actual':receipt.get('group_id') or (group_id if legacy_group_proven else None)},
  }
  for item in checks.values():
   expected=item['expected'];actual=item['actual']
   item['result']='PASS' if expected is not None and expected==actual else 'FAIL'
  receipt_epoch=receipt.get('accepted_at_epoch')
  accepted_epoch=accepted.get('accepted_at_epoch')
  diagnostics={
   'project_id':project_id,'group_id':group_id or None,'ledger_group_id':ledger.get('group_id'),
   'segment_index':prior_index,'dependent_segment_index':segment_index,
   'receipt_created_at':datetime.fromtimestamp(receipt_epoch,timezone.utc).isoformat() if isinstance(receipt_epoch,(int,float)) else None,
   'acceptance_submitted_at':datetime.fromtimestamp(accepted_epoch,timezone.utc).isoformat() if isinstance(accepted_epoch,(int,float)) else None,
   'receipt_prompt_id':receipt.get('prompt_id'),'receipt_status':receipt.get('status'),
   'latent_path':str(p),'latent_exists':file_exists,'latent_size_bytes':file_stat.st_size if file_stat else None,
   'latent_mtime_epoch':file_stat.st_mtime if file_stat else None,'latent_sha256':actual_sha,'checks':checks,
   'ledger_path':str(ledger_path) if ledger_path else None,
  }
  if not group_id or ledger.get('group_id')!=group_id or receipt.get('status')!='SUCCESS' or any(v['result']!='PASS' for v in checks.values()):
   diagnostic='H3PreBakePreviousState rejected predecessor: '+json.dumps(diagnostics,ensure_ascii=False,separators=(',',':'))
   record('PREVIOUS_STATE_REJECTED',{'status':'FAIL','diagnostics':diagnostics})
   raise ValueError(diagnostic)
  raw=p.read_bytes()
  if codec.digest(raw).upper()!=actual_sha:raise ValueError('Predecessor latent changed between validation and load')
  state=load(raw)
  assert set(state)=={'video','audio'}
  record('PREVIOUS_STATE',{'status':'PASS','previous_path':str(p),'previous_sha256':codec.digest(raw).upper(),'receipt':receipt,'dependent_segment':segment_index,'diagnostics':diagnostics})
  return ({'samples':NestedTensor([state['video'],state['audio']])},)

class H3AttemptGuard:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'conditioning':('CONDITIONING',),'latent':('LATENT',),'execution_json':('STRING',)}}
 RETURN_TYPES=('CONDITIONING','LATENT');FUNCTION='guard';CATEGORY='H3/PreBake'
 @classmethod
 def IS_CHANGED(cls,**kwargs):return float('nan')
 def guard(self,conditioning,latent,execution_json):
  from .production import claim_prompt
  from server import PromptServer
  ctx=get_executing_context()
  if not ctx or not ctx.prompt_id:raise ValueError('Missing server execution prompt_id')
  claim_prompt(execution_json,ctx.prompt_id,getattr(PromptServer.instance,'h3_acceptance_state_lock',None))
  return conditioning,latent

NODE_CLASS_MAPPINGS={'H3AttemptGuard':H3AttemptGuard,'H3ConditioningBake':H3ConditioningBake,'H3ConditioningLoad':H3ConditioningLoad,'H3PreBakeContinuationAudit':H3PreBakeContinuationAudit,'H3PreBakePreviousState':H3PreBakePreviousState}
from .user_guides import H3SixUserGuideAudit
NODE_CLASS_MAPPINGS['H3SixUserGuideAudit']=H3SixUserGuideAudit
