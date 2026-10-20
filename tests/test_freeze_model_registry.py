import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('registry_setup',ROOT/'scripts/setup/freeze_model_registry.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Registry(unittest.TestCase):
 def test_actual_file_hashes_and_previous_registry_preserved(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);models={}
   for role in mod.ROLES:
    p=root/(role+'.fixture');p.write_bytes(('synthetic hash fixture '+role).encode());models[role]=p
   registry=root/'model_registry.json';registry.write_text('[]');rows=mod.freeze(models,registry)
   self.assertEqual(json.loads(registry.read_text()),rows);self.assertEqual(next(root.glob('model_registry.json.before_*')).read_text(),'[]')
   for row in rows:self.assertEqual(row['sha256'],hashlib.sha256(Path(row['path']).read_bytes()).hexdigest().upper())
 def test_missing_role_rejected_before_write(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'registry.json'
   with self.assertRaises(ValueError):mod.freeze({},p)
   self.assertFalse(p.exists())
if __name__=='__main__':unittest.main()
