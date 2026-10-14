"""CPU-only checks for publication redaction and exact latent acceptance.
Fake tensor headers exercise identity rules without loading tensors or starting a service.
"""
from pathlib import Path
import importlib.util,json,hashlib,sys,tempfile,types,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
S=load('public_sanitize','scripts/sanitize/sanitize_workflows.py')
R=load('six_receipts','custom_nodes/local_author/H3_Prompt_Sidecar/six_resume.py')
class FakeHeader:
 def __init__(self,prompt):self.prompt=prompt
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def metadata(self):return {'provider':R.PROVIDER,'segment_index':'0','prompt_id':self.prompt}
 def get_slice(self,key):return types.SimpleNamespace(get_shape=lambda:[1,1,12,1,65] if key=='video' else [1,1,65])
class ReleaseGuards(unittest.TestCase):
 def test_nested_short_private_text_and_media(self):
  original={'nodes':[{'id':1,'type':'PrimitiveStringMultiline','inputs':[],'outputs':[],'widgets_values':['私密裸体剧情']},{'id':2,'type':'LoadImage','widgets_values':['private-person-reference.png']}],'links':[], 'extra':{'nested':json.dumps({'prompt':'naked scene','preview':'data:image/png;base64,AAAA'})}}
  log=[];public=S.sanitize(original,log)
  self.assertEqual(S.graph_contract(original),S.graph_contract(public))
  self.assertNotIn('private-person-reference',json.dumps(public))
  self.assertFalse(any(p.search(s) for _,s in S.strings(public) for p in S.PAT.values()))
 def test_interface_description_is_not_private_dialogue(self):
  self.assertFalse(S.PAT['adult'].search('导演接口交互'))
 def test_named_prompt_on_subgraph_wrapper_is_neutralized(self):
  original={'nodes':[{'id':1,'type':'synthetic-subgraph-id','widgets_values':['private diary line'], 'widgets_values_named':{'prompt':'private diary line'}}], 'links':[]}
  public=S.sanitize(original,[])
  self.assertEqual(public['nodes'][0]['widgets_values'],[S.NEUTRAL])
  self.assertEqual(public['nodes'][0]['widgets_values_named']['prompt'],S.NEUTRAL)
  self.assertEqual(S.graph_contract(original),S.graph_contract(public))
 def inspect(self,receipt=True,receipt_prompt='p1',metadata_prompt='p1',ledger_prompt='p1',tamper=False,require=True):
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp)/'h3_continuation'/'sample';d.mkdir(parents=True);latent=d/'seg_00000.safetensors';latent.write_bytes(b'synthetic-header')
   (d/'index.json').write_text(json.dumps({'provider':R.PROVIDER,'segments':[{'segment_index':0,'provider':R.PROVIDER,'prompt_id':ledger_prompt}]}))
   if receipt:
    (d/'six_acceptance.json').write_text(json.dumps({'0':{'status':'SUCCESS','prompt_id':receipt_prompt,'latent_sha256':hashlib.sha256(latent.read_bytes()).hexdigest()}}))
   if tamper:latent.write_bytes(b'changed-header')
   fake=types.SimpleNamespace(safe_open=lambda *a,**k:FakeHeader(metadata_prompt))
   with patch.dict(sys.modules,{'safetensors':fake}):return R.inspect_segment(tmp,'sample',0,require_accepted=require)
 def test_missing_receipt_rejected(self):
  with self.assertRaises(ValueError):self.inspect(receipt=False)
 def test_stale_metadata_rejected(self):
  with self.assertRaises(ValueError):self.inspect(metadata_prompt='stale')
 def test_stale_ledger_rejected(self):
  with self.assertRaises(ValueError):self.inspect(ledger_prompt='stale')
 def test_tampered_latent_rejected(self):
  with self.assertRaises(ValueError):self.inspect(tamper=True)
 def test_exact_receipt_accepted(self):self.assertTrue(self.inspect()['accepted'])
 def test_header_inspection_does_not_mint_acceptance(self):self.assertFalse(self.inspect(receipt=False,require=False)['accepted'])
if __name__=='__main__':unittest.main()
