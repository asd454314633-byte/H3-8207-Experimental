"""H3 explicit tensor/primitive tree codec. No pickle, object import or executable loading."""
import hashlib,json,math,os,uuid
from pathlib import Path
import torch
from safetensors.torch import save_file,load_file,load as load_bytes
from comfy.nested_tensor import NestedTensor
SCHEMA='H3_CONDITIONING_PREBAKE_V1'
import os
import folder_paths
ROOT=Path(os.environ.get('H3_CONDITIONING_CACHE_ROOT', str(Path(folder_paths.get_user_directory())/'h3_conditioning_cache')))
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(x):return hashlib.sha256(x).hexdigest()
def file_sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest().upper()
HASH_MEMO={}
MODEL_REGISTRY={}
def verified_contract(text):
 c=json.loads(text);assert c['schema']==SCHEMA
 for name in ('prompt_sha256','reference_slots','width','height','frames','fps','h3','te','node136','generation_mode','ref2va_branch','conditioning_parameters','files'):
  if name not in c:raise ValueError('Missing binding '+name)
 assert digest(c['conditioning_parameters']['prompt'].encode())==c['prompt_sha256']
 for rec in c['files']:
  p=Path(rec['path']);s=p.stat();key=(str(p.resolve()),s.st_size,s.st_mtime_ns)
  if rec.get('role') in ('h3','te','video_vae','audio_vae') and MODEL_REGISTRY:
   trusted=MODEL_REGISTRY.get(str(p.resolve()))
   if not trusted or trusted['sha256']!=rec['sha256'] or s.st_size!=trusted['bytes'] or s.st_mtime_ns!=trusted['mtime_ns']:raise ValueError('Frozen model changed; fresh full-hash preflight required: '+str(p))
  elif file_sha(p)!=rec['sha256']:raise ValueError('Dependency changed: '+str(p))
 return c,digest(canonical(c))
def encode(obj):
 tensors={};inventory=[]
 def visit(x,path):
  if type(x) is torch.Tensor:
   if x.layout!=torch.strided or x.is_nested:raise TypeError('Unsupported tensor layout')
   name='t'+str(len(tensors));cpu=x.detach().cpu().contiguous().clone();tensors[name]=cpu
   inventory.append({'key':name,'path':path,'dtype':str(x.dtype),'shape':list(x.shape),'device':str(x.device),'bytes':x.numel()*x.element_size(),'sha256':digest(cpu.reshape(-1).view(torch.uint8).numpy().tobytes())})
   return {'type':'tensor','key':name,'device':str(x.device)}
  if type(x) is NestedTensor:return {'type':'nested_av','items':[visit(v,path+'.stream'+str(i))for i,v in enumerate(x.unbind())]}
  if type(x) in (list,tuple):return {'type':type(x).__name__,'items':[visit(v,path+'.'+str(i))for i,v in enumerate(x)]}
  if type(x) is dict:
   if not all(type(k) is str for k in x):raise TypeError('Only string metadata keys accepted')
   return {'type':'dict','items':[[k,visit(v,path+'.'+k)]for k,v in x.items()]}
  if x is None or type(x) in (bool,int,str):return {'type':'primitive','value':x}
  if type(x) is float and math.isfinite(x):return {'type':'primitive','value':x}
  raise TypeError('Unknown object at '+path+': '+str(type(x)))
 return visit(obj,'output'),tensors,inventory
def decode(tree,tensors,restore_device=True):
 def visit(n):
  kind=n['type']
  if kind=='tensor':
   t=tensors[n['key']]
   return t.to(n['device']) if restore_device else t
  if kind=='primitive':
   v=n['value']
   if v is None or type(v)in(bool,int,str)or(type(v)is float and math.isfinite(v)):return v
   raise TypeError('Invalid primitive')
  if kind=='dict':return {k:visit(v)for k,v in n['items']}
  if kind=='list':return [visit(v)for v in n['items']]
  if kind=='tuple':return tuple(visit(v)for v in n['items'])
  if kind=='nested_av':return NestedTensor([visit(v)for v in n['items']])
  raise TypeError('Unknown tree tag')
 return visit(tree)
def load(text,restore_device=True):
 c,key=verified_contract(text);folder=ROOT/key
 manifest=json.loads((folder/'manifest.json').read_text())
 if manifest['schema']!=SCHEMA or manifest['key']!=key or manifest['contract']!=c:raise ValueError('Cache contract mismatch')
 for name in ('tensors.safetensors','metadata.json'):
  if file_sha(folder/name)!=manifest['files'][name]:raise ValueError('Cache corruption: '+name)
 meta=json.loads((folder/'metadata.json').read_text());tensors=load_bytes((folder/'tensors.safetensors').read_bytes())
 if set(tensors)!=set(v['key']for v in meta['inventory']):raise ValueError('Tensor count mismatch')
 for rec in meta['inventory']:
  t=tensors[rec['key']]
  if str(t.dtype)!=rec['dtype'] or list(t.shape)!=rec['shape'] or digest(t.reshape(-1).view(torch.uint8).numpy().tobytes())!=rec['sha256']:raise ValueError('Tensor mismatch')
 return decode(meta['tree'],tensors,restore_device),meta,manifest
def save(obj,text):
 c,key=verified_contract(text);tree,tensors,inventory=encode(obj)
 ROOT.mkdir(parents=True,exist_ok=True);final=ROOT/key
 if final.exists():
  restored,meta,manifest=load(text)
  if meta['tree']!=tree or meta['inventory']!=inventory:raise ValueError('Existing input-key yields different output; fail closed')
  return restored,meta,manifest
 temp=ROOT/('.tmp-'+uuid.uuid4().hex);temp.mkdir()
 save_file(tensors,str(temp/'tensors.safetensors'))
 meta={'schema':SCHEMA,'tree':tree,'inventory':inventory,'tensor_count':len(tensors),'tensor_bytes':sum(v['bytes']for v in inventory)}
 (temp/'metadata.json').write_bytes(canonical(meta))
 manifest={'schema':SCHEMA,'key':key,'contract':c,'files':{name:file_sha(temp/name)for name in ('tensors.safetensors','metadata.json')}}
 (temp/'manifest.json').write_bytes(canonical(manifest))
 # Validate complete staged payload before making it visible by a same-volume rename.
 reread=load_file(str(temp/'tensors.safetensors'),device='cpu')
 assert set(reread)==set(tensors)
 for name,t in tensors.items():assert torch.equal(t,reread[name]) and t.dtype==reread[name].dtype
 for name in ('tensors.safetensors','metadata.json','manifest.json'):
  with (temp/name).open('r+b') as durable:os.fsync(durable.fileno())
 os.rename(temp,final)
 return load(text)
def equivalent(a,b):
 ta,sa,ia=encode(a);tb,sb,ib=encode(b)
 assert ta==tb and ia==ib,'Type/metadata/device/dtype/shape/hash mismatch'
 for k in sa:assert torch.equal(sa[k],sb[k]),k
 return {'CONDITIONING_EQUIVALENCE':'PASS','CONDITIONING_NUMERIC_EQUAL':True,'max_abs_diff':0,'mean_abs_diff':0,'tensor_count':len(sa),'tensor_bytes':sum(t.numel()*t.element_size()for t in sa.values()),'inventory':ia,'output_hash':digest(canonical({'tree':ta,'inventory':ia}))}
