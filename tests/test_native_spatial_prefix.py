import ast,copy,hashlib,importlib.util,json,sys,tempfile,types
from pathlib import Path
import torch
from safetensors.torch import save_file,load_file
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--host',required=True);parser.add_argument('--results');options=parser.parse_args()
R=Path(__file__).resolve().parents[1];HOST=Path(options.host).resolve()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
core=module('spatial_core',R/'custom_nodes/local_author/H3_NativeContinuation/core.py');core.feature_detect=lambda:{}
nt=module('offline_nested',HOST/'comfy/nested_tensor.py').NestedTensor
def extract(path,names,scope):
 tree=ast.parse(path.read_text('utf-8'));nodes=[n for n in tree.body if getattr(n,'name',None) in names];exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope);return scope
ns={'core':core,'json':json,'NestedTensor':nt,'CATEGORY':'test','PROVIDER_ID':core.PROVIDER_ID,'VIDEO_PREFIX_FRAMES':core.VIDEO_PREFIX_FRAMES,'BRANCH_GENERATED_AUDIO':core.BRANCH_GENERATED_AUDIO}
extract(R/'custom_nodes/local_author/H3_NativeContinuation/nodes.py',['_unpack_av','_pack_av','H3ContinuationPrepare'],ns)
rows=[]
def case(name,fn):
 try:fn();rows.append({'name':name,'result':'PASS'})
 except Exception:
  import traceback;rows.append({'name':name,'result':'FAIL','trace':traceback.format_exc()})
 print(name,rows[-1]['result'],flush=True)
with tempfile.TemporaryDirectory(prefix='h3-spatial-zero-gpu-') as temp:
 fp=types.ModuleType('folder_paths');fp.get_output_directory=lambda:temp;sys.modules['folder_paths']=fp
 records=[];codec=types.SimpleNamespace(file_sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest().upper(),equivalent=lambda a,b:{'test':'same_inputs'})
 audit={'json':json,'Path':Path,'codec':codec,'residency':lambda _: {},'record':lambda kind,data:records.append(data),'module_at':lambda _:types.SimpleNamespace(core=core)}
 extract(R/'custom_nodes/local_author/h3_conditioning_prebake/nodes.py',['H3PreBakeContinuationAudit'],audit)
 prior_path=Path(temp)/'h3_continuation/CPU/seg_00000.safetensors';prior_path.parent.mkdir(parents=True)
 def run(source=(66,38),target=(60,34),dtype=torch.float32):
  torch.manual_seed(17)
  pv=torch.randn(1,24,57,*source,dtype=dtype);pa=torch.randn(1,32,2,320,dtype=dtype)
  video=torch.randn(1,24,57,*target,dtype=dtype);audio=torch.randn(1,32,2,320,dtype=dtype)
  before=video.clone();abefore=audio.clone();old=pv.clone();save_file({'video':pv,'audio':pa},str(prior_path))
  output,plan,*_=ns['H3ContinuationPrepare']().run(ns['_pack_av'](video,audio),True,'CPU',1,prev_latent=ns['_pack_av'](pv,pa))
  p=json.loads(plan);v,a=output['samples'].unbind();vt=p['video_prefix_tokens'];at=p['audio_prefix_steps']
  audit['H3PreBakeContinuationAudit']().audit([],output,'CPU',1,plan)
  assert torch.equal(v[:,:,vt:],before[:,:,vt:]) and torch.equal(a[...,at:],abefore[...,at:])
  assert torch.equal(a[...,:at],pa[...,-at:]) and torch.equal(pv,old)
  assert tuple(v.shape)==tuple(video.shape)
  return output,p,pv,pa
 case('ACTUAL_NATIVE_PREPARE_608x1056_TO_544x960_AND_AUDIT',run)
 case('UPSCALE_GRID_WITH_TARGET_SAMPLING_SHAPE',lambda:run((60,34),(66,38)))
 case('BF16_CPU_MAPPING_AND_AUDIO_EXACT',lambda:run(dtype=torch.bfloat16))
 def same():
  out,p,pv,pa=run((60,34),(60,34));v,a=out['samples'].unbind();assert p['video_prefix_transform'] is None;assert torch.equal(v[:,:,:12],pv[:,:,-12:]);assert records[-1]['previous_video_tail_equal']
 case('SAME_GRID_ORIGINAL_EXACT_PATH',same)
 def tamper():
  out,p,_,_=run();out['samples'].unbind()[0][0,0,0,0,0]+=1
  try:audit['H3PreBakeContinuationAudit']().audit([],out,'CPU',1,json.dumps(p))
  except AssertionError:return
  raise AssertionError('Tampered prefix accepted')
 case('MAPPED_PREFIX_CORRUPTION_REJECTED',tamper)
 def forged():
  out,p,_,_=run();p['video_prefix_transform']['method']='nearest'
  try:audit['H3PreBakeContinuationAudit']().audit([],out,'CPU',1,json.dumps(p))
  except ValueError:return
  raise AssertionError('Forged transform accepted')
 case('FORGED_TRANSFORM_REJECTED',forged)
 def unmarked():
  out,p,_,_=run();p.pop('video_prefix_transform')
  try:audit['H3PreBakeContinuationAudit']().audit([],out,'CPU',1,json.dumps(p))
  except AssertionError:return
  raise AssertionError('Unmarked changed grid accepted')
 case('UNMARKED_RESAMPLE_NOT_EXACT_CONTINUATION',unmarked)
 def noinherit(clean=False):
  v=torch.zeros(1,24,57,60,34);a=torch.zeros(1,32,2,320);latent=ns['_pack_av'](v,a)
  out,plan,*_=ns['H3ContinuationPrepare']().run(latent,clean,'CPU',3,clean_rebase_enabled=clean,clean_rebase_segment=3)
  assert out is latent and 'noise_mask' not in out and not json.loads(plan).get('video_prefix_transform')
 case('INDEPENDENT_PATH_UNCHANGED',noinherit);case('CLEAN_REBASE_PATH_UNCHANGED',lambda:noinherit(True))
 def wrong():
  try:core.adapt_video_prefix(torch.zeros(1,25,57,66,38),(1,24,57,60,34),12,torch.float32)
  except ValueError:return
  raise AssertionError('Wrong channel identity accepted')
 case('WRONG_MODEL_CHANNELS_REJECTED',wrong)
 def official():
  scope={'torch':torch};extract(HOST/'comfy/utils.py',['common_upscale'],scope)
  previous=torch.randn(2,24,17,66,38)
  actual,_=core.adapt_video_prefix(previous,(2,24,57,60,34),12,torch.float32)
  expected=scope['common_upscale'](previous[:,:,-12:],34,60,'bilinear','disabled')
  assert torch.equal(actual,expected)
 case('OFFICIAL_CORE_LATENT_UPSCALE_EQUIVALENCE',official)
assert not torch.cuda.is_initialized()
if options.results:Path(options.results).write_text(json.dumps({'cuda_initialized':False,'gpu_submissions':0,'cases':rows},indent=2),encoding='utf-8')
assert all(r['result']=='PASS' for r in rows)
