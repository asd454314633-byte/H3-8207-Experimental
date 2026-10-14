"""Offline publication checks for tracked/exported files, provenance hashes and nested workflows.
This is a static check; it never asserts GPU/runtime acceptance.
"""
from pathlib import Path
import subprocess,json,hashlib,sys,importlib.util
PKG=Path(__file__).resolve().parents[2]
def files():
 if (PKG/'.git').is_dir():
  return [PKG/x for x in subprocess.check_output(['git','-C',str(PKG),'ls-files','-z']).decode().strip('\0').split('\0') if x]
 return [f for f in PKG.rglob('*') if f.is_file() and not any(x in ('.git','__pycache__') for x in f.parts)]
def main():
 errors=[];fs=files();nj=0
 showcase={x['path']:x['sha256'] for x in json.loads((PKG/'manifests/showcase.json').read_text('utf-8'))}
 if len(showcase)!=4:errors.append('SHOWCASE_COUNT')
 spec=importlib.util.spec_from_file_location('wf_sanitize',PKG/'scripts/sanitize/sanitize_workflows.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 for f in fs:
  if not f.exists():errors.append('MISSING '+str(f.relative_to(PKG)));continue
  if f.suffix=='.json':
   try:json.loads(f.read_text(encoding='utf-8-sig'));nj+=1
   except Exception:errors.append('JSON '+str(f.relative_to(PKG)))
 inv=json.loads((PKG/'custom_nodes/local_author/COPY_INVENTORY.json').read_text(encoding='utf-8'))
 expected=set()
 for x in inv:
  rel=x['dest'].replace('\\','/');f=PKG/'custom_nodes/local_author'/rel;expected.add(rel)
  if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest()!=x['new_sha']:errors.append('SOURCE_HASH '+rel)
 actual={f.relative_to(PKG/'custom_nodes/local_author').as_posix() for f in fs if f.is_relative_to(PKG/'custom_nodes/local_author')}-{'COPY_INVENTORY.json'}
 if actual!=expected:errors.append('SOURCE_INVENTORY_SET')
 n,problems=mod.selfcheck(PKG/'workflows')
 errors.extend('WORKFLOW_PRIVACY '+str(x) for x in problems)
 for f in fs:
  rel=f.relative_to(PKG).as_posix()
  if rel in showcase:
   if hashlib.sha256(f.read_bytes()).hexdigest()!=showcase[rel]:errors.append('SHOWCASE_SHA '+rel)
   continue
  if f.suffix.lower() in ('.gif','.jpeg','.png','.jpg','.mp4','.wav','.safetensors','.gguf','.sqlite','.db','.jsonl','.pyc') or any(x in rel.split('/') for x in ('cache','raw_replies','PRIVATE_AUDIT','director_runtime','__pycache__')):errors.append('EXCLUDED_ARTIFACT '+rel)
 for rel in showcase:
  if not (PKG/rel).is_file():errors.append('SHOWCASE_MISSING '+rel)
 print('JSON',nj,'SOURCE_HASHES',len(inv),'WORKFLOWS',n)
 for error in errors:print(error)
 print('OFFLINE_INTEGRITY='+('FAIL' if errors else 'PASS')+' GPU=NOT_TESTED RUNTIME=HOLD')
 return bool(errors)
if __name__=='__main__':sys.exit(main())
