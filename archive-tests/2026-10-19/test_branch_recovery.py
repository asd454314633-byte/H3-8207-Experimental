from pathlib import Path
import copy, importlib, json, sys, tempfile, types, unittest

ROOT=Path(r"D:\H3导演台项目目录\_parallel_v29_chinese_ui_8207\runtime")
sys.path.insert(0,str(ROOT))
PKG="_prebake_branch_recovery_test";pkg=types.ModuleType(PKG);pkg.__path__=[str(ROOT/"custom_nodes/h3_conditioning_prebake")];sys.modules[PKG]=pkg
P=importlib.import_module(PKG+".production"); E=importlib.import_module(PKG+".execution_state"); L=importlib.import_module(PKG+".attempt_lifecycle")

class BranchRecoveryTests(unittest.TestCase):
 def test_successful_fork_separates_parent_attempt_and_preserves_receipt(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td); out=root/"output"; source={"story_id":"S","project_id":"PARENT","group_id":"G","execution_version":"v-parent","start_index":0,"start_mode":"independent","revisions":[1,0,0,0,0,0],"cache_keys":["k",None,None,None,None,None]}
   parent_dir=out/"h3_continuation"/"PARENT";parent_dir.mkdir(parents=True);(parent_dir/"seg_00000.safetensors").write_bytes(b"latent")
   parent_attempt={"attempt_id":"aid","project_id":"PARENT","group_id":"G","execution_version":"v-parent","revision":1,"cache_key":"k","status":"SUCCESS","prompt_id":"pid"}
   (out/"video.mp4").parent.mkdir(parents=True,exist_ok=True);(out/"video.mp4").write_bytes(b"video")
   receipt={**parent_attempt,"status":"SUCCESS","latent_sha256":"sha","video_sha256":"sha","video_path":str(out/"video.mp4")}
   (parent_dir/"six_acceptance.json").write_text(json.dumps({"0":receipt}),encoding="utf-8")
   (parent_dir/"index.json").write_text(json.dumps({"segments":[]}),encoding="utf-8")
   ledger={"project_id":"PARENT","group_id":"G","execution":source,"segments":{"0":{"video_status":"SUCCESS","receipt_status":"SUCCESS","attempt":copy.deepcopy(parent_attempt),"revision":1,"cache_key":"k","latent_sha256":"sha","prompt_id":"pid"}}}
   old_registry=P.story_registry;old_ledger=P.ledger_path;old_verify=P.verify_predecessor;old_sha=P.codec.file_sha
   P.story_registry=lambda:root/"registry.json";P.ledger_path=lambda ctx:out/"h3_continuation"/ctx["project_id"]/"prebake_G.json";P.verify_predecessor=lambda *a,**k:None;P.codec.file_sha=lambda path:"sha"
   try:
    binding,child=E.fork(source,ledger)
    entry=child["segments"]["0"];saved=json.loads((P.ledger_path(binding).parent/"six_acceptance.json").read_text(encoding="utf-8"))["0"]
    self.assertEqual(ledger["segments"]["0"]["attempt"],parent_attempt)
    self.assertNotIn("attempt",entry);self.assertEqual(entry["inherited_attempt"],parent_attempt)
    self.assertEqual(entry["video_status"],"SUCCESS");self.assertEqual(saved["status"],"SUCCESS")
    self.assertEqual(saved["attempt_id"],"aid");self.assertEqual(saved["prompt_id"],"pid")
    self.assertEqual(saved["inherited_from"]["execution_version"],"v-parent")
    self.assertEqual(saved["latent_path"],str(P.ledger_path(binding).parent/"seg_00000.safetensors"))
   finally:P.story_registry=old_registry;P.ledger_path=old_ledger;P.verify_predecessor=old_verify;P.codec.file_sha=old_sha

 def test_tick_skips_mismatched_copy_once_and_recovers_owner_branch(self):
  manager=L.AttemptManager(types.SimpleNamespace(),None,None); calls=[]
  parent={"story_id":"S","project_id":"PARENT","group_id":"G","execution_version":"v-parent"};child={"story_id":"S","project_id":"CHILD","group_id":"G","execution_version":"v-child"}
  entries={"PARENT":{"segments":{"0":{"attempt":{"attempt_id":"a","project_id":"PARENT","group_id":"G","execution_version":"v-parent","status":"PENDING"}}}},"CHILD":{"segments":{"0":{"attempt":{"attempt_id":"a","project_id":"PARENT","group_id":"G","execution_version":"v-parent","status":"SUCCESS"}}}}}
  old_bindings=P.execution_state.bindings;old_read=P.read_state;old_recover=manager.recover
  P.execution_state.bindings=lambda:[parent,child];P.read_state=lambda path:entries[Path(path).parts[-2]];manager.recover=lambda project,index:calls.append(project)
  try:
   import asyncio,logging
   with self.assertLogs(level="ERROR") as logs:asyncio.run(manager.tick());asyncio.run(manager.tick())
   self.assertEqual(calls,["PARENT","PARENT"]);self.assertEqual(len([x for x in logs.output if "identity does not belong" in x]),1)
  finally:P.execution_state.bindings=old_bindings;P.read_state=old_read;manager.recover=old_recover

if __name__=="__main__":unittest.main(verbosity=2)
