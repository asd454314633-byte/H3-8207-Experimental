"""Synthetic CPU regressions of the actual recovery functions; no service/GPU."""
import ast,copy,hashlib,json,tempfile,types,unittest
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]/'custom_nodes/local_author/h3_conditioning_prebake'
def extract(path,name,nested=None):
 tree=ast.parse(path.read_text('utf-8'))
 if nested:tree=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==nested)
 fn=copy.deepcopy(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name))
 fn.body=[n for n in fn.body if not isinstance(n,ast.ImportFrom)]
 return compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec')
clean=lambda g:{k:{'class_type':n['class_type'],'inputs':copy.deepcopy(n['inputs'])} for k,n in g.items()}
digest=lambda g:hashlib.sha256(json.dumps(clean(g),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
class Recovery(unittest.TestCase):
 def test_history_handoff_keeps_identity_until_published(self):
  manager=types.SimpleNamespace(executing_items={1:'test-task'},executing_pids={'test-task'})
  during=[]
  def original(*a,**kw):during.append('test-task' in manager.executing_pids);return 'published'
  scope={'manager':manager,'_orig_done':original}
  exec(extract(PACKAGE/'attempt_lifecycle.py','_traced_done','install'),scope)
  self.assertEqual(scope['_traced_done'](1),'published');self.assertEqual(during,[True]);self.assertFalse(manager.executing_pids)
 def test_failed_history_write_does_not_erase_liveness(self):
  manager=types.SimpleNamespace(executing_items={1:'test-task'},executing_pids={'test-task'})
  def original(*a,**kw):raise RuntimeError('synthetic write failure')
  scope={'manager':manager,'_orig_done':original};exec(extract(PACKAGE/'attempt_lifecycle.py','_traced_done','install'),scope)
  with self.assertRaises(RuntimeError):scope['_traced_done'](1)
  self.assertIn('test-task',manager.executing_pids)
 def test_only_declared_float_coercions_are_equivalent(self):
  original={'A':{'class_type':'Fixture','inputs':{'fps':24,'frame':39,'text':'synthetic prompt','link':['B',0]}},'B':{'class_type':'Fixture','inputs':{}}}
  metadata={'Fixture':{'input':{'required':{'fps':['FLOAT',{}],'frame':['INT',{}],'text':['STRING',{}],'link':['CONDITIONING',{}]}}}}
  snapshot=types.SimpleNamespace(graph_json=json.dumps(original),metadata_json=json.dumps(metadata));attempt={'prompt_id':'synthetic-task','graph_sha256':digest(original)}
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'snapshot.json';path.write_text('{}')
   scope={'json':json,'p':types.SimpleNamespace(clean_graph=clean,graph_digest=digest),'snapshot_path':lambda pid:path,'TaskSnapshot':types.SimpleNamespace(load=lambda p:snapshot)}
   exec(extract(PACKAGE/'adaptive_bridge.py','history_graph_matches'),scope);check=scope['history_graph_matches']
   history=copy.deepcopy(original);history['A']['inputs']['fps']=24.0
   self.assertTrue(check(attempt,history))
   for key,value in [('fps',25.0),('frame',39.0),('text','changed'),('link',['B',1])]:
    bad=copy.deepcopy(history);bad['A']['inputs'][key]=value;self.assertFalse(check(attempt,bad),(key,value))
   bad=dict(attempt,graph_sha256='0'*64);self.assertFalse(check(bad,history))
if __name__=='__main__':unittest.main()
