"""Rebuild an isolated source tree from pinned public 8197 and ComfyUI checkouts.
No service is started, no models/inputs/caches are copied, and no pip is run.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,tarfile,io,shutil,sys
PKG=Path(__file__).resolve().parents[2]
def git(root,*args):return subprocess.check_output(['git','-C',str(root),*args])
def checkout(root,url,commit,fetch):
 if not root.exists():
  if not fetch:raise ValueError('Missing pinned source checkout; use --fetch-sources')
  root.mkdir(parents=True)
  subprocess.run(['git','init',str(root)],check=True,stdout=subprocess.DEVNULL)
  subprocess.run(['git','-C',str(root),'fetch','--depth=1',url,commit],check=True)
  subprocess.run(['git','-C',str(root),'checkout','--detach','FETCH_HEAD'],check=True,stdout=subprocess.DEVNULL)
 if git(root,'rev-parse','HEAD').decode().strip()!=commit:raise ValueError('Source commit mismatch')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--baseline',required=True);ap.add_argument('--host',required=True);ap.add_argument('--out',required=True);ap.add_argument('--fetch-sources',action='store_true');ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
 baseline,host,out=(Path(x).resolve() for x in (args.baseline,args.host,args.out))
 if len({baseline,host,out,PKG})!=4:raise ValueError('Source and output directories must be distinct')
 for src in (baseline,host,PKG):
  if out.is_relative_to(src) or src.is_relative_to(out):raise ValueError('Source/output trees must not overlap')
 if out.exists() and (not out.is_dir() or any(out.iterdir())):raise ValueError('Output must be absent or empty')
 lock=json.loads((PKG/'config/baseline.lock.json').read_text(encoding='utf-8'))
 if args.dry_run:
  print(json.dumps(lock,indent=2));print('Plan: export pinned host; overlay each node at custom_nodes/<node>; check/apply execution patch; copy public workflows and example config');return
 checkout(baseline,lock['repository'],lock['commit'],args.fetch_sources)
 checkout(host,lock['host_repository'],lock['host_commit'],args.fetch_sources)
 out.mkdir(parents=True,exist_ok=True)
 # Export committed source bytes, independent of Windows checkout line endings.
 with tarfile.open(fileobj=io.BytesIO(git(host,'archive',lock['host_commit']))) as archive:
  for item in archive:
   dst=(out/item.name).resolve()
   if not dst.is_relative_to(out) or item.issym() or item.islnk():raise ValueError('Unsafe source archive path')
  archive.extractall(out,filter='data')
 # Reconstruct the exact Qwen 2.1 backport on its pinned public host base.
 qwen=lock.get('qwen21_backport')
 if qwen:
  qpatch=PKG/qwen['patch']
  if hashlib.sha256(qpatch.read_bytes()).hexdigest()!=qwen['sha256']:raise ValueError('Qwen patch hash mismatch')
  for entry in qwen['files']:
   dst=out/entry['path'];expected=entry['base_sha256']
   if expected is None:
    if dst.exists():raise ValueError('Unexpected Qwen target file: '+entry['path'])
   else:
    dst.write_bytes(dst.read_bytes().replace(b'\r\n',b'\n'))
    if hashlib.sha256(dst.read_bytes()).hexdigest()!=expected:raise ValueError('Qwen source hash mismatch: '+entry['path'])
  subprocess.run(['git','-c','core.autocrlf=false','-C',str(out),'apply','--check',str(qpatch)],check=True)
  subprocess.run(['git','-c','core.autocrlf=false','-C',str(out),'apply',str(qpatch)],check=True)
  for entry in qwen['files']:
   if hashlib.sha256((out/entry['path']).read_bytes()).hexdigest()!=entry['target_sha256']:raise ValueError('Qwen target hash mismatch: '+entry['path'])
 source=PKG/'custom_nodes/local_author';cn=out/'custom_nodes';cn.mkdir(exist_ok=True)
 # Reuse the exact published 8197 source line, then overlay audited 8207 files.
 prefix='custom_nodes/local_author/8197_production_line/'
 with tarfile.open(fileobj=io.BytesIO(git(baseline,'archive',lock['commit'],'custom_nodes/local_author/8197_production_line'))) as archive:
  for item in archive:
   if not item.isfile() or not item.name.startswith(prefix):continue
   rel=item.name[len(prefix):];dst=(cn/rel).resolve()
   if not dst.is_relative_to(cn.resolve()):raise ValueError('Unsafe baseline source path')
   dst.parent.mkdir(parents=True,exist_ok=True)
   dst.write_bytes(archive.extractfile(item).read())
 for node in source.iterdir():
  if node.is_dir() and not node.name.startswith('_') and not node.name.endswith('.disabled'):
   shutil.copytree(node,cn/node.name,dirs_exist_ok=True)
 execution=out/'execution.py'
 # Git archive can honor checkout EOL attributes; this patch is explicitly LF.
 execution.write_bytes(execution.read_bytes().replace(b'\r\n',b'\n'))
 if hashlib.sha256(execution.read_bytes()).hexdigest()!=lock['execution_before_sha256']:raise ValueError('Unsupported host execution.py; patch refused')
 patch=PKG/lock['patch']
 subprocess.run(['git','-c','core.autocrlf=false','-C',str(out),'apply','--check',str(patch)],check=True)
 subprocess.run(['git','-c','core.autocrlf=false','-C',str(out),'apply',str(patch)],check=True)
 if hashlib.sha256(execution.read_bytes()).hexdigest()!=lock['execution_after_sha256']:raise ValueError('Patched host hash mismatch')
 shutil.copytree(PKG/'workflows',out/'user/default/workflows',dirs_exist_ok=True)
 shutil.copy2(PKG/'config/examples/extra_model_paths.example.yaml',out/'extra_model_paths.example.yaml')
 (out/'REBUILD_RECEIPT.json').write_text(json.dumps({'source_export':'PASS','baseline_commit':lock['commit'],'host_commit':lock['host_commit'],'host_patch':'PASS','qwen_source_rebuild':'PASS' if qwen else 'NOT_REQUESTED','gpu':'NOT_TESTED','runtime_equivalence':'HOLD'},indent=2),encoding='utf-8')
 print('SOURCE_EXPORT=PASS HOST_PATCH=PASS RUNTIME_EQUIVALENCE=HOLD GPU=NOT_TESTED')
if __name__=='__main__':
 try:main()
 except Exception as exc:print('REBUILD_FAILED:',exc,file=sys.stderr);sys.exit(1)
