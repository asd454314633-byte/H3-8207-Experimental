"""Metadata-led discovery and immutable-task recovery. Python standard library only.

Never imports ComfyUI or executes node classes. Never submits, interrupts, or rewrites graphs.
"""
from __future__ import annotations
import copy,hashlib,json,math,re,uuid,struct,ast,operator
from dataclasses import dataclass,field
from decimal import Decimal,InvalidOperation
from pathlib import Path
from typing import Any,Callable

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def file_sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

class CompatibilityError(ValueError):pass

class ScalarResolver:
 """Optional pure value adapters. No eval, node execution, or parameter rewriting."""
 def __init__(self,graph,meta):self.graph=graph;self.meta=meta;self.adapters={}
 def register(self,kind,fn):self.adapters[kind]=fn;return self
 def resolve(self,value,seen=None):
  if not is_link(value):return copy.deepcopy(value)
  seen=set() if seen is None else set(seen);k,slot=value
  if k in seen:raise CompatibilityError('Scalar cycle')
  seen.add(k);n=self.graph[k];p=n['inputs'];kind=n['class_type']
  if kind in self.adapters:return self.adapters[kind](p,slot,lambda x:self.resolve(x,seen))
  if kind.startswith('Primitive') and 'value' in p:return copy.deepcopy(p['value'])
  if kind=='Any Switch (rgthree)':
   values=[v for _,v in sorted(p.items()) if v is not None]
   if len(values)!=1:raise CompatibilityError('Scalar switch is ambiguous')
   return self.resolve(values[0],seen)
  if kind=='ResolutionSelector':
   match=re.match(r'^(\d+):(\d+)',p['aspect_ratio'])
   if not match:raise CompatibilityError('Unknown resolution ratio')
   w,h=map(int,match.groups());multiple=int(p['multiple']);scale=math.sqrt(float(p['megapixels'])*1024*1024/(w*h))
   return (round(w*scale/multiple)*multiple,round(h*scale/multiple)*multiple)[slot]
  if kind=='ComfyMathExpression':
   values={k.split('.',1)[1]:self.resolve(v,seen) for k,v in p.items() if k.startswith('values.')}
   tree=ast.parse(p['expression'],mode='eval');ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Mod:operator.mod};calls={'max':max,'min':min,'round':round,'floor':math.floor,'ceil':math.ceil}
   def calc(t):
    if isinstance(t,ast.Expression):return calc(t.body)
    if isinstance(t,ast.Constant) and type(t.value) in (int,float):return t.value
    if isinstance(t,ast.Name) and t.id in values:return values[t.id]
    if isinstance(t,ast.BinOp) and type(t.op) in ops:return ops[type(t.op)](calc(t.left),calc(t.right))
    if isinstance(t,ast.UnaryOp) and isinstance(t.op,ast.USub):return -calc(t.operand)
    if isinstance(t,ast.Call) and isinstance(t.func,ast.Name) and t.func.id in calls and not t.keywords:return calls[t.func.id](*[calc(x) for x in t.args])
    raise CompatibilityError('Unsupported scalar expression; preserve symbolic input')
   val=calc(tree);out=self.meta.outputs(kind)
   return int(val) if slot<len(out) and out[slot]=='INT' else val
  raise CompatibilityError('Unknown scalar producer '+kind+'; register a pure adapter')

class Metadata:
 def __init__(self,raw):self.raw=copy.deepcopy(raw)
 def node(self,kind):return self.raw.get(kind,{})
 def declaration(self,kind,name):
  spec=self.node(kind).get('input',{})
  for group in ('required','optional','hidden'):
   if name in spec.get(group,{}):return spec[group][name]
  if '.' in name:
   family,member=name.split('.',1)
   for group in ('required','optional'):
    d=spec.get(group,{}).get(family)
    if isinstance(d,list) and len(d)>1 and d[0]=='COMFY_AUTOGROW_V3':
     template=d[1].get('template',{});prefix=template.get('prefix','')
     index=member[len(prefix):] if prefix and member.startswith(prefix) else ''
     if index.isdigit() and int(index)<template.get('max',10**6):
      items=[v for g in ('required','optional') for v in template.get('input',{}).get(g,{}).values()]
      if len(items)==1:return items[0]
  # Autogrow families may advertise an existing numbered member.
  base=re.sub(r'\d+$','*',name)
  matches=[d for group in ('required','optional') for k,d in spec.get(group,{}).items() if re.sub(r'\d+$','*',k)==base]
  return matches[0] if matches and all(x==matches[0] for x in matches) else None
 def input_type(self,kind,name):
  d=self.declaration(kind,name)
  if isinstance(d,(list,tuple)) and d:
   return 'COMBO' if isinstance(d[0],(list,tuple)) else str(d[0])
  return 'UNKNOWN'
 def types(self,kind):
  return {self.input_type(kind,k) for g in ('required','optional') for k in self.node(kind).get('input',{}).get(g,{})}
 def outputs(self,kind):return self.node(kind).get('output',[])

def is_link(value,declared='UNKNOWN'):
 # Literal arrays must use the ComfyUI __value__ wrapper (or ARRAY/JSON declaration).
 return declared not in ('ARRAY','JSON','COMBO') and isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and type(value[1]) is int and value[1]>=0

def normalize(value,declared='UNKNOWN'):
 if isinstance(value,dict) and '__value__' in value and len(value)==1:
  raw=value['__value__']
  return {'literal':normalize(raw,'ARRAY')} if isinstance(raw,(list,dict)) else normalize(raw,declared)
 if declared in ('INT','FLOAT'):
  if isinstance(value,bool) or not isinstance(value,(int,float,str)):raise CompatibilityError('Invalid '+declared)
  try:n=Decimal(str(value))
  except InvalidOperation:raise CompatibilityError('Invalid numeric input')
  if not n.is_finite():raise CompatibilityError('Non-finite numeric input')
  if declared=='INT' and n!=n.to_integral_value():raise CompatibilityError('Lossy INT conversion')
  return {'number':format(n.normalize(),'f')}
 if declared=='BOOLEAN':
  if type(value) is bool:return value
  if type(value) in (int,float) and value in (0,1):return bool(value)
  # Mirrors ComfyUI bool(str), not an invented parser in which "false" means False.
  if isinstance(value,str):return bool(value)
  raise CompatibilityError('Unsupported BOOLEAN representation')
 if declared=='STRING':
  if isinstance(value,(dict,list)):raise CompatibilityError('Container cannot be silently converted to STRING')
  return str(value)
 if isinstance(value,list):return [normalize(v) for v in value]
 if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
 if isinstance(value,float) and not math.isfinite(value):raise CompatibilityError('Non-finite opaque value')
 return value

@dataclass
class GraphAnalysis:
 semantic_version:str
 nodes:dict
 issues:list
 signatures:dict

def analyze(graph:dict,metadata:Metadata)->GraphAnalysis:
 """ID/order/layout independent DAG signature; retains class, edges, ports, values.

 Unknown declared/undeclared values stay opaque. No execution behavior is inferred
 from cosmetic title/position. Cycles and missing edges are explicit issues.
 """
 nodes={str(k):v for k,v in graph.items()};memo={};active=set();issues=[]
 def visit(k):
  if k in memo:return memo[k]
  if k in active:raise CompatibilityError('Cycle at '+k)
  if k not in nodes:raise CompatibilityError('Dangling source '+k)
  active.add(k);n=nodes[k];inputs={}
  if n['class_type'] not in metadata.raw:issues.append({'node':k,'issue':'UNKNOWN_METADATA'})
  for name,decl in metadata.node(n['class_type']).get('input',{}).get('required',{}).items():
   autogrow=isinstance(decl,list) and decl and decl[0]=='COMFY_AUTOGROW_V3'
   if not autogrow and name not in n.get('inputs',{}):issues.append({'node':k,'issue':'MISSING_REQUIRED_INPUT','input':name})
  for name,v in n.get('inputs',{}).items():
   typ=metadata.input_type(n['class_type'],name)
   if is_link(v,typ):
    source,slot=v
    if source not in nodes:raise CompatibilityError('Dangling source '+source)
    outs=metadata.outputs(nodes[source]['class_type'])
    if outs and slot>=len(outs):raise CompatibilityError('Output slot out of range')
    st=str(outs[slot]) if outs else 'UNKNOWN'
    if typ not in ('UNKNOWN','*','ANY') and st not in ('UNKNOWN','*','ANY') and typ!=st and ',' not in typ and ',' not in st:
     raise CompatibilityError('Incompatible connection '+k+'.'+name+': '+st+' -> '+typ)
    inputs[name]={'source':visit(source),'slot':slot}
   else:inputs[name]=normalize(v,typ)
  active.remove(k);memo[k]=digest({'kind':n['class_type'],'inputs':inputs});return memo[k]
 for k in nodes:visit(k)
 return GraphAnalysis(digest(sorted(memo.values())),nodes,issues,memo)

@dataclass(frozen=True)
class Capability:
 role:str
 node_id:str
 confidence:str='DECLARED'
 details:dict=field(default_factory=dict)

class AdapterRegistry:
 """Adapters are supplied code, not code loaded from an untrusted workflow."""
 def __init__(self):self.adapters=[]
 def register(self,adapter:Callable):self.adapters.append(adapter);return self
 def discover(self,graph,meta):
  analysis=analyze(graph,meta);caps=[]
  for k,n in analysis.nodes.items():
   kind=n['class_type'];info=meta.node(kind);types=meta.types(kind);outs=set(meta.outputs(kind))
   actual_types={meta.input_type(kind,name) for name in n.get('inputs',{})};types|=actual_types
   if info.get('output_node') and 'VIDEO' in types:caps.append(Capability('video_output',k))
   elif info.get('output_node') and {'IMAGE','AUDIO'}<=types and any('fps' in x.lower() or 'frame_rate' in x.lower() for x in n.get('inputs',{})):
    # May be an assertion terminal; do NOT call it a video saver merely by shape.
    caps.append(Capability('av_terminal_candidate',k,'CONTEXT_ONLY'))
   if 'IMAGE' in outs and {'LATENT','VAE'}<=types:caps.append(Capability('video_decode',k))
   if 'AUDIO' in outs:caps.append(Capability('audio',k))
   if 'LATENT' in outs and ('GUIDER' in types or {'MODEL','CONDITIONING'}<=types):caps.append(Capability('sampling',k))
   if 'MODEL' in outs:caps.append(Capability('model',k,details={'inputs':copy.deepcopy(n.get('inputs',{}))}))
   if 'CONDITIONING' in outs and any('prompt' in x.lower() for x in n.get('inputs',{})):
    refs=[name for name in n['inputs'] if name.startswith('ref_images.') or ('ref' in name.lower() and meta.input_type(kind,name)=='IMAGE')]
    first=any('first' in name.lower() and meta.input_type(kind,name)=='IMAGE' for name in n['inputs'])
    last=any('last' in name.lower() and meta.input_type(kind,name)=='IMAGE' for name in n['inputs'])
    mode='Ref2VA' if refs else ('FL2VA' if first and last else 'I2VA' if first else 'L2VA' if last else 'T2VA')
    caps.append(Capability('generation',k,details={'mode':mode,'reference_inputs':refs}))
   video_inputs=[name for name in n.get('inputs',{}) if meta.input_type(kind,name)=='VIDEO']
   if 'VIDEO' in outs and (len(video_inputs)>1 or (video_inputs and info.get('input_is_list'))):caps.append(Capability('merge_candidate',k,'CONTEXT_ONLY'))
   if 'IMAGE' in outs and not any(is_link(v,meta.input_type(kind,name)) for name,v in n.get('inputs',{}).items()):caps.append(Capability('image_source',k))
   for name,v in n.get('inputs',{}).items():
    tag=name.lower()
    role=next((role for role,words in [('prompt',('prompt','text')),('fps',('fps','frame_rate')),('frames',('length','frames')),('resolution',('width','height','megapixels'))] if any(w in tag for w in words)),None)
    if role:caps.append(Capability(role,k,'CONTEXT_ONLY',{'input':name,'declaration':meta.input_type(kind,name),'value':copy.deepcopy(v)}))
   for adapter in self.adapters:caps.extend(adapter(k,n,info,graph,meta))
  return analysis,caps

def native_h3_adapter(k,n,info,graph,meta):
 roles={'H3ContinuationPrepare':'native_prepare','H3ContinuationSave':'native_save','H3ContinuationTrimOnce':'native_trim','H3ContinuationAssemble':'assembly_assertion'}
 return [Capability(roles[n['class_type']],k,details=copy.deepcopy(n['inputs']))] if n['class_type'] in roles else []

@dataclass(frozen=True)
class VerifiedNative:
 prompt_id:str
 provider:str
 frames:int
 path:str
 sha256:str
 metadata_json:str

def verify_native(receipt,root,expected_prompt_id):
 """Read actual native file/header; never generate a receipt or latent."""
 if receipt.get('prompt_id')!=expected_prompt_id:raise CompatibilityError('Native receipt prompt_id mismatch')
 root=Path(root).resolve();p=(root/receipt.get('file','')).resolve()
 if not p.is_relative_to(root) or not p.is_file():raise CompatibilityError('Native file missing/outside root')
 with p.open('rb') as f:
  raw=f.read(8)
  if len(raw)!=8:raise CompatibilityError('Invalid native header')
  size=struct.unpack('<Q',raw)[0]
  if not 0<size<16*1024*1024:raise CompatibilityError('Invalid native header size')
  header=json.loads(f.read(size))
 meta=header.get('__metadata__',{})
 for k in ('prompt_id','provider','frames','segment_index'):
  if str(meta.get(k))!=str(receipt.get(k)):raise CompatibilityError('Native header/receipt mismatch: '+k)
 tensors=[t for k,t in header.items() if k!='__metadata__']
 if not tensors:raise CompatibilityError('Native file has no tensor data')
 for tensor in tensors:
  offsets=tensor.get('data_offsets',[])
  if len(offsets)!=2 or not 0<=offsets[0]<=offsets[1]<=p.stat().st_size-size-8:raise CompatibilityError('Invalid native tensor bounds')
 sha=file_sha(p)
 if receipt.get('sha256') and receipt['sha256']!=sha:raise CompatibilityError('Native file SHA mismatch')
 return VerifiedNative(expected_prompt_id,meta['provider'],int(meta['frames']),str(p),sha,canonical(meta))

def continuation(caps,receipt=None):
 roles={c.role for c in caps};missing=sorted({'native_prepare','native_save','native_trim'}-roles)
 if missing:return {'status':'UNAVAILABLE','missing':missing,'preserve_completed_output':True,'choices':['independent_segment','registered_compatible_adapter','stop']}
 if receipt is None:return {'status':'AVAILABLE_NEEDS_RECEIPT','preserve_completed_output':True}
 if not isinstance(receipt,VerifiedNative) or receipt.provider!='CORE_NATIVE_MASKED_AV':
  return {'status':'UNAVAILABLE','missing':['valid_native_receipt'],'preserve_completed_output':True}
 return {'status':'COMPATIBLE_OFFLINE','provider':receipt.provider,'frames':receipt.frames,'native_sha256':receipt.sha256,'preserve_completed_output':True,'evidence':'Actual native file header/receipt verified; no GPU continuation executed'}

class MappingStore:
 def __init__(self,path):self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
 def save(self):
  self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(canonical(self.data),encoding='utf-8');tmp.replace(self.path)
 def choose(self,scope,candidates,selected=None):
  state=self.data.setdefault(scope,{})
  if selected is not None:
   if selected not in candidates:raise CompatibilityError('Invalid saved mapping')
   state['selected']=selected;self.save();return selected,'SAVED_SELECTION'
  if state.get('selected') in candidates:return state['selected'],'SAVED_SELECTION'
  if len(candidates)==1:return candidates[0],'UNIQUE'
  if not candidates:return None,'MISSING_OUTPUT'
  first=not state.get('asked');state['asked']=True;state['candidates']=candidates;self.save()
  return None,'NEEDS_SELECTION_ONCE' if first else 'AWAITING_SAVED_SELECTION'

class WorkflowVersionStore:
 """Append-only versions and raw variants; semantic equivalence is not rejection."""
 def __init__(self,directory):self.directory=Path(directory)
 def observe(self,graph,meta):
  a=analyze(graph,meta);raw=digest(graph);root=self.directory/a.semantic_version;root.mkdir(parents=True,exist_ok=True)
  path=root/(raw+'.json')
  if not path.exists():
   with path.open('x',encoding='utf-8') as f:f.write(canonical({'semantic_version':a.semantic_version,'raw_sha256':raw,'graph':graph,'metadata':meta.raw}))
  return {'semantic_version':a.semantic_version,'raw_sha256':raw,'path':str(path)}

@dataclass(frozen=True)
class TaskSnapshot:
 prompt_id:str
 graph_json:str
 metadata_json:str
 receipt_json:str
 raw_sha256:str
 semantic_version:str
 task_id:str
 @classmethod
 def create(cls,prompt_id,graph,meta,receipt):
  if not prompt_id or receipt.get('prompt_id')!=prompt_id:raise CompatibilityError('Snapshot receipt prompt_id mismatch')
  a=analyze(graph,meta);raw=canonical(graph)
  return cls(prompt_id,raw,canonical(meta.raw),canonical(receipt),hashlib.sha256(raw.encode()).hexdigest(),a.semantic_version,str(uuid.uuid4()))
 def persist(self,directory):
  p=Path(directory)/('task_'+self.task_id+'.json');p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('x',encoding='utf-8') as f:f.write(canonical(self.__dict__))
  return p
 @classmethod
 def load(cls,path):
  s=cls(**json.loads(Path(path).read_text(encoding='utf-8')))
  if hashlib.sha256(s.graph_json.encode()).hexdigest()!=s.raw_sha256:raise CompatibilityError('Snapshot file integrity failure')
  if analyze(json.loads(s.graph_json),Metadata(json.loads(s.metadata_json))).semantic_version!=s.semantic_version:raise CompatibilityError('Snapshot semantic integrity failure')
  return s

class AssetResolver:
 def __init__(self,roots):self.roots={k:Path(v).resolve() for k,v in roots.items()}
 def resolve(self,ref):
  root=self.roots.get(ref.get('type'))
  if root is None:raise CompatibilityError('Unknown asset storage type')
  # Disallow cross-platform path escapes, Windows drives and ADS as well.
  parts=[str(ref.get('subfolder','')),str(ref.get('filename',''))]
  if not parts[1] or any(':' in p or p.startswith(('/','\\')) for p in parts):raise CompatibilityError('Unsafe output reference')
  p=root.joinpath(*[x.replace('\\','/') for x in parts]).resolve()
  if not p.is_relative_to(root):raise CompatibilityError('Output outside storage root')
  if not p.is_file():raise CompatibilityError('Output file missing')
  return p

class RecoveryEngine:
 def __init__(self,registry=None,mappings=None,versions=None):self.registry=registry or AdapterRegistry().register(native_h3_adapter);self.mappings=mappings;self.versions=versions
 def recover(self,snapshot,history,resolver,current_graph=None,current_meta=None,native_receipt=None):
  result={'task_id':snapshot.task_id,'prompt_id':snapshot.prompt_id,'gpu_status':'UNCONFIRMED','output_status':'NOT_RECOVERED','player_status':'NOT_RECOVERED','warnings':[]}
  h=history.get(snapshot.prompt_id) if snapshot.prompt_id in history else history
  receipt=json.loads(snapshot.receipt_json)
  if not isinstance(h,dict) or not isinstance(h.get('prompt'),list) or len(h['prompt'])<3 or h['prompt'][1]!=snapshot.prompt_id:
   result['reason']='EXACT_HISTORY_MISSING_OR_WRONG_ID';return result
  status=h.get('status',{});events=status.get('messages',[])
  if not (status.get('completed') is True and status.get('status_str')=='success') or any(e[0] in ('execution_error','execution_interrupted') for e in events):
   result['reason']='NO_ERROR_FREE_GPU_SUCCESS';return result
  # Keep genuine GPU evidence independently, even when output/receipt recovery fails.
  result['gpu_status']='SUCCESS'
  graph=h['prompt'][2];meta=Metadata(json.loads(snapshot.metadata_json))
  if receipt.get('prompt_id')!=snapshot.prompt_id:result['reason']='RECEIPT_ID_MISMATCH';return result
  if receipt.get('attempt_id'):
   claims=[]
   for n in graph.values():
    v=n.get('inputs',{}).get('execution_json')
    if v:
     try:claims.append(json.loads(v))
     except (ValueError,TypeError):pass
   valid=[c for c in claims if c.get('attempt_id')==receipt['attempt_id'] and all(c.get('context',{}).get(k)==receipt[k] for k in ('project_id','group_id','execution_version') if k in receipt)]
   if len(valid)!=1:result['reason']='TASK_BINDING_NOT_PROVEN';return result
  try:analysis,caps=self.registry.discover(graph,meta)
  except CompatibilityError as e:result['reason']='HISTORY_CAPABILITY_ERROR: '+str(e);return result
  result['executed_semantic_version']=analysis.semantic_version
  if self.versions:result['executed_version_record']=self.versions.observe(graph,meta)
  result['semantic_relation']='EQUIVALENT' if analysis.semantic_version==snapshot.semantic_version else 'EXECUTED_VERSION_RECORDED'
  if result['semantic_relation']!='EQUIVALENT':result['warnings'].append('Task-owned history differs; preserve both immutable versions, never replace it with current canvas')
  candidates=[]
  for cap in caps:
   if cap.role!='video_output':continue
   outputs=h.get('outputs',{}).get(cap.node_id,{})
   for key in ('images','videos','gifs'):
    for ref in outputs.get(key,[]):
     if isinstance(ref,dict) and Path(str(ref.get('filename',''))).suffix.lower() in ('.mp4','.mkv','.webm','.mov','.avi'):
      candidates.append((cap.node_id,ref))
  if not candidates:result['reason']='NO_DECLARED_VIDEO_OUTPUT';return result
  scope=snapshot.semantic_version+':player'
  stable=[analysis.signatures[node]+':'+digest(ref) for node,ref in candidates]
  # Exact duplicates have no topology-derived unique identity; explicit per-snapshot
  # choice is required. Distinct outputs retain mappings across ID renumbering.
  ids=[key if stable.count(key)==1 else key+':'+node for key,(node,ref) in zip(stable,candidates)]
  selected,choice=self.mappings.choose(scope,ids) if self.mappings else ((ids[0],'UNIQUE') if len(ids)==1 else (None,'NEEDS_PERSISTENT_MAPPING_STORE'))
  if selected is None:result.update(reason=choice,candidates=ids);return result
  node,ref=candidates[ids.index(selected)]
  try:
   path=resolver.resolve(ref);sha=file_sha(path)
   if receipt.get('video_sha256') and receipt['video_sha256']!=sha:raise CompatibilityError('Output SHA256 differs from original receipt')
   # A new filename needs independent receipt/content proof, not a blind filename match.
   old_ref=receipt.get('video_output_ref')
   if old_ref and any(old_ref.get(k)!=ref.get(k) for k in ('filename','subfolder','type')) and not receipt.get('video_sha256'):
    raise CompatibilityError('Renamed output requires original content SHA256 receipt')
  except CompatibilityError as e:result['reason']=str(e);return result
  result.update(output_status='RECOVERED',player_status='READY_TO_BIND',output={'node_id':node,'ref':copy.deepcopy(ref),'path':str(path),'sha256':sha},reason='EXACT_TASK_OUTPUT_RECOVERED')
  active_caps=caps
  if current_graph is not None:
   try:
    ca,active_caps=self.registry.discover(current_graph,current_meta or meta);result['current_workflow_version']=ca.semantic_version
    if self.versions:result['current_version_record']=self.versions.observe(current_graph,current_meta or meta)
   except CompatibilityError as e:active_caps=[];result['warnings'].append('Current workflow unusable: '+str(e))
  result['continuation']=continuation(active_caps,native_receipt)
  if current_graph is not None and result['continuation']['status']=='COMPATIBLE_OFFLINE':
   # Never assume a different latent-producing model/geometry is tensor-compatible.
   previous=json.loads(snapshot.graph_json)
   def contract(g,m):
    found=[]
    for n in g.values():
     if 'MODEL' in m.outputs(n['class_type']):
      found.append(('model',n['class_type'],{k:v for k,v in n['inputs'].items() if not is_link(v,m.input_type(n['class_type'],k))}))
     for k,v in n.get('inputs',{}).items():
      if k.lower() in ('width','height','fps','frame_rate','aspect_ratio','megapixels') and not is_link(v,m.input_type(n['class_type'],k)):
       found.append((n['class_type'],k,normalize(v,m.input_type(n['class_type'],k))))
    return sorted(canonical(x) for x in found)
   if contract(previous,meta)!=contract(current_graph,current_meta or meta):
    result['continuation']={'status':'UNAVAILABLE','missing':['latent_model_geometry_or_fps_compatibility_proof'],'preserve_completed_output':True,'choices':['independent_segment','registered_compatible_adapter','stop']}
  return result

class TaskPlayerStore:
 """Offline bridge contract. UI integration must address task_id AND prompt_id."""
 def __init__(self,path):self.path=Path(path);self.data=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
 def apply(self,recovery,active_prompt_id):
  if recovery.get('output_status')!='RECOVERED':return 'NO_OUTPUT_BINDING'
  key=recovery['task_id'];entry=copy.deepcopy(recovery);entry['player_status']='RECOVERED';self.data[key]=entry
  self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(canonical(self.data),encoding='utf-8')
  return 'ACTIVE_PLAYER_RECOVERED' if active_prompt_id==recovery['prompt_id'] else 'ORIGINAL_TASK_LIBRARY_RECOVERED'

@dataclass(frozen=True)
class ExecutionPlan:
 ready:bool
 graph_json:str
 semantic_version:str
 capabilities:tuple
 missing:tuple

def plan_execution(graph,meta,registry=None):
 """Pure candidate adaptation: original parameters/edges are copied unchanged.

 The host supplies its existing executor. This module never has a live transport.
 """
 registry=registry or AdapterRegistry().register(native_h3_adapter)
 try:a,caps=registry.discover(graph,meta)
 except CompatibilityError as e:return ExecutionPlan(False,canonical(graph),'',(),(str(e),))
 sinks=[c.node_id for c in caps if c.role=='video_output'];active=set()
 def upstream(k):
  if k in active:return
  active.add(k);n=graph[k]
  for name,v in n.get('inputs',{}).items():
   if is_link(v,meta.input_type(n['class_type'],name)):upstream(v[0])
 for k in sinks:upstream(k)
 missing=[canonical(x) for x in a.issues if x['issue']=='MISSING_REQUIRED_INPUT' and x['node'] in active]
 if not sinks:missing.append('declared_video_output_or_registered_adapter')
 return ExecutionPlan(not missing,canonical(graph),a.semantic_version,tuple(caps),tuple(missing))

def execute_with_snapshot(plan,meta,receipt,directory,transport):
 """Reusable boundary tested ONLY with an offline fake transport.

 Save snapshot BEFORE dispatch. Transport must return the exact prompt_id. An
 uncertain response is not retried. Host retains timeout/queue isolation policy.
 """
 if not plan.ready:raise CompatibilityError('Missing execution capabilities: '+str(plan.missing))
 graph=json.loads(plan.graph_json);snapshot=TaskSnapshot.create(receipt['prompt_id'],graph,meta,receipt)
 snapshot.persist(directory)
 response=transport(copy.deepcopy(graph),snapshot.prompt_id)
 if response.get('prompt_id')!=snapshot.prompt_id:raise CompatibilityError('Dispatch identity uncertain; never auto-retry')
 return snapshot,response
