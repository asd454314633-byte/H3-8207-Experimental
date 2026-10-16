"""Dependency-free tests of the actual published timeline and pre-GPU start gates."""
import ast,json,math,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'custom_nodes/local_author/H3_LongSong'
def functions(file,names,namespace):
 tree=ast.parse((ROOT/file).read_text('utf-8'))
 selected=ast.Module(body=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names],type_ignores=[])
 exec(compile(selected,str(ROOT/file),'exec'),namespace)
 return namespace
N=functions('nodes.py',{'interval'},{'math':math})
C=functions('cross_group.py',{'check_requested_start','graph_contract','verify_graph'},{'math':math,'json':json})
class TimelineTests(unittest.TestCase):
 def test_independent_then_native_and_rebase(self):
  first=N['interval'](243,0,0,52)
  second=N['interval'](243,243,39,52)
  self.assertEqual(first['output_end'],second['output_start'])
  self.assertEqual(second['source_start'],60.5)
  self.assertEqual(second['kept_frames'],204)
  rebase=N['interval'](243,447,0,52)
  self.assertEqual(rebase['source_start'],rebase['output_start'])
  self.assertEqual(rebase['kept_frames'],243)
 def test_cross_group_39_once(self):
  plan=N['interval'](362,0,39,82.375,external_first=True)
  self.assertEqual(plan['source_start'],80.75)
  self.assertEqual(plan['output_start'],82.375)
  self.assertEqual(plan['kept_frames'],323)
  self.assertAlmostEqual(plan['output_end'],95.83333333333333)
  self.assertEqual(plan['source_end'],plan['output_end'])
 def test_invalid_grid_prefix_and_origin(self):
  for args in [(360,0,0,0),(243,0,39,0),(243,243,38,0),(243,0,0,-1),(243,0,0,float('nan'))]:
   with self.subTest(args=args),self.assertRaises(ValueError):N['interval'](*args)
 def test_cross_start_requires_continuous_and_matching_origin(self):
  proof={'global_boundary':82.375,'song_start':0}
  for value,origin,continuous,independent in [(0,'首段提示词',True,False),(52,'起始秒设置',True,False),(82.375,'首段提示词',False,False),(82.375,'首段提示词',True,True)]:
   with self.subTest(value=value,origin=origin),self.assertRaises(ValueError):C['check_requested_start'](proof,value,origin,continuous,independent)
  C['check_requested_start'](proof,82.375,'首段提示词',True,False)
  C['check_requested_start'](proof,0,'起始秒设置',True,False)
 def test_removed_binding_rejected_before_gpu(self):
  with self.assertRaises(ValueError):C['verify_graph']({}, {'project_id':'synthetic'},0,prepared={'schema':'synthetic'})
  with self.assertRaises(ValueError):C['verify_graph']({'CROSS_GROUP_PREVIOUS':{}},{'project_id':'synthetic'},0)
  self.assertIsNone(C['verify_graph']({}, {'project_id':'synthetic'},0))
if __name__=='__main__':unittest.main()
