"""Opt-in six-UI graph planning. No model lifecycle mutations, no sampling here."""
import copy,inspect,json,os,time,uuid,threading
from contextlib import nullcontext
from pathlib import Path
from . import cache_codec as codec
from . import execution_state
LOCK=threading.RLock()
STATE_LOCK=None
STATIC_CLASSES={'MiniMaxH3ReferenceToVideo','CLIPLoader','VAELoader','Any Switch (rgthree)','ResolutionSelector','PrimitiveFloat','PrimitiveInt','PrimitiveBoolean','PrimitiveStringMultiline','ComfyMathExpression','LoadImageCrop','LoadImage'}
def clean_graph(g):return {str(k):{'class_type':v['class_type'],'inputs':copy.deepcopy(v['inputs'])} for k,v in g.items()}
def link(v,g):return isinstance(v,list) and len(v)==2 and isinstance(v[0],str) and v[0] in g and type(v[1]) is int
def prune(g,roots):
 seen=set();walking=set()
 def walk(k):
  if k in walking:raise ValueError('Graph cycle '+k)
  if k in seen:return
  if k not in g:raise ValueError('Missing node '+k)
  walking.add(k)
  for v in g[k]['inputs'].values():
   if link(v,g):walk(v[0])
  walking.remove(k);seen.add(k)
 for k in roots:walk(k)
 return {k:copy.deepcopy(v) for k,v in g.items() if k in seen}
def token(value):
 if not isinstance(value,str) or not value or len(value)>160 or any(not(c.isalnum()or c in '-_') for c in value):raise ValueError('Invalid group/project identity')
 return value
def scalar(value,g):
 if not link(value,g):return value
 k,slot=value;n=g[k];t=n['class_type'];p=n['inputs']
 if t.startswith('Primitive'):return p['value']
 if t=='Any Switch (rgthree)':return scalar(next(v for _,v in sorted(p.items()) if v is not None),g)
 if t=='ResolutionSelector':
  from comfy_extras.nodes_resolution import ResolutionSelector
  return ResolutionSelector.execute(**p)[slot]
 if t=='ComfyMathExpression':
  from comfy_extras.nodes_math import MathExpressionNode
  vals={name.split('.',1)[1]:scalar(v,g) for name,v in p.items() if name.startswith('values.')}
  return MathExpressionNode.execute(p['expression'],vals)[slot]
 raise ValueError('Unresolved scalar '+t)
def model_record(role,name):
 records=[r for r in codec.MODEL_REGISTRY.values() if r['role']==role and Path(r['path']).name==name]
 if len(records)!=1:raise ValueError('Model outside frozen registry: '+role+'/'+str(name))
 return copy.deepcopy(records[0])
def implementation(cls):
 import nodes
 p=Path(inspect.getfile(nodes.NODE_CLASS_MAPPINGS[cls]));return {'role':'implementation','path':str(p),'sha256':codec.file_sha(p)}
def build_contract(g,text,index,context):
 import folder_paths
 g=clean_graph(g);token(context['project_id']);token(context['group_id'])
 if not 0<=index<6 or not text.strip():raise ValueError('Missing final segment text')
 if g.get('136',{}).get('class_type')!='MiniMaxH3ReferenceToVideo':raise ValueError('Official Node136 missing')
 g['136']['inputs']['prompt']=text
 upstream=prune(g,['136'])
 unknown=sorted({n['class_type'] for n in upstream.values()}-STATIC_CLASSES)
 if unknown:return None,'Node136 runtime/unsupported ancestry: '+','.join(unknown)
 if context.get('dynamic_inputs'):return None,'Explicit runtime Node136 inputs'
 if not any('PDD' in n['class_type'] for n in prune(g,['125']).values()):return None,'Non-PDD branch preserved'
 p=g['136']['inputs'];files=[];refs=[];role_models={}
 for k,n in upstream.items():
  t=n['class_type'];v=n['inputs']
  if t in ('LoadImage','LoadImageCrop'):
   image=v.get('image');
   if not isinstance(image,str) or image.endswith(' [output]') or image.endswith(' [temp]'):return None,'Dynamic/output reference'
   path=Path(folder_paths.get_annotated_filepath(image));root=Path(folder_paths.get_input_directory()).resolve()
   if not path.resolve().is_relative_to(root):return None,'Reference outside fixed input root'
   rec={'role':'reference','path':str(path),'sha256':codec.file_sha(path)};files.append(rec)
   slots=[int(name.rsplit('_',1)[-1]) for name,value in p.items() if name.startswith('ref_images.') and value==[k,0]]
   if not slots:return None,'Indirect image processing unsupported'
   for s in slots:refs.append({'slot':s,'enabled':True,'sha256':rec['sha256'],'crop':v.get('crop',''),'max_megapixels':v.get('max_megapixels')})
  if t=='CLIPLoader':role_models['te']=model_record('te',v['clip_name'])
  if t=='VAELoader':
   role='audio_vae' if 'audio' in v['vae_name'] else 'video_vae';role_models[role]=model_record(role,v['vae_name'])
 files.extend(role_models.values())
 h3=next((n['inputs']['unet_name'] for n in prune(g,['125']).values() if n['class_type']=='UNETLoader'),None);h3=model_record('h3',h3);files.append(h3)
 impls={t:implementation(t) for t in sorted({n['class_type'] for n in upstream.values()}-{'Any Switch (rgthree)'})};files.extend(impls.values())
 # Binding the entire effective upstream graph includes switches, disabled slots and encode parameters.
 c={'schema':codec.SCHEMA,'segment_id':str(index),'group_id':context['group_id'],'story_id':context['group_id'],'final_text_revision':int(context['revisions'][index]),'prompt_sha256':codec.digest(text.encode()),'reference_slots':sorted(refs,key=lambda r:r['slot']),'width':scalar(p['width'],g),'height':scalar(p['height'],g),'frames':scalar(p['length'],g),'fps':scalar(g.get('960',{}).get('inputs',{}).get('fps',context['fps']),g),'h3':h3,'te':role_models['te'],'node136':impls['MiniMaxH3ReferenceToVideo'],'generation_mode':'Ref2VA','ref2va_branch':'INT8_CONVROT_PDD8','conditioning_parameters':{'prompt':text,'effective_node136_graph':upstream,'reference_size':p['ref_image_size'],'static_dynamic_split':'Node136 only; previous AV state applied after real VIDEO_SUCCESS'},'files':files}
 from .user_guides import fingerprint,source_info
 guide=fingerprint(g,index)
 if guide is not None:
  info=source_info(guide['source'],guide['source_sha256'])
  c['user_guide']=guide
  c['files'].append({'role':'user_guide','path':str(Path(folder_paths.get_input_directory())/info['source']),'sha256':info['source_sha256']})
 codec.verified_contract(json.dumps(c));return c,None
def ledger_path(context):
 import folder_paths
 return Path(folder_paths.get_output_directory())/'h3_continuation'/token(context['project_id'])/('prebake_'+token(context['group_id'])+'.json')
def atomic_json(path,data):
 with LOCK,STATE_LOCK or nullcontext():
  path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
  try:
   with tmp.open('wb') as f:f.write(codec.canonical(data));f.flush();os.fsync(f.fileno())
   # Windows external readers (including virus scanners) may briefly deny replace.
   # Retain the same fully flushed temporary file; never expose partial JSON.
   for retry in range(6):
    try:os.replace(tmp,path);break
    except PermissionError:
     if retry==5:raise
     time.sleep(.01*(retry+1))
  finally:tmp.unlink(missing_ok=True)

def read_state(path):
 with LOCK,STATE_LOCK or nullcontext():
  try:
   for retry in range(6):
    try:raw=path.read_text(encoding='utf-8');break
    except PermissionError:
     if retry==5:raise
     time.sleep(.01*(retry+1))
   data=json.loads(raw)
  except FileNotFoundError:return None
  except (json.JSONDecodeError,UnicodeError) as ex:raise ValueError('CORRUPT state: '+str(path)) from ex
  if not isinstance(data,dict):raise ValueError('CORRUPT state object: '+str(path))
  return data

def story_registry():
 import folder_paths
 return Path(folder_paths.get_output_directory())/'h3_continuation'/'_prebake_stories.json'

def story(payload,state_lock=None):
 import folder_paths
 sid=token(payload['story_id']);action=payload.get('action','restore')
 with LOCK, state_lock or nullcontext():
  registry=read_state(story_registry()) or {};binding=registry.get(sid)
  if action=='restore':binding=execution_state.selected_story(sid)
  if action=='restore':
   if not binding:return {'state':'UNINITIALIZED','binding':None}
   data=read_state(ledger_path(binding))
   if not data or not data.get('execution'):raise ValueError('MISSING story execution ledger; no directory fallback')
   if data['execution']!=binding:
    current=data['execution']
    if any(current.get(k)!=binding[k] for k in ('story_id','project_id','group_id')):raise ValueError('Inconsistent story identity; no directory fallback')
    # The known group ledger is the durable execution owner. A stop between
    # ledger and registry writes may leave only routing metadata one write behind.
    binding=current;registry[sid]=binding;atomic_json(story_registry(),registry)
   receipts=read_state(ledger_path(binding).parent/'six_acceptance.json')
   receipt_state='MISSING' if receipts is None and any(s.get('attempt') or s.get('video_status')=='SUCCESS' for s in data['segments'].values()) else ('UNINITIALIZED' if receipts is None else 'PRESENT')
   # Frontend recovery reads this exact bound ledger, never latest files.
   segments={k:{'video_status':v.get('video_status'),'revision':v.get('revision'),'cache_key':v.get('cache_key'),'attempt':v.get('attempt'),'inherited_attempt':v.get('inherited_attempt'),'receipt':(receipts or {}).get(k)} for k,v in data['segments'].items()}
   for segment in segments.values():
    receipt=segment.get('receipt') or {}
    if segment.get('video_status')=='SUCCESS' and receipt.get('video_output_ref'):
     video=Path(receipt['video_path']).resolve()
     if not video.is_relative_to(Path(folder_paths.get_output_directory()).resolve()) or not video.is_file() or codec.file_sha(video)!=receipt['video_sha256']:
      segment.update(video_status='UNAVAILABLE',recovery_error='Accepted video missing or SHA256 changed')
   from .adaptive_bridge import recovery
   from server import PromptServer
   for key,segment in segments.items():
    ledger_entry=data['segments'][key]
    if ledger_entry.get('inherited_from') and ledger_entry.get('video_status')=='SUCCESS' and (receipts or {}).get(key,{}).get('status')=='SUCCESS':
     segment['adaptive_recovery']=None
     continue
    try:segment['adaptive_recovery']=recovery(binding,int(key),ledger_entry,PromptServer.instance)
    except Exception as ex:segment['adaptive_recovery_error']=str(ex)
   return {'state':'BOUND','receipt_state':receipt_state,'binding':binding,'segments':segments}
  if action!='bind':raise ValueError('Unknown story action')
  gid=token(payload['group_id']);requested=token(payload['project_id']);requested_settings=(read_state(ledger_path({'project_id':requested,'group_id':gid}).parent/'six_acceptance.json') or {}).get('_native_merge',{}).get('auto_merge_enabled',True);first=int(payload['start_index']);mode=payload['start_mode']
  if not 0<=first<6 or mode not in ('resume','independent'):raise ValueError('Invalid start policy')
  if binding:
   if gid!=binding['group_id'] or requested!=binding['project_id']:raise ValueError('Story group/project changed; refusing silent directory switch')
   if payload.get('execution_version')!=binding['execution_version']:raise ValueError('Story execution version changed; reload required')
   path=ledger_path(binding);data=read_state(path)
   if not data or data.get('execution')!=binding:raise ValueError('MISSING story ledger')
   if (first,mode)!=(binding['start_index'],binding['start_mode']):
    if any(s.get('attempt',{}).get('status') in ('PREPARED','PENDING','CANCELLING','BLOCKED') for s in data['segments'].values()):raise ValueError('Cannot change start policy during a pending execution')
    binding,data=execution_state.fork(binding,data,state_lock)
    binding={**binding,'start_index':first,'start_mode':mode};path=ledger_path(binding)
  else:
   # Adopt only the explicitly named existing project/group; never scan output.
   if payload.get('previous_story_id'):
    previous=registry.get(payload['previous_story_id'])
    previous_data=read_state(ledger_path(previous)) if previous else None
    if previous_data and any(s.get('attempt',{}).get('status') in ('PREPARED','PENDING','CANCELLING','BLOCKED') for s in previous_data['segments'].values()):raise ValueError('Cannot switch stories during pending execution')
   context={'project_id':requested,'group_id':gid};path=ledger_path(context);data=read_state(path)
   receipt_path=path.parent/'six_acceptance.json';receipts=read_state(receipt_path)
   active=(receipts or {}).get('_native_merge',{}).get('active_group_id')
   if not data and (active!=gid or not receipts):
    context['project_id']=gid;path=ledger_path(context);data=read_state(path);receipts=read_state(path.parent/'six_acceptance.json');requested=gid
    active=(receipts or {}).get('_native_merge',{}).get('active_group_id')
   if active and active!=gid:raise ValueError('Project belongs to another story group')
   if any(b['story_id']!=sid and b['project_id']==requested for b in registry.values()):raise ValueError('Project already bound to another story identity')
   if data and (data.get('group_id')!=gid or data.get('project_id',requested)!=requested):raise ValueError('Existing story ledger identity mismatch')
   if not data and first>0 and mode=='resume':raise ValueError('No legal predecessor in requested story; initialization cannot authorize resume')
   data=data or {'project_id':requested,'group_id':gid,'segments':{}}
   existing=data.get('execution')
   if not existing:
    known=[b for b in execution_state.bindings() if b['story_id']==sid and b['project_id']==requested and b['group_id']==gid]
    if len(known)==1:existing=known[0]
   if existing and existing.get('story_id')!=sid:raise ValueError('Existing execution belongs to another story')
   binding=existing or {'story_id':sid,'project_id':requested,'group_id':gid,'start_index':first,'start_mode':mode,'execution_version':uuid.uuid4().hex,'auto_merge_enabled':requested_settings,'revisions':[int(data['segments'].get(str(i),{}).get('revision',0)) for i in range(6)],'cache_keys':[data['segments'].get(str(i),{}).get('cache_key') for i in range(6)]}
  data['execution']=binding;atomic_json(path,data)
  execution_state.select(binding)
  registry[sid]=binding;atomic_json(story_registry(),registry)
  return {'state':'BOUND','binding':binding}

def bound_context(ctx):
 with LOCK,STATE_LOCK or nullcontext():
  matches=[b for b in execution_state.bindings() if b.get('story_id')==ctx.get('story_id') and b.get('execution_version')==ctx.get('execution_version')]
  binding=matches[0] if len(matches)==1 else None
  if not binding or any(ctx.get(k)!=binding[k] for k in ('project_id','group_id','execution_version')):raise ValueError('Story identity/execution version mismatch')
  data=read_state(ledger_path(binding))
  if not data or data.get('execution')!=binding:raise ValueError('MISSING or inconsistent execution binding')
  return binding,data

def invalidate_texts(payload,state_lock=None):
 with LOCK, state_lock or nullcontext():
  binding,data=bound_context(payload['context']);texts=payload['texts']
  if len(texts)!=6:raise ValueError('Expected six final texts')
  changed=[]
  for i,text in enumerate(texts):
   entry=data['segments'].get(str(i),{});wanted=codec.digest(text.encode())
   if entry.get('final_prompt_sha256') and entry['final_prompt_sha256']!=wanted:
    changed.append(i);entry['revision']=int(entry.get('revision',0))+1;entry['final_prompt_sha256']=wanted
    binding['revisions'][i]=entry['revision']
  if changed:invalidate_video_chain(ledger_path(binding),data,binding,min(changed),state_lock)
  data['execution']=binding;atomic_json(ledger_path(binding),data)
  registry=read_state(story_registry()) or {};registry[binding['story_id']]=binding;atomic_json(story_registry(),registry)
  return {'binding':binding,'invalidated_video_from':min(changed) if changed else None}

def attempt_check(ctx,index,data,attempt):
 binding,_=bound_context(ctx);entry=data['segments'].get(str(index),{})
 expected={'project_id':binding['project_id'],'group_id':binding['group_id'],'execution_version':binding['execution_version'],'revision':entry.get('revision'),'cache_key':entry.get('cache_key')}
 if not attempt or any(attempt.get(k)!=v for k,v in expected.items()) or attempt.get('status') not in ('PREPARED','PENDING','SUCCESS'):raise ValueError('STALE attempt group/project/version/revision/cache_key')
 return entry

def mark_pending(project,index,group_id,state_lock=None):
 ctx={'project_id':project,'group_id':group_id};path=ledger_path(ctx)
 with LOCK, state_lock or nullcontext():
  data=read_state(path)
  if not data or not data.get('execution'):raise ValueError('UNINITIALIZED PreBake execution')
  ctx=data['execution'];entry=data['segments'].get(str(index),{});attempt=entry.get('attempt',{})
  attempt_check(ctx,index,data,attempt)
  if attempt['status']=='SUCCESS':return {'status':'SUCCESS','segment_index':index}
  receipt_path=path.parent/'six_acceptance.json';receipts=read_state(receipt_path)
  if receipts is None:raise ValueError('MISSING receipt after generation preparation')
  r=receipts.get(str(index),{})
  if r.get('attempt_id')!=attempt['attempt_id'] or r.get('status')!='PENDING':raise ValueError('PENDING receipt changed; refusing overwrite')
  attempt['status']='PENDING';atomic_json(path,data)
  return {'status':'PENDING','segment_index':index}

def claim_prompt(execution_json,prompt_id,state_lock=None):
 if not isinstance(prompt_id,str) or not prompt_id:raise ValueError('Missing server execution prompt_id')
 claim=json.loads(execution_json);ctx=claim['context'];i=int(claim['index'])
 with LOCK, state_lock or nullcontext():
  _,data=bound_context(ctx);entry=data['segments'].get(str(i),{});attempt=entry.get('attempt',{})
  attempt_check(ctx,i,data,attempt)
  if claim['attempt_id']!=attempt.get('attempt_id') or attempt['status']!='PENDING':raise ValueError('STALE or unsubmitted attempt before sampling')
  if attempt.get('prompt_id') not in (None,prompt_id):raise ValueError('Attempt already bound to another prompt_id')
  attempt['prompt_id']=prompt_id;path=ledger_path(ctx);receipts=read_state(path.parent/'six_acceptance.json')
  if receipts is None or receipts.get(str(i),{}).get('attempt_id')!=attempt['attempt_id']:raise ValueError('MISSING or changed pending receipt before sampling')
  atomic_json(path,data);receipts[str(i)].update(prompt_id=prompt_id);atomic_json(path.parent/'six_acceptance.json',receipts)

def invalidate_video_chain(path,ledger,ctx,first,state_lock=None):
 invalidated_prompts={};affected=[]
 for j in range(first,6):
  entry=ledger['segments'].get(str(j),{})
  if j>first and 'predecessor_index' in entry and entry['predecessor_index'] is None:break
  affected.append(j);invalidated_prompts[str(j)]=entry.get('prompt_id')
  entry['video_status']='STALE';entry['invalidated_at_epoch']=time.time();entry['invalidated_reason']='CACHE_CONTRACT_CHANGED'
  if entry.get('attempt'):entry['attempt']['status']='STALE'
  for field in ('prompt_id','latent_sha256'):entry.pop(field,None)
 receipt_path=path.parent/'six_acceptance.json'
 def update():
  receipts=read_state(receipt_path)
  if receipts is None:return
  group=receipts.get('_native_merge',{}).get('groups',{}).get(ctx['group_id'])
  for j in affected:
   receipt=receipts.get(str(j),{});old_prompt=invalidated_prompts.get(str(j))
   if receipt and (receipt.get('group_id')==ctx['group_id'] or (old_prompt and receipt.get('prompt_id')==old_prompt)):
    receipt['invalidated_prompt_id']=receipt.get('prompt_id');receipt.pop('prompt_id',None)
    receipt.update(status='STALE',invalidated_at_epoch=time.time(),invalidated_reason='CACHE_CONTRACT_CHANGED')
  if group:
   for j in affected:group.get('prompt_ids',{}).pop(str(j),None)
   group.update(merge_prompt_id=None,merge_output=None,merge_status='WAITING_6_OF_6' if group.get('eligible') else 'DISABLED')
  atomic_json(receipt_path,receipts)
 if state_lock:
  with state_lock:update()
 else:update()

def verify_predecessor(ctx,index):
 import folder_paths
 prior=index-1;root=Path(folder_paths.get_output_directory())/'h3_continuation'/ctx['project_id']
 path=root/('seg_%05d.safetensors'%prior);receipts=read_state(root/'six_acceptance.json')
 if receipts is None:raise ValueError('MISSING predecessor receipt: '+str(root/'six_acceptance.json'))
 receipt=receipts.get(str(prior),{})
 ledger_path=root/('prebake_'+token(ctx['group_id'])+'.json');ledger=read_state(ledger_path) or {}
 accepted=ledger.get('segments',{}).get(str(prior),{});file_exists=path.is_file();actual_sha=codec.file_sha(path) if file_exists else None
 legacy_group_proven=ledger.get('group_id')==ctx['group_id'] and receipt.get('prompt_id') is not None and receipts.get('_native_merge',{}).get('groups',{}).get(ctx['group_id'],{}).get('prompt_ids',{}).get(str(prior))==receipt.get('prompt_id')==accepted.get('prompt_id')
 latent_prompt=None
 if file_exists:
  from safetensors import safe_open
  with safe_open(str(path),framework='pt',device='cpu') as handle:latent_prompt=handle.metadata().get('prompt_id')
 checks={'VIDEO_STATUS_CHECK':{'expected':'SUCCESS','actual':accepted.get('video_status')},
         'PROMPT_ID_CHECK':{'expected':receipt.get('prompt_id'),'actual':accepted.get('prompt_id')},
         'LATENT_SHA256_CHECK':{'expected':accepted.get('latent_sha256'),'actual':actual_sha},
         'RECEIPT_LATENT_SHA256_CHECK':{'expected':receipt.get('latent_sha256',accepted.get('latent_sha256')),'actual':actual_sha},
         'LATENT_PROMPT_ID_CHECK':{'expected':accepted.get('prompt_id'),'actual':latent_prompt},
         'GROUP_ID_CHECK':{'expected':ctx['group_id'],'actual':accepted.get('group_id') or (ctx['group_id'] if legacy_group_proven else None)},
         'RECEIPT_GROUP_CHECK':{'expected':ctx['group_id'],'actual':receipt.get('group_id') or (ctx['group_id'] if legacy_group_proven else None)}}
 for item in checks.values():item['result']='PASS' if item['expected'] is not None and item['expected']==item['actual'] else 'FAIL'
 if receipt.get('status')!='SUCCESS' or ledger.get('group_id')!=ctx['group_id'] or any(item['result']!='PASS' for item in checks.values()):
  raise ValueError('PreBake predecessor eligibility denied: '+json.dumps({'project_id':ctx['project_id'],'group_id':ctx['group_id'],'segment_index':prior,'latent_path':str(path),'latent_exists':file_exists,'latent_sha256':actual_sha,'receipt':receipt,'checks':checks},ensure_ascii=False,separators=(',',':')))
def fallback_conditioning_key(graph,text,index,ctx):
 # Match the final text override used by executeVisiblePrompt. Only Node136's
 # effective upstream conditioning inputs belong in this identity; current
 # sampler/continuation segment fields cannot invalidate an accepted predecessor.
 g=clean_graph(graph)
 if '138' in g and g['138']['class_type']=='PrimitiveStringMultiline':
  g['138']['inputs']['value']=text;g['136']['inputs']['prompt']=['138',0]
 else:g['136']['inputs']['prompt']=text
 value={'route':'DYNAMIC_FALLBACK','text':text,'revision':ctx['revisions'][index],'group_id':ctx['group_id'],'fps':ctx.get('fps',24),'conditioning_graph':prune(g,['136'])}
 from .user_guides import fingerprint
 guide=fingerprint(g,index)
 if guide is not None:value['user_guide']=guide
 return codec.digest(codec.canonical(value))

def reject_first_frame_guides(conditioning):
 if not isinstance(conditioning,(list,tuple)) or not conditioning:raise ValueError('Guide conditioning cannot be inspected')
 for item in conditioning:
  if not isinstance(item,(list,tuple)) or len(item)!=2 or not isinstance(item[1],dict):raise ValueError('Malformed Guide conditioning')
  for keyframe in item[1].get('minimax_keyframes',[]):
   position=keyframe.get('resolved_frame_index')
   if type(position) is not int or position<0:raise ValueError('Unresolved existing Guide position')
   if position==0:raise ValueError('Existing first-frame Guide conflicts with Rebase composition anchor; preserve references and refuse submission')

def check_guide_ancestry(graph):
 explicit_first=False
 root=graph['126']['inputs']['conditioning']
 if not link(root,graph):raise ValueError('Unresolved Guide conditioning graph')
 if 'PREBAKE_LOAD' in graph:length=json.loads(graph['PREBAKE_LOAD']['inputs']['contract_json']).get('frames')
 else:length=scalar(graph.get('136',{}).get('inputs',{}).get('length'),graph)
 frames=None
 if type(length) is int and length>0:
  frames=max(5,length)
  while frames%17!=5:frames+=1
 for key,node in prune(graph,[root[0]]).items():
  p=node['inputs'];kind=node['class_type']
  if kind=='MiniMaxH3AddGuide':
   position=scalar(p.get('frame_idx'),graph)
   if type(position) is not int:raise ValueError('Unresolved existing Guide position before submission')
   # Official negative-index semantics; preserve legal end/other-time anchors.
   if position<0:
    if frames is None:raise ValueError('Relative Guide target duration cannot be resolved before submission')
    position+=frames
   if position==0:explicit_first=True
   if position<0 or (frames is not None and position>=frames):raise ValueError('Existing Guide outside effective target duration')
  if kind=='MiniMaxH3ImageToVideo' and p.get('first_frame') is not None:explicit_first=True
 return explicit_first

def validate_guide_runtime(conditioning,latent,policy_json,image,prompt_id):
 # Called by the existing audit node both before and after the official AddGuide.
 # No model loads, no alternate Guide implementation, no mutation of conditioning.
 import folder_paths
 policy=json.loads(policy_json);ctx=policy['context'];index=policy['index']
 with LOCK,STATE_LOCK or nullcontext():
  binding,data=bound_context(ctx);entry=data['segments'].get(str(index),{})
  if any(entry.get(k)!=policy[k] for k in ('revision','cache_key')):raise ValueError('STALE Guide cache/revision')
  attempt=entry.get('attempt',{});attempt_check(ctx,index,data,attempt)
  if attempt.get('attempt_id')!=policy['attempt_id']:raise ValueError('STALE Guide attempt')
  if not prompt_id or attempt.get('prompt_id')!=prompt_id:raise ValueError('Guide executing prompt_id mismatch')
  if attempt.get('guide_anchor_sha256')!=guide_policy_digest(policy):raise ValueError('Guide policy differs from committed attempt')
  verify_predecessor(ctx,index)
  receipt=(read_state(ledger_path(ctx).parent/'six_acceptance.json') or {}).get(str(index-1),{})
  if any(receipt.get(k)!=policy['source'][k] for k in ('prompt_id','video_sha256','latent_sha256')):raise ValueError('Guide predecessor changed before sampling')
  path=(Path(folder_paths.get_input_directory())/policy['image']).resolve()
  if not path.is_relative_to(Path(folder_paths.get_input_directory()).resolve()) or not path.is_file() or codec.file_sha(path)!=policy['image_sha256']:raise ValueError('Guide source image changed before sampling')
  if image is None or list(image.shape)!=policy['image_shape'] or codec.digest(image.detach().cpu().contiguous().numpy().tobytes())!=policy['pixel_sha256']:raise ValueError('Actual Guide image fingerprint mismatch')
  video=latent['samples'].unbind()[0]
  if (video.shape[-1]*16,video.shape[-2]*16)!=(policy['width'],policy['height']):raise ValueError('Actual Guide latent canvas mismatch')
  target=policy.get('frame_idx',0)
  latent_t=video.shape[2]
  if latent_t<2 or (latent_t-2)%5:raise ValueError('Actual H3 video latent temporal shape is invalid')
  model_frames=5+17*((latent_t-2)//5)
  if type(target) is not int or target<0 or target>=model_frames:raise ValueError('Guide target is outside actual model duration')
  if policy['stage']=='before':
   for item in conditioning:
    for keyframe in item[1].get('minimax_keyframes',[]):
     position=keyframe.get('resolved_frame_index')
     if type(position) is not int or position<0:raise ValueError('Unresolved existing Guide position')
     if position==target:raise ValueError('Existing Guide conflicts with Rebase composition anchor')
  elif policy['stage']=='after':
   for item in conditioning:
    keyframes=item[1].get('minimax_keyframes',[]);anchored=[k for k in keyframes if k.get('resolved_frame_index')==target]
    if len(anchored)!=1 or 'latent' not in anchored[0]:raise ValueError('Official Guide must produce exactly one image keyframe at the saved-frame anchor')
    v=anchored[0]['latent']
    if tuple(v.shape)!=(video.shape[0],24,1,video.shape[-2],video.shape[-1]):raise ValueError('Official Guide latent shape mismatch')
  else:raise ValueError('Unknown Guide audit stage')
 return {'stage':policy['stage'],'source_prompt_id':policy['source']['prompt_id'],'pixel_sha256':policy['pixel_sha256'],'frame_idx':policy.get('frame_idx',0),'actual_image_shape':list(image.shape),'actual_latent_shape':list(video.shape),'duplicate_check':'PASS'}

def guide_policy_digest(policy):return codec.digest(codec.canonical({k:v for k,v in policy.items() if k!='stage'}))

def anchor_clean_rebase(graph,ctx,index,enabled=False,attempt_id=None,cached_conditioning=None):
 # A fresh epoch resets motion, but must not invent a new camera composition.
 # Keep this dynamic guide outside the static Node136 conditioning cache.
 if not enabled:return graph
 prep=next((n['inputs'] for n in graph.values() if n['class_type']=='H3ContinuationPrepare'),{})
 rebase=prep.get('enabled') is True and prep.get('clean_rebase_enabled') is True and index==prep.get('clean_rebase_segment')
 independent=ctx.get('start_mode')=='independent' and index==ctx.get('start_index')
 if not rebase or independent:return graph
 if index<=0:raise ValueError('Rebase composition anchor needs a predecessor')
 if any(k in graph for k in ('SEAM_GUIDE','SEAM_PRECHECK','SEAM_AUDIT','SEAM_IMAGE')):raise ValueError('Repeated automatic Guide injection; prepare a fresh graph')
 # Anchor the first frame that will survive the explicit rebase output crop.
 anchor_frame_idx=scalar(graph.get('LONG_SONG',{}).get('inputs',{}).get('clean_rebase_output_discard_frames',0),graph)
 if type(anchor_frame_idx) is not int or anchor_frame_idx<0:raise ValueError('Invalid Clean Rebase output discard target')
 if check_guide_ancestry(graph):raise ValueError('Existing Guide conflicts with requested Clean Rebase output anchor')
 length=scalar(graph.get('136',{}).get('inputs',{}).get('length'),graph)
 if type(length) is not int or anchor_frame_idx>=length:raise ValueError('Clean Rebase Guide anchor outside model duration')
 if 'PREBAKE_LOAD' in graph:
  if cached_conditioning is None:
   cached,_,_=codec.load(graph['PREBAKE_LOAD']['inputs']['contract_json'],restore_device=False)
   explicit_first=any(k.get('resolved_frame_index')==0 for item in cached['conditioning'] for k in item[1].get('minimax_keyframes',[]));del cached
   if explicit_first:return graph
  elif any(k.get('resolved_frame_index')==0 for item in cached_conditioning for k in item[1].get('minimax_keyframes',[])):return graph
 import folder_paths,subprocess,tempfile
 verify_predecessor(ctx,index)
 receipt=(read_state(ledger_path(ctx).parent/'six_acceptance.json') or {}).get(str(index-1),{})
 output=Path(folder_paths.get_output_directory()).resolve();video=Path(receipt.get('video_path','')).resolve()
 if not video.is_relative_to(output) or not video.is_file() or not receipt.get('video_sha256') or codec.file_sha(video)!=receipt['video_sha256']:raise ValueError('Rebase accepted predecessor video missing or SHA256 changed')
 info=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=nb_frames,width,height','-of','json',str(video)],capture_output=True,text=True,timeout=15,check=True)
 stream=json.loads(info.stdout)['streams'][0];last=int(stream['nb_frames'])-1
 if last<0:raise ValueError('Rebase predecessor has no video frames')
 if 'PREBAKE_LOAD' in graph:
  contract=json.loads(graph['PREBAKE_LOAD']['inputs']['contract_json'])
  if (stream['width'],stream['height'])!=(contract['width'],contract['height']):raise ValueError('Rebase composition dimensions changed; no automatic crop')
 else:
  target=graph.get('136',{}).get('inputs',{})
  if (stream['width'],stream['height'])!=(scalar(target.get('width'),graph),scalar(target.get('height'),graph)):raise ValueError('Fallback Rebase composition dimensions changed; no automatic crop')
 vae=graph.get('122',{}).get('inputs',{}).get('vae')
 if not vae:raise ValueError('Rebase composition anchor has no official video VAE')
 folder=Path(folder_paths.get_input_directory())/'h3_rebase_composition';folder.mkdir(parents=True,exist_ok=True)
 image=folder/(receipt['prompt_id']+'_'+receipt['video_sha256'][:16]+'.png')
 fd,name=tempfile.mkstemp(prefix='.anchor-',suffix='.png',dir=folder);os.close(fd)
 try:
  subprocess.run(['ffmpeg','-y','-v','error','-i',str(video),'-vf','select=eq(n\\,%d)'%last,'-frames:v','1',name],capture_output=True,timeout=20,check=True)
  if codec.file_sha(video)!=receipt['video_sha256']:raise ValueError('Rebase predecessor changed during frame extraction')
  verify_predecessor(ctx,index)
  current=(read_state(ledger_path(ctx).parent/'six_acceptance.json') or {}).get(str(index-1),{})
  if any(current.get(k)!=receipt.get(k) for k in ('prompt_id','video_sha256','latent_sha256')):raise ValueError('Rebase predecessor changed during frame extraction')
  os.replace(name,image)
 finally:
  if os.path.exists(name):os.unlink(name)
 graph['SEAM_IMAGE']={'class_type':'LoadImage','inputs':{'image':'h3_rebase_composition/'+image.name}}
 import numpy as np
 from PIL import Image
 with Image.open(image) as img:pixels=(np.array(img.convert('RGB')).astype(np.float32)/255.0)[None]
 policy={'context':copy.deepcopy(ctx),'index':index,'attempt_id':attempt_id,'revision':ctx['revisions'][index],'cache_key':ctx['cache_keys'][index],'source':{k:receipt[k] for k in ('prompt_id','video_sha256','latent_sha256')},'source_frame':last,'image':graph['SEAM_IMAGE']['inputs']['image'],'image_sha256':codec.file_sha(image),'pixel_sha256':codec.digest(pixels.tobytes()),'image_shape':list(pixels.shape),'width':stream['width'],'height':stream['height'],'frame_idx':anchor_frame_idx}
 prepare=next(k for k,n in graph.items() if n['class_type']=='H3ContinuationPrepare')
 plan=copy.deepcopy(graph.get('PREBAKE_AUDIT',{}).get('inputs',{}).get('plan_json',[prepare,1]))
 common={'latent':copy.deepcopy(graph['125']['inputs']['latent_image']),'project_id':ctx['project_id'],'segment_index':index,'plan_json':plan,'guide_image':['SEAM_IMAGE',0]}
 graph['SEAM_PRECHECK']={'class_type':'H3PreBakeContinuationAudit','inputs':{**copy.deepcopy(common),'conditioning':copy.deepcopy(graph['126']['inputs']['conditioning']),'guide_guard_json':json.dumps({**policy,'stage':'before'})}}
 graph['SEAM_GUIDE']={'class_type':'MiniMaxH3AddGuide','inputs':{'positive':['SEAM_PRECHECK',0],'latent':['SEAM_PRECHECK',1],'frame_idx':anchor_frame_idx,'vae':copy.deepcopy(vae),'image':['SEAM_IMAGE',0]}}
 graph['SEAM_AUDIT']={'class_type':'H3PreBakeContinuationAudit','inputs':{**copy.deepcopy(common),'conditioning':['SEAM_GUIDE',0],'guide_guard_json':json.dumps({**policy,'stage':'after'})}}
 graph['126']['inputs']['conditioning']=['SEAM_AUDIT',0]
 return graph

def plan(payload,state_lock=None):
 g=payload['graph'];ctx=payload['context'];texts=payload['texts'];assert len(texts)==len(ctx['revisions'])==6
 if len(g)>400:raise ValueError('Graph too large')
 plans=[];invalidated=[]
 with LOCK, state_lock or nullcontext():
  binding,ledger=bound_context(ctx);path=ledger_path(ctx)
  for i,text in enumerate(texts):
   if 'requested_index' in payload and i != int(payload['requested_index']):
    # Unsubmitted editors are drafts, not retrospective execution inputs.
    # Preserve the exact selected output and its original conditioning contract.
    old=ledger['segments'].get(str(i),{})
    plans.append({'index':i,'status':'SNAPSHOT_PRESERVED' if old else 'DRAFT',
                  'cache_key':old.get('cache_key'),
                  'draft_differs':old.get('final_prompt_sha256')!=codec.digest(text.encode())})
    continue
   if not text.strip():
    old=ledger['segments'].get(str(i),{})
    if old.get('final_prompt_sha256'):invalidated.append(i)
    plans.append({'index':i,'status':'ERROR','reason':'Final prompt empty'});continue
   c,reason=build_contract(g,text,i,ctx)
   if c is None:
    old=ledger['segments'].get(str(i),{});fingerprint=fallback_conditioning_key(g,text,i,ctx);key=fingerprint
    if old.get('conditioning_status')=='DYNAMIC_FALLBACK' and old.get('video_status')=='SUCCESS' and not old.get('fallback_conditioning_key') and old.get('revision')==ctx['revisions'][i] and old.get('final_prompt_sha256')==codec.digest(text.encode()):
     # Adopt a legacy fingerprint only from that exact successful history.
     # Missing volatile history blocks migration without invalidating old assets.
     from server import PromptServer
     prior=PromptServer.instance.prompt_queue.get_history(prompt_id=old['prompt_id']).get(old['prompt_id'])
     if not prior or prior.get('status',{}).get('completed') is not True or prior['status'].get('status_str')!='success':raise ValueError('Legacy fallback history missing; cannot prove conditioning migration')
     if fallback_conditioning_key(prior['prompt'][2],text,i,ctx)==fingerprint:key=old['cache_key']
    elif old.get('fallback_conditioning_key')==fingerprint:key=old['cache_key']
    if old.get('cache_key') and old['cache_key']!=key:invalidated.append(i)
    ledger['segments'][str(i)]={**old,'group_id':ctx['group_id'],'project_id':ctx['project_id'],'cache_key':key,'fallback_conditioning_key':fingerprint,'revision':ctx['revisions'][i],'final_prompt_sha256':codec.digest(text.encode()),'conditioning_status':'DYNAMIC_FALLBACK'}
    plans.append({'index':i,'status':'DYNAMIC_FALLBACK','reason':reason,'cache_key':key});continue
   ct=json.dumps(c,ensure_ascii=False);_,key=codec.verified_contract(ct);folder=codec.ROOT/key;status='STATIC_ELIGIBLE';cache_error=None
   if folder.exists():
    try:
     output,meta,manifest=codec.load(ct,restore_device=False);del output
     status='CACHE_HIT'
    except Exception as ex:
     cache_error=str(ex);quarantine=codec.ROOT/('.quarantine-'+key+'-'+uuid.uuid4().hex);os.rename(folder,quarantine);status='CACHE_STALE'
   old=ledger['segments'].get(str(i),{})
   if old.get('cache_key') and old['cache_key']!=key:invalidated.append(i)
   if int(ctx['revisions'][i])<int(old.get('revision',0)):raise ValueError('STALE final text revision')
   ledger['segments'][str(i)]={**old,'group_id':ctx['group_id'],'project_id':ctx['project_id'],'cache_key':key,'revision':ctx['revisions'][i],'final_prompt_sha256':c['prompt_sha256'],'conditioning_status':status,'contract':c,'cache_error':cache_error}
   bake=clean_graph(g);bake['136']['inputs']['prompt']=text
   bake['PREBAKE_BAKE']={'class_type':'H3ConditioningBake','inputs':{'conditioning':['136',0],'latent':['136',1],'contract_json':ct,'require_te_released':False}}
   plans.append({'index':i,'status':status,'contract_json':ct,'cache_key':key,'bake_graph':prune(bake,['PREBAKE_BAKE'])})
  if invalidated:
   for changed in invalidated:invalidate_video_chain(path,ledger,ctx,changed,state_lock)
  atomic_json(path,ledger)
  binding['revisions']=list(ctx['revisions']);binding['cache_keys']=[ledger['segments'].get(str(i),{}).get('cache_key') for i in range(6)]
  ledger['execution']=binding;atomic_json(path,ledger)
  execution_state.remember(binding)
  registry=read_state(story_registry()) or {}
  if registry.get(binding['story_id'],{}).get('execution_version')==binding['execution_version']:
   registry[binding['story_id']]=binding;atomic_json(story_registry(),registry)
 if payload.get('require_predecessor') is True and int(payload['requested_index'])>0:
  verify_predecessor(ctx,int(payload['requested_index']))
 return {'invalidated_video_from':min(invalidated) if invalidated else None,'plans':plans,'group_id':ctx['group_id'],'project_id':ctx['project_id'],'binding':binding}
def generate(payload,state_lock=None):
 g=clean_graph(payload['graph']);ctx=payload['context'];i=int(payload['index']);ct=payload['contract_json'];c,key=codec.verified_contract(ct)
 if g.get('LONG_SONG',{}).get('inputs',{}).get('cross_group_json'):raise ValueError('跨组仅允许现有长歌动态参考链，禁止绕过受控Fallback提交')
 if c['group_id']!=ctx['group_id'] or c['segment_id']!=str(i) or c['prompt_sha256']!=codec.digest(payload['text'].encode()):raise ValueError('Final text/group mismatch')
 cached,_,_=codec.load(ct,restore_device=False) # complete content validation before Generate; never old cache fallback
 cached_guides=None
 if payload.get('anchor_clean_rebase') is True:
  # Keep only primitive positions. Do not retain/reload the large conditioning tensors.
  cached_guides=[[None,{'minimax_keyframes':[{'resolved_frame_index':k.get('resolved_frame_index')} for k in item[1].get('minimax_keyframes',[])]}] for item in cached['conditioning']]
 del cached
 with LOCK, state_lock or nullcontext():
  binding,data=bound_context(ctx);entry=data['segments'].get(str(i),{})
  if entry.get('cache_key')!=key or entry.get('revision')!=c['final_text_revision']:raise ValueError('STALE generation cache/revision')
  independent=binding['start_mode']=='independent' and i==binding['start_index']
  if i<binding['start_index']:raise ValueError('Segment precedes selected start')
  if entry.get('attempt',{}).get('status') in ('PREPARED','PENDING','CANCELLING','BLOCKED'):raise ValueError('Segment already has an active attempt')
  prep_input=next(n['inputs'] for n in g.values() if n['class_type']=='H3ContinuationPrepare')
  if (prep_input.get('enabled') is True)!=(i>0 and not independent):raise ValueError('Native inheritance does not match bound start policy')
  rebase=prep_input.get('enabled') is True and prep_input.get('clean_rebase_enabled') is True and i==prep_input.get('clean_rebase_segment')
  if i>0 and not independent and not rebase:verify_predecessor(ctx,i)
  attempt={'attempt_id':uuid.uuid4().hex,'project_id':ctx['project_id'],'group_id':ctx['group_id'],'execution_version':ctx['execution_version'],'revision':entry['revision'],'cache_key':key,'status':'PREPARED','prepared_at_epoch':time.time(),'prompt_id':None}
  attempt['snapshot']={'text':payload['text'],'context':copy.deepcopy(ctx),'predecessor_index':i-1 if i>0 and not independent and not (prep_input.get('clean_rebase_enabled') is True and i==prep_input.get('clean_rebase_segment')) else None}
  claim={'context':ctx,'index':i,'attempt_id':attempt['attempt_id']}
 if payload.get('require_predecessor') is True and i>0:verify_predecessor(ctx,i)
 g['PREBAKE_LOAD']={'class_type':'H3ConditioningLoad','inputs':{'contract_json':ct,'execution_json':json.dumps(claim)}}
 for n in g.values():
  for name,value in list(n['inputs'].items()):
   if value==['136',0]:n['inputs'][name]=['PREBAKE_LOAD',0]
   elif value==['136',1]:n['inputs'][name]=['PREBAKE_LOAD',1]
 # Existing TE unload would be a redundant zero-target check. Preserve all runtime Guides; bypass its passthrough only here.
 te=g['1057']['inputs']['conditioning']
 for n in g.values():
  for name,value in list(n['inputs'].items()):
   if value==['1057',0]:n['inputs'][name]=copy.deepcopy(te)
 prepare=next((k for k,n in g.items() if n['class_type']=='H3ContinuationPrepare'),None)
 guides=next((k for k,n in g.items() if n['class_type']=='H3ContinuationGuides'),None)
 saves=[k for k,n in g.items() if n['class_type']=='H3ContinuationSave'];assert len(saves)==1
 save=saves[0];assert g[save]['inputs'].get('enabled') is True
 g[save]['inputs']['latent']=['1058',0]
 # Contract-driven wiring: whether this segment inherits a predecessor is the
 # same real Clean Rebase policy the adapter resolves at runtime
 # (enabled AND clean_rebase_enabled AND segment_index==clean_rebase_segment).
 # A Clean Rebase segment must not wire/read any predecessor; the audit then
 # judges the noise_mask contract from the adapter's real plan, not segment_index.
 prep=g[prepare]['inputs']
 rebase=prep.get('enabled') is True and prep.get('clean_rebase_enabled') is True and i==prep.get('clean_rebase_segment')
 if i>0 and prep.get('enabled') is True and not rebase:
  g['PREBAKE_PREVIOUS']={'class_type':'H3PreBakePreviousState','inputs':{'project_id':ctx['project_id'],'segment_index':i,'group_id':ctx['group_id']}}
  g[prepare]['inputs']['prev_latent']=['PREBAKE_PREVIOUS',0]
 g['PREBAKE_AUDIT']={'class_type':'H3PreBakeContinuationAudit','inputs':{'conditioning':[guides,0],'latent':[prepare,0],'project_id':ctx['project_id'],'segment_index':i,'plan_json':[prepare,1]}}
 g['126']['inputs']['conditioning']=['PREBAKE_AUDIT',0];g['125']['inputs']['latent_image']=['PREBAKE_AUDIT',1]
 g=anchor_clean_rebase(g,ctx,i,payload.get('anchor_clean_rebase') is True,attempt['attempt_id'],cached_guides)
 if 'SEAM_PRECHECK' in g:
  attempt['guide_anchor_sha256']=guide_policy_digest(json.loads(g['SEAM_PRECHECK']['inputs']['guide_guard_json']))
  attempt['snapshot'].update(predecessor_index=i-1,guide_predecessor_index=i-1)
 from .user_guides import apply as apply_user_guide
 g,user_guide=apply_user_guide(g,ctx,i,attempt['attempt_id'])
 if user_guide is not None:attempt['snapshot']['user_guide']=user_guide
 result=prune(g,['961',save]);assert not any(n['class_type'] in ('MiniMaxH3ReferenceToVideo','CLIPLoader','H3SelectiveTEUnload') for n in result.values())
 if 'SEAM_PRECHECK' in result or user_guide is not None:attempt['graph_sha256']=graph_digest(result) # Existing submit gate rejects changes before queue/GPU.
 with LOCK, state_lock or nullcontext():
  _,data=bound_context(ctx);entry=data['segments'].get(str(i),{})
  attempt_check(ctx,i,data,attempt)
  if entry.get('attempt',{}).get('status') in ('PREPARED','PENDING','CANCELLING','BLOCKED'):raise ValueError('Concurrent generation preparation')
  if entry.get('video_status')=='SUCCESS':invalidate_video_chain(ledger_path(ctx),data,ctx,i,state_lock)
  archive_attempt(entry);entry['attempt']=attempt;entry['predecessor_index']=attempt['snapshot']['predecessor_index'];path=ledger_path(ctx);receipts=read_state(path.parent/'six_acceptance.json') or {}
  receipts[str(i)]={**attempt,'status':'PENDING','submitted_at_epoch':time.time()}
  atomic_json(path,data);atomic_json(path.parent/'six_acceptance.json',receipts)
 return {'graph':result,'cache_key':key,'attempt_id':attempt['attempt_id']}

def archive_attempt(entry):
 old=entry.get('attempt')
 if old:entry.setdefault('attempt_history',[]).append(copy.deepcopy(old))

def graph_digest(graph):return codec.digest(codec.canonical(clean_graph(graph)))

def cross_group_gate(graph,ctx,index):
 raw=graph.get('LONG_SONG',{}).get('inputs',{}).get('cross_group_json')
 if not raw and 'CROSS_GROUP_PREVIOUS' not in graph:return None
 import nodes
 guard=nodes.NODE_CLASS_MAPPINGS.get('H3CrossGroupPrevious')
 if guard is None:raise ValueError('跨组校验节点未加载，禁止提交GPU')
 return guard.verify_graph(graph,ctx,index)

def validate_deadline(attempt,h=None):
 if attempt.get('stop_reason'):raise ValueError('Attempt stopped: '+attempt['stop_reason'])
 # Elapsed time is observational only. Explicitly stopped attempts stay rejected.

def fallback(payload,state_lock=None):
 ctx=payload['context'];i=int(payload['index']);g=clean_graph(payload['graph'])
 cross=cross_group_gate(g,ctx,i)
 with LOCK,state_lock or nullcontext():
  binding,data=bound_context(ctx);entry=data['segments'].get(str(i),{})
  if entry.get('conditioning_status')!='DYNAMIC_FALLBACK' or payload['cache_key']!=entry.get('cache_key') or codec.digest(payload['text'].encode())!=entry.get('final_prompt_sha256'):raise ValueError('Fallback contract/revision mismatch')
  independent=binding['start_mode']=='independent' and i==binding['start_index']
  prep=next(n['inputs'] for n in g.values() if n['class_type']=='H3ContinuationPrepare')
  if cross and independent:raise ValueError('跨组必须选择连续续跑，不能独立开始')
  if i<binding['start_index'] or (prep.get('enabled') is True)!=((i>0 and not independent) or bool(cross and i==0)):raise ValueError('Fallback inheritance/start policy mismatch')
  if i>0 and not independent and not (prep.get('clean_rebase_enabled') is True and i==prep.get('clean_rebase_segment')):verify_predecessor(ctx,i)
  if entry.get('attempt',{}).get('status') in ('PREPARED','PENDING','CANCELLING','BLOCKED'):raise ValueError('Segment already has an active attempt')
  attempt={'attempt_id':uuid.uuid4().hex,'project_id':ctx['project_id'],'group_id':ctx['group_id'],'execution_version':ctx['execution_version'],'revision':entry['revision'],'cache_key':entry['cache_key'],'status':'PREPARED','prepared_at_epoch':time.time(),'prompt_id':None,'route':'DYNAMIC_FALLBACK'}
  attempt['snapshot']={'text':payload['text'],'context':copy.deepcopy(ctx),'predecessor_index':i-1 if i>0 and not independent and not (prep.get('clean_rebase_enabled') is True and i==prep.get('clean_rebase_segment')) else None}
  if cross:attempt['snapshot']['cross_group']=copy.deepcopy(cross)
  claim={'context':ctx,'index':i,'attempt_id':attempt['attempt_id']}
  for n in g.values():
   for k,v in list(n['inputs'].items()):
    if v==['136',0]:n['inputs'][k]=['ATTEMPT_GUARD',0]
    elif v==['136',1]:n['inputs'][k]=['ATTEMPT_GUARD',1]
  g['ATTEMPT_GUARD']={'class_type':'H3AttemptGuard','inputs':{'conditioning':['136',0],'latent':['136',1],'execution_json':json.dumps(claim)}}
  g=anchor_clean_rebase(g,ctx,i,payload.get('anchor_clean_rebase') is True,attempt['attempt_id'])
  if 'SEAM_PRECHECK' in g:
   attempt['guide_anchor_sha256']=guide_policy_digest(json.loads(g['SEAM_PRECHECK']['inputs']['guide_guard_json']))
   attempt['snapshot'].update(predecessor_index=i-1,guide_predecessor_index=i-1)
  from .user_guides import apply as apply_user_guide
  g,user_guide=apply_user_guide(g,ctx,i,attempt['attempt_id'])
  if user_guide is not None:attempt['snapshot']['user_guide']=user_guide
  attempt['graph_sha256']=graph_digest(g)
  if entry.get('video_status')=='SUCCESS':invalidate_video_chain(ledger_path(ctx),data,ctx,i,state_lock)
  archive_attempt(entry);entry['attempt']=attempt;entry['predecessor_index']=attempt['snapshot']['predecessor_index'];receipts=read_state(ledger_path(ctx).parent/'six_acceptance.json') or {}
  receipts[str(i)]={**attempt,'status':'PENDING'}
  atomic_json(ledger_path(ctx),data);atomic_json(ledger_path(ctx).parent/'six_acceptance.json',receipts)
  return {'graph':g,'attempt_id':attempt['attempt_id'],'cache_key':entry['cache_key']}

def accepted(payload,server,state_lock=None):
 import folder_paths
 from safetensors import safe_open
 ctx=payload['context'];i=int(payload['index']);pid=payload['prompt_id'];path=ledger_path(ctx);root=path.parent
 def validate(data,receipts):
  entry=data['segments'].get(str(i),{});r=(receipts or {}).get(str(i),{});attempt=entry.get('attempt')
  if data.get('group_id')!=ctx['group_id'] or data.get('project_id',ctx['project_id'])!=ctx['project_id']:raise ValueError('Acceptance ledger group/project mismatch')
  if entry.get('cache_key')!=payload['cache_key']:raise ValueError('STALE acceptance cache_key')
  if attempt:
   attempt_check(ctx,i,data,attempt)
   validate_deadline(attempt,h=None)
   if attempt.get('prompt_id')!=pid or attempt['status'] not in ('PENDING','SUCCESS'):raise ValueError('Acceptance prompt_id/attempt mismatch')
   if r and (r.get('status') not in ('PENDING','SUCCESS') or any(r.get(k)!=attempt[k] for k in ('group_id','project_id','execution_version','revision','cache_key','attempt_id')) or r.get('prompt_id') not in (None,pid)):raise ValueError('STALE acceptance receipt identity/revision/cache/attempt changed')
  else:
   # Legacy receipts remain valid only with exact existing acceptance lineage.
   group=(receipts or {}).get('_native_merge',{}).get('groups',{}).get(ctx['group_id'],{})
   if not r or r.get('status')!='SUCCESS' or entry.get('video_status')!='SUCCESS' or r.get('prompt_id')!=pid or entry.get('prompt_id')!=pid:raise ValueError('MISSING legacy acceptance; no synthetic predecessor')
   if r.get('group_id') not in (None,ctx['group_id']) or (not r.get('group_id') and group.get('prompt_ids',{}).get(str(i))!=pid):raise ValueError('Legacy group identity is not proven')
  h=server.prompt_queue.get_history(prompt_id=pid).get(pid)
  if not h or h['status'].get('completed') is not True or h['status'].get('status_str')!='success' or any(e in ('execution_error','execution_interrupted') for e,_ in h['status'].get('messages',[])):raise ValueError('No completed error-free video history for exact prompt_id')
  if attempt:validate_deadline(attempt,h)
  if h['prompt'][1]!=pid:raise ValueError('History prompt_id mismatch')
  graph=h['prompt'][2];saves=[n for n in graph.values() if n['class_type']=='H3ContinuationSave' and n['inputs'].get('enabled') is True]
  if attempt:
   from .user_guides import submission_check
   submission_check(graph,ctx,i,attempt)
  if 'SEAM_GUIDE' in graph:
   if attempt and attempt.get('guide_anchor_sha256') and not __import__(__package__+'.adaptive_bridge',fromlist=['graph_matches']).graph_matches(attempt,graph):raise ValueError('Guide submitted graph changed before acceptance')
   verify_predecessor(ctx,i)
   source=(receipts or {}).get(str(i-1),{})
   expected='h3_rebase_composition/'+source['prompt_id']+'_'+source['video_sha256'][:16]+'.png'
   if graph.get('SEAM_IMAGE',{}).get('inputs',{}).get('image')!=expected:raise ValueError('Rebase anchor predecessor changed before acceptance')
   if attempt and attempt.get('guide_anchor_sha256'):
    for name,stage in (('SEAM_PRECHECK','before'),('SEAM_AUDIT','after')):
     policy=json.loads(graph.get(name,{}).get('inputs',{}).get('guide_guard_json','{}'))
     if policy.get('stage')!=stage or guide_policy_digest(policy)!=attempt['guide_anchor_sha256']:raise ValueError('Guide audit binding changed before acceptance')
  native_graph_check(graph,ctx,i)
  loads=[n['inputs'] for n in graph.values() if n['class_type']=='H3ConditioningLoad']
  guards=[n['inputs'] for n in graph.values() if n['class_type']=='H3AttemptGuard']
  if attempt and attempt.get('route')=='DYNAMIC_FALLBACK':
   if len(guards)!=1 or not __import__(__package__+'.adaptive_bridge',fromlist=['graph_matches']).graph_matches(attempt,graph):raise ValueError('Fallback history semantic snapshot mismatch')
   claim=json.loads(guards[0]['execution_json'])
   if claim.get('attempt_id')!=attempt['attempt_id'] or any(claim.get('context',{}).get(k)!=ctx.get(k) for k in ('story_id','project_id','group_id','execution_version')) or claim.get('index')!=i:raise ValueError('Fallback execution binding mismatch')
  elif len(loads)!=1:raise ValueError('Video history has no unique PreBake load contract')
  if not (attempt and attempt.get('route')=='DYNAMIC_FALLBACK'):
   contract,key=codec.verified_contract(loads[0]['contract_json'])
   if key!=entry['cache_key'] or contract['group_id']!=ctx['group_id'] or contract['segment_id']!=str(i) or contract['final_text_revision']!=entry['revision']:raise ValueError('History group/revision/cache_key mismatch')
   if attempt:
    claim=json.loads(loads[0].get('execution_json','{}'))
    if claim.get('attempt_id')!=attempt['attempt_id'] or any(claim.get('context',{}).get(k)!=ctx.get(k) for k in ('story_id','project_id','group_id','execution_version')) or claim.get('index')!=i:raise ValueError('History execution binding mismatch')
  videos=[(k,n) for k,n in graph.items() if n['class_type']=='SaveVideo']
  if len(videos)!=1:raise ValueError('Video history has no unique SaveVideo')
  output=h.get('outputs',{}).get(videos[0][0],{});files=[v for k in ('images','videos') for v in output.get(k,[]) if Path(v.get('filename','')).suffix.lower() in ('.mp4','.webm','.mov','.mkv')]
  if len(files)!=1 or files[0].get('type')!='output':raise ValueError('No exact saved video output')
  video=(Path(folder_paths.get_output_directory())/files[0].get('subfolder','')/files[0]['filename']).resolve()
  if not video.is_relative_to(Path(folder_paths.get_output_directory()).resolve()) or not video.is_file():raise ValueError('Video file missing or outside output')
  latent=root/('seg_%05d.safetensors'%i)
  if not latent.is_file():raise ValueError('Native latent missing')
  with safe_open(str(latent),framework='pt',device='cpu') as handle:meta=handle.metadata()
  if meta.get('provider')!='CORE_NATIVE_MASKED_AV' or int(meta.get('segment_index',-1))!=i or meta.get('prompt_id')!=pid:raise ValueError('Latent metadata/prompt_id mismatch')
  latent_sha=codec.file_sha(latent)
  for expected in (r.get('latent_sha256'),entry.get('latent_sha256') if entry.get('prompt_id')==pid else None):
   if expected and expected!=latent_sha:raise ValueError('Latent SHA256 changed after acceptance')
  return entry,r,latent,latent_sha,attempt,files[0],str(video),codec.file_sha(video)
 with LOCK, state_lock or nullcontext():
  data=read_state(path);receipts=read_state(root/'six_acceptance.json')
  if data is None:raise ValueError('MISSING PreBake ledger')
 validate(data,receipts)
 with LOCK, state_lock or nullcontext():
  data=read_state(path);receipts=read_state(root/'six_acceptance.json')
  if data is None:raise ValueError('MISSING ledger before commit')
  entry,r,latent,latent_sha,attempt,video_ref,video_path,video_sha=validate(data,receipts)
  receipts=receipts or {};stamp=r.get('accepted_at_epoch') or time.time()
  entry.update(group_id=ctx['group_id'],project_id=ctx['project_id'],video_status='SUCCESS',prompt_id=pid,latent_sha256=latent_sha,accepted_at_epoch=stamp,receipt_status='SUCCESS')
  if attempt:attempt.update(status='SUCCESS',terminal_status='SUCCESS')
  receipt={**(attempt or {}),'status':'SUCCESS','prompt_id':pid,'group_id':ctx['group_id'],'project_id':ctx['project_id'],'revision':entry['revision'],'cache_key':entry['cache_key'],'latent_path':str(latent),'latent_sha256':latent_sha,'accepted_at_epoch':stamp,'video_output_ref':{**video_ref,'prompt_id':pid},'video_path':video_path,'video_sha256':video_sha}
  # Ledger first: an interrupted second write is recovered only by the same
  # exact history/attempt validator, never by interpreting a saved file as success.
  atomic_json(path,data);receipts[str(i)]=receipt;atomic_json(root/'six_acceptance.json',receipts)
 return {'VIDEO_SUCCESS':True,'segment_index':i}

def recover_segment(project,index,server,state_lock=None):
 manager=getattr(server,'h3_attempt_manager',None)
 if manager:return manager.recover(project,index)
 with LOCK, state_lock or nullcontext():
  bindings=[b for b in execution_state.bindings() if b['project_id']==project]
  if len(bindings)!=1:return False
  ctx=bindings[0];_,data=bound_context(ctx);entry=data['segments'].get(str(index),{});attempt=entry.get('attempt',{})
  if not attempt:return False
  receipts=read_state(ledger_path(ctx).parent/'six_acceptance.json')
  if entry.get('video_status')=='SUCCESS' and (receipts or {}).get(str(index),{}).get('status')=='SUCCESS':
   # A completed predecessor remains valid after selecting a later start/mode.
   # Do not reinterpret its historical execution version as a live late commit.
   verify_predecessor(ctx,index+1)
   return True
  if attempt.get('status') not in ('PENDING','SUCCESS') or not attempt.get('prompt_id'):return True
  pid=attempt['prompt_id'];h=server.prompt_queue.get_history(prompt_id=pid).get(pid)
  if not h:return True
  accepted({'context':ctx,'index':index,'prompt_id':pid,'cache_key':entry['cache_key']},server,state_lock)
  return True

def register():
 import asyncio
 from aiohttp import web
 from server import PromptServer
 server=PromptServer.instance
 if getattr(server,'h3_prebake_routes_installed',False):return
 server.h3_prebake_routes_installed=True
 from .attempt_lifecycle import install
 install(server)
 from .user_guides import register as register_user_guides
 register_user_guides()
 server.h3_prebake_acceptance_reconcile=lambda payload:accepted(payload,server,getattr(server,'h3_acceptance_state_lock',None))
 server.h3_prebake_pending=lambda project,index,group:mark_pending(project,index,group,getattr(server,'h3_acceptance_state_lock',None))
 server.h3_prebake_recover=lambda project,index:recover_segment(project,index,server,getattr(server,'h3_acceptance_state_lock',None))
 for route,fn in (('execution',lambda p:execution_state.prepare(p,getattr(server,'h3_acceptance_state_lock',None))),('draft',lambda p:execution_state.draft(p,getattr(server,'h3_acceptance_state_lock',None))),('story',lambda p:story(p,getattr(server,'h3_acceptance_state_lock',None))),('invalidate',lambda p:execution_state.draft(p,getattr(server,'h3_acceptance_state_lock',None))),('plan',lambda p:plan(p,getattr(server,'h3_acceptance_state_lock',None))),('generate',lambda p:generate(p,getattr(server,'h3_acceptance_state_lock',None))),('fallback',lambda p:fallback(p,getattr(server,'h3_acceptance_state_lock',None))),('accepted',lambda p:accepted(p,server,getattr(server,'h3_acceptance_state_lock',None)))):
  async def handler(request,fn=fn,route=route):
   try:
    origin=request.headers.get('Origin')
    if origin and origin!=f'{request.scheme}://{request.host}':raise ValueError('Origin rejected')
    payload=await request.json()
    if route in ('generate','fallback','story','execution'):await server.h3_attempt_manager.tick()
    result=await asyncio.to_thread(fn,payload)
    if route=='invalidate':await server.h3_attempt_manager.tick()
    return web.json_response(result)
   except Exception as ex:return web.json_response({'error':str(ex)},status=409)
  server.routes.post('/h3/prebake/'+route)(handler)






def native_graph_check(graph,ctx,index):
 saves=[n for n in graph.values() if n['class_type']=='H3ContinuationSave' and n['inputs'].get('enabled') is True]
 if len(saves)!=1 or saves[0]['inputs'].get('project_id')!=ctx['project_id'] or int(saves[0]['inputs'].get('segment_index',-1))!=int(index):raise ValueError('Native latent save identity mismatch; rejected before GPU dispatch')
