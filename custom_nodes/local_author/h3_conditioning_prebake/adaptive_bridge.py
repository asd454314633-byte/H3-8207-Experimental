"""Production host bridge for the proven pure V1 core. Never queues or cancels jobs."""
import json,time,threading
from pathlib import Path
from .adaptive_v1 import Metadata,TaskSnapshot,RecoveryEngine,AssetResolver,MappingStore,WorkflowVersionStore,verify_native,file_sha
LOCK=threading.RLock()

def root():
 import folder_paths
 return Path(folder_paths.get_output_directory())/'h3_adaptive_v1'

def metadata(graph):
 import nodes
 result={}
 for kind in {n['class_type'] for n in graph.values()}:
  cls=nodes.NODE_CLASS_MAPPINGS.get(kind)
  if cls is None:continue
  if hasattr(cls,'GET_NODE_INFO_V1'):result[kind]=cls.GET_NODE_INFO_V1()
  else:result[kind]={'input':cls.INPUT_TYPES(),'output':list(cls.RETURN_TYPES),'output_node':bool(getattr(cls,'OUTPUT_NODE',False))}
 return Metadata(json.loads(json.dumps(result)))

def snapshot_path(pid):
 import uuid
 uuid.UUID(pid)
 return root()/'tasks'/(pid+'.json')

def capture(pid,graph,receipt):
 path=snapshot_path(pid)
 if path.exists():return TaskSnapshot.load(path)
 snapshot=TaskSnapshot.create(pid,graph,metadata(graph),receipt)
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f:json.dump(snapshot.__dict__,f,ensure_ascii=False)
 return snapshot

def graph_matches(attempt,graph):
 path=snapshot_path(attempt['prompt_id'])
 if not path.exists():return False
 from .adaptive_v1.core import analyze
 snapshot=TaskSnapshot.load(path)
 return analyze(graph,Metadata(json.loads(snapshot.metadata_json))).semantic_version==snapshot.semantic_version

def recovery(ctx,index,entry,server):
 import folder_paths
 pid=entry.get('attempt',{}).get('prompt_id') or entry.get('prompt_id')
 if not pid:return None
 path=snapshot_path(pid)
 if not path.exists():return None # No invented legacy submission snapshot.
 with LOCK:
  snapshot=TaskSnapshot.load(path)
  receipt=json.loads(snapshot.receipt_json)
  if any(receipt.get(k)!=ctx.get(k) for k in ('project_id','group_id')):raise ValueError('Adaptive snapshot owner mismatch')
  if receipt.get('revision')!=entry.get('revision') or receipt.get('cache_key')!=entry.get('cache_key'):return None
  history=server.prompt_queue.get_history(prompt_id=pid).get(pid)
  source='LIVE_HISTORY'
  if not history:
   archive=root()/'history'/(pid+'.json');proof=archive.with_suffix('.sha256')
   if not archive.is_file() or not proof.is_file() or file_sha(archive)!=proof.read_text().strip():return None
   history=json.loads(archive.read_text(encoding='utf-8'));source='VERIFIED_ARCHIVED_HISTORY'
  native_root=Path(folder_paths.get_output_directory())/'h3_continuation'/ctx['project_id']
  native_index=json.loads((native_root/'index.json').read_text(encoding='utf-8'))
  candidates=[x for x in native_index['segments'] if x.get('prompt_id')==pid and int(x.get('segment_index',-1))==int(index)]
  if len(candidates)!=1:raise ValueError('Adaptive Native receipt owner not unique')
  native=verify_native(candidates[0],native_root,pid)
  start=time.perf_counter()
  engine=RecoveryEngine(mappings=MappingStore(root()/'mapping.json'),versions=WorkflowVersionStore(root()/'versions'))
  result=engine.recover(snapshot,history,AssetResolver({'output':folder_paths.get_output_directory()}),native_receipt=native)
  result.update(segment_index=int(index),history_source=source,handler_ms=(time.perf_counter()-start)*1000,receipt_policy='ORIGINAL_NATIVE_AND_LEGACY_RECEIPTS_UNCHANGED')
  (root()/'events').mkdir(parents=True,exist_ok=True)
  with (root()/'events/recovery.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'at':time.time(),'result':result},ensure_ascii=False)+'\n')
  return result
