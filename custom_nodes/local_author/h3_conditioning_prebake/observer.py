"""Temporary read-only per-file logical I/O and light resource observer; no model lifecycle edits."""
import ctypes,functools,json,os,threading,time
from pathlib import Path
import psutil,torch
import comfy_aimdo.host_buffer as hb
from aiohttp import web
from server import PromptServer
from comfy_execution.utils import get_executing_context
import sys
R=Path(__file__).resolve().parent
STATE=None;NODE=None;STEP=None;LOCK=threading.RLock();STOP=False;ORIGINALS=[]
NODE_CLASS_MAPPINGS={}
def memory():
 for module in tuple(sys.modules.values()):
  if str(getattr(module,'__file__','')).replace('\\','/').endswith('/h3_te_residency_probe/__init__.py'):
   return module._windows_memory()
 raise RuntimeError('Shared memory observer absent')
def filename(file):
 if not isinstance(file,int):return os.path.abspath(str(file.name))
 k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetFinalPathNameByHandleW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32]
 b=ctypes.create_unicode_buffer(32768)
 return b.value.removeprefix('\\\\?\\') if k.GetFinalPathNameByHandleW(file,b,len(b),0) else None
def read(file,offset,size,kind):
 if STATE is None:return
 name=filename(file)
 if not name or os.path.normcase(os.path.abspath(name))!=os.path.normcase(STATE['checkpoint']):return
 ctx=get_executing_context()
 with LOCK:
  STATE['reads'].append({'epoch':time.time(),'file':name,'offset':int(offset),'bytes':int(size),'kind':kind,'prompt_id':ctx.prompt_id if ctx else None,'node_id':ctx.node_id if ctx else NODE,'step':STEP})
def wrap(obj,name,make):
 old=getattr(obj,name);new=make(old);setattr(obj,name,new);ORIGINALS.append((obj,name,old,new))
def host(old):
 @functools.wraps(old)
 def call(self,file_obj,file_offset,size,*args,**kw):
  value=old(self,file_obj,file_offset,size,*args,**kw);read(file_obj,file_offset,size,'HostBuffer.read_file_slice');return value
 return call
def gpu(old):
 @functools.wraps(old)
 def call(file_obj,file_offset,size,*args,**kw):
  value=old(file_obj,file_offset,size,*args,**kw);read(file_obj,file_offset,size,'read_file_to_device');return value
 return call
def events(old):
 @functools.wraps(old)
 def call(event,data,*args,**kw):
  global NODE,STEP
  if STATE is not None:
   if event=='executing':NODE=str(data.get('node'));STEP=None
   if event=='progress':STEP=data.get('value')
   if event in ('execution_start','executing','progress','execution_success','execution_error','execution_interrupted'):
    with LOCK:STATE['events'].append({'epoch':time.time(),'event':event,'data':data})
  return old(event,data,*args,**kw)
 return call
def exported():
 with LOCK:return {'armed':False,'pid':os.getpid()} if STATE is None else json.loads(json.dumps(STATE))
def loop():
 while not STOP:
  time.sleep(1)
  if STATE is None:continue
  try:
   row={'epoch':time.time(),'node':NODE,'step':STEP,'memory':memory(),'process_io':psutil.Process().io_counters()._asdict(),'disks':{k:v._asdict() for k,v in psutil.disk_io_counters(perdisk=True).items()}}
   if torch.cuda.is_initialized():
    free,total=torch.cuda.mem_get_info();row['vram_used_bytes']=total-free
   with LOCK:
    if STATE is not None:STATE['samples'].append(row)
  except Exception as ex:
   if STATE is not None:STATE.setdefault('monitor_errors',[]).append(str(ex))
@PromptServer.instance.routes.post('/h3_prebake_observer/arm')
async def arm(request):
 global STATE,NODE,STEP
 if STATE is not None:raise web.HTTPConflict()
 data=await request.json();checkpoint=str(Path(data['checkpoint']).resolve())
 if Path(checkpoint).name not in ('minimax_h3_ref2va_pruned_int8_convrot.safetensors','minimax_h3_ref2va_pruned_nvfp4.safetensors'):raise web.HTTPBadRequest()
 STATE={'checkpoint':checkpoint,'label':data['label'],'pid':os.getpid(),'epoch':time.time(),'reads':[],'events':[],'samples':[]};NODE=STEP=None
 return web.json_response({'armed':True,'pid':os.getpid()})
@PromptServer.instance.routes.get('/h3_prebake_observer/status')
async def status(request):return web.json_response(exported())
@PromptServer.instance.routes.post('/h3_prebake_observer/disarm')
async def disarm(request):
 global STATE
 value=exported();STATE=None;return web.json_response(value)
@PromptServer.instance.routes.post('/h3_prebake_observer/uninstall')
async def uninstall(request):
 global STATE,STOP
 STOP=True;STATE=None;conflicts=[]
 for obj,name,old,new in reversed(ORIGINALS):
  if getattr(obj,name) is new:setattr(obj,name,old)
  else:conflicts.append(name)
 return web.json_response({'restored':not conflicts,'conflicts':conflicts})
wrap(hb.HostBuffer,'read_file_slice',host);wrap(hb,'read_file_to_device',gpu);wrap(PromptServer.instance,'send_sync',events)
threading.Thread(target=loop,daemon=True).start()
