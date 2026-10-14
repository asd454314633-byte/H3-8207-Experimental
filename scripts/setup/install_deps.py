"""Install only commit-pinned third-party dependencies into an isolated target.
Unresolved references produce HOLD and nonzero exit; this never reports success after a failed clone.
No models, requirements or services are installed or started by this script.
"""
from pathlib import Path
import argparse,json,re,subprocess,sys
PKG=Path(__file__).resolve().parents[2]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--comfyui-root',required=True);ap.add_argument('--dry-run',action='store_true');ap.add_argument('--node',action='append');args=ap.parse_args()
 target=Path(args.comfyui_root).resolve();locks=json.loads((PKG/'config/third_party_nodes.lock.json').read_text(encoding='utf-8'));failures=[]
 if target==PKG or target.is_relative_to(PKG):raise ValueError('Dependency target must be outside this repository')
 for n in locks:
  name=n['node']
  if args.node and name not in args.node:continue
  if n.get('pin_kind')=='host_builtin':print('HOST_BUILTIN',name);continue
  url,pin=n.get('upstream_url',''),n.get('pin','')
  if not url.startswith('https://github.com/') or not re.fullmatch('[0-9a-f]{40}',pin):
   print('HOLD',name,'unresolved immutable upstream reference');failures.append(name);continue
  dst=target/'custom_nodes'/name
  if args.dry_run:print('PINNED_FETCH',name,url,pin);continue
  if dst.exists():
   head=subprocess.check_output(['git','-C',str(dst),'rev-parse','HEAD']).decode().strip()
   root=Path(subprocess.check_output(['git','-C',str(dst),'rev-parse','--show-toplevel']).decode().strip()).resolve()
   if root!=dst or head!=pin:raise ValueError('Existing dependency does not match pinned source: '+name)
   continue
  dst.mkdir(parents=True)
  for cmd in (['git','init',str(dst)],['git','-C',str(dst),'fetch','--depth=1',url,pin],['git','-C',str(dst),'checkout','--detach','FETCH_HEAD']):subprocess.run(cmd,check=True)
 if args.node:
  missing=set(args.node)-{n['node'] for n in locks}
  failures.extend(sorted(missing))
 print('DEPENDENCIES=HOLD' if failures else 'DEPENDENCIES=PASS')
 return 2 if failures else 0
if __name__=='__main__':
 try:sys.exit(main())
 except Exception as exc:print('DEPENDENCIES=FAIL',exc,file=sys.stderr);sys.exit(1)
