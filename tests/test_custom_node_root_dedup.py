import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('dedup_patch',ROOT/'runtime_patches/dedup_custom_nodes.py');patch=importlib.util.module_from_spec(spec);spec.loader.exec_module(patch)
class Dedup(unittest.TestCase):
 def test_same_directory_once_and_different_directory_retained(self):
  import os
  for base,source,count in [('X:/lab','X:/lab/folder_paths.py',1),('X:/assets','X:/source/folder_paths.py',2)]:
   scope={'os':os,'base_path':base,'__file__':source,'folder_names_and_paths':{}}
   exec(patch.NEW,scope);self.assertEqual(len(scope['folder_names_and_paths']['custom_nodes'][0]),count)
 def test_known_upstream_single_root_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'folder_paths.py';p.write_text(patch.SINGLE,encoding='utf-8');raw=p.read_bytes();patch.apply(root)
   self.assertEqual(raw,p.read_bytes());self.assertFalse((root/'folder_paths.py.pre_closeout20261020').exists())
 def test_backed_up_and_idempotent(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'folder_paths.py';p.write_text(patch.OLD,encoding='utf-8');raw=p.read_bytes()
   patch.apply(root);first=p.read_bytes();patch.apply(root)
   self.assertEqual(first,p.read_bytes());self.assertEqual(raw,(root/'folder_paths.py.pre_closeout20261020').read_bytes())
if __name__=='__main__':unittest.main()
