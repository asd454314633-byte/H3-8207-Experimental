"""Temporary, opt-in observational H3 probe. No tensor modifications; abort after first DiT.
Loaded only during authorized audit; remove this custom-node directory after audit.
"""
import json, hashlib, inspect, sys, threading, logging
from pathlib import Path
import torch
from safetensors.torch import save_file
from server import PromptServer
import comfy.model_base as mb
import comfy.ldm.minimax.model as mm
import execution
import nodes
# Comfy loads built-in extras under loader-generated module names; use the
# actual registered classes, not a second import of the same source file.
Ref=nodes.NODE_CLASS_MAPPINGS['MiniMaxH3ReferenceToVideo']
BasicGuider=nodes.NODE_CLASS_MAPPINGS['BasicGuider']

OUT=Path(r'<USER_HOME>\Documents\ChatGPT\导演台\H3_CONDITIONING_DIT_AUDIT_20261004')
TLS=threading.local()
def current():return getattr(TLS,'case',None)
def emit(stage,data):
 c=current()
 if c:
  with (OUT/(c+'.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps({'stage':stage,**data},ensure_ascii=False)+'\n')
  logging.info('[H3 CONDITION AUDIT] %s %s',c,stage)
def tensor(t):
 a=t.detach().to('cpu').contiguous();f=a.float()
 result={'shape':list(a.shape),'dtype':str(a.dtype),'sha256':hashlib.sha256(a.reshape(-1).view(torch.uint8).numpy().tobytes()).hexdigest(),'finite':bool(torch.isfinite(f).all()),'mean':float(f.mean()) if a.numel() else None,'std':float(f.std()) if a.numel()>1 else 0,'min':float(f.min()) if a.numel() else None,'max':float(f.max()) if a.numel() else None}
 if a.dtype==torch.int64 and a.ndim==1:
  values,counts=torch.unique(a,return_counts=True);result['value_counts']={str(int(v)):int(n) for v,n in zip(values,counts)}
 return result
def cond(c):
 return [{'embedding':tensor(x[0]),'keys':list(x[1]),'minimax_refs_count':len(x[1].get('minimax_refs',[])),'tags':tensor(x[1]['minimax_token_tags']) if isinstance(x[1].get('minimax_token_tags'),torch.Tensor) else None,'refs':[{'kind':r['kind'],'latent':tensor(r['latent'])} for r in x[1].get('minimax_refs',[]) if 'latent' in r]} for x in c]
class H3AuditClipMarker:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'clip':('CLIP',),'audit_case':('STRING',)}}
 RETURN_TYPES=('CLIP',);FUNCTION='run';CATEGORY='audit'
 def run(self,clip,audit_case):
  if audit_case not in ['A_ref1','B_ref1','A_no_ref1','A_ref_repeat1']:raise ValueError('unauthorized audit case')
  TLS.case=audit_case;TLS.forwards=0
  emit('marker',{'thread':threading.get_ident()})
  return (clip,)
class H3AuditSink:
 @classmethod
 def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',)}}
 RETURN_TYPES=();FUNCTION='run';OUTPUT_NODE=True;CATEGORY='audit'
 def run(self,latent):raise RuntimeError('AUDIT_UNEXPECTED_SAMPLER_COMPLETION')
NODE_CLASS_MAPPINGS={'H3AuditClipMarker':H3AuditClipMarker,'H3AuditSink':H3AuditSink}

orig_ref=Ref.execute
def ref_execute(cls,*args,**kwargs):
 if not current():return orig_ref(*args,**kwargs)
 bound=inspect.signature(orig_ref).bind(*args,**kwargs);bound.apply_defaults();images=bound.arguments.get('ref_images') or {}
 emit('execute_entry',{'ref_images_count':sum(x is not None for x in images.values()),'keys':list(images),'images':[tensor(x) for x in images.values() if x is not None],'vae_present':bound.arguments.get('vae') is not None,'prompt_sha256':hashlib.sha256(bound.arguments['prompt'].encode()).hexdigest()})
 expected=0 if current()=='A_no_ref1' else 3
 if sum(x is not None for x in images.values())!=expected:raise RuntimeError('H3_AUDIT_P0_REF_COUNT_MISMATCH')
 target=orig_ref.__func__.__code__;old=sys.getprofile()
 def profile(frame,event,arg):
  if frame.f_code is target and event=='return':
   emit('execute_locals',{'ref_items_count':len(frame.f_locals.get('ref_items',[])),'ref_blocks_count':len(frame.f_locals.get('ref_blocks',[]))})
 sys.setprofile(profile)
 try:r=orig_ref(*args,**kwargs)
 finally:sys.setprofile(old)
 emit('node_conditioning',{'conditioning':cond(r.result[0])})
 if any(len(x[1].get('minimax_refs',[]))!=expected for x in r.result[0]):raise RuntimeError('H3_AUDIT_P0_NODE_REFS_LOSS')
 return r
Ref.execute=classmethod(ref_execute)
orig_guider=BasicGuider.execute
def guider_execute(cls,model,conditioning):
 if current():
  emit('guider_conditioning',{'conditioning':cond(conditioning)})
  expected=0 if current()=='A_no_ref1' else 3
  if any(len(x[1].get('minimax_refs',[]))!=expected for x in conditioning):raise RuntimeError('H3_AUDIT_P0_GUIDER_REFS_LOSS')
 return orig_guider(model,conditioning)
BasicGuider.execute=classmethod(guider_execute)
orig_extra=mb.MiniMaxH3.extra_conds
def extra(self,**kwargs):
 r=orig_extra(self,**kwargs)
 if current():
  p=r['minimax_payload'].cond
  emit('extra_conds',{'input_refs_count':len(kwargs.get('minimax_refs',[])),'payload_refs_count':len(p.get('refs',[])),'crossattn':tensor(r['c_crossattn'].cond),'tags':tensor(p['text_token_tags']) if isinstance(p.get('text_token_tags'),torch.Tensor) else None,'payload_keys':list(p)})
  expected=0 if current()=='A_no_ref1' else 3
  if len(p.get('refs',[]))!=expected:raise RuntimeError('H3_AUDIT_P0_PAYLOAD_REFS_LOSS')
  if not isinstance(p.get('text_token_tags'),torch.Tensor):raise RuntimeError('H3_AUDIT_P0_TOKEN_TAGS_MISSING')
 return r
mb.MiniMaxH3.extra_conds=extra
orig_layout=mm.PackedLayout.__init__
def layout(self,*args,**kwargs):
 orig_layout(self,*args,**kwargs)
 if current():emit('packed_layout',{'segments':[list(s) for s in self.segments],'ref_img_segments':sum(s[2]=='ref_img' for s in self.segments),'seq_len':self.seq_len})
mm.PackedLayout.__init__=layout
orig_forward=mm.MiniMaxH3Model._forward
def forward(self,x,timestep,context,transformer_options={},minimax_payload=None,denoise_mask=None,audio_denoise_mask=None,**kwargs):
 if not current():return orig_forward(self,x,timestep,context,transformer_options,minimax_payload,denoise_mask,audio_denoise_mask,**kwargs)
 TLS.forwards+=1;p=minimax_payload or {}
 emit('dit_entry',{'forward_index':TLS.forwards,'input_video':tensor(x[0]),'input_audio':tensor(x[1]),'timestep':tensor(timestep),'context':tensor(context),'refs_count':len(p.get('refs',[])),'tags':tensor(p['text_token_tags']) if isinstance(p.get('text_token_tags'),torch.Tensor) else None,'options_keys':list(transformer_options),'denoise_mask_present':denoise_mask is not None})
 out=orig_forward(self,x,timestep,context,transformer_options,minimax_payload,denoise_mask,audio_denoise_mask,**kwargs)
 save_file({'video':out[0].detach().cpu().contiguous(),'audio':out[1].detach().cpu().contiguous()},str(OUT/(current()+'_first_dit.safetensors')))
 emit('dit_output',{'forward_index':TLS.forwards,'video':tensor(out[0]),'audio':tensor(out[1])})
 name=current();TLS.case=None
 raise RuntimeError('H3_AUDIT_FIRST_FORWARD_CAPTURED:'+name)
mm.MiniMaxH3Model._forward=forward
def receive(body):
 if any(n.get('class_type')=='H3AuditClipMarker' for n in body.get('prompt',{}).values()):
  name=next(n['inputs']['audit_case'] for n in body['prompt'].values() if n.get('class_type')=='H3AuditClipMarker')
  (OUT/(name+'_server_received_post.json')).write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf-8')
 return body
PromptServer.instance.add_on_prompt_handler(receive)
orig_executor=execution.PromptExecutor.execute
def executor(self,*args,**kwargs):
 TLS.case=None
 try:return orig_executor(self,*args,**kwargs)
 finally:TLS.case=None
execution.PromptExecutor.execute=executor
logging.info('[H3 CONDITION AUDIT] registered_v2 observational probe loaded; opt-in marker only')
