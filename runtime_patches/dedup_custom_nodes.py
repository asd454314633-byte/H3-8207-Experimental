"""Explicit host-source patch; run only against an isolated, stopped ComfyUI host."""
import argparse,hashlib,shutil
from pathlib import Path
OLD='folder_names_and_paths["custom_nodes"] = ([os.path.join(base_path, "custom_nodes"), os.path.join(os.path.dirname(os.path.realpath(__file__)), "custom_nodes")], set())'
NEW='folder_names_and_paths["custom_nodes"] = (list({os.path.normcase(os.path.realpath(p)): p for p in [os.path.join(base_path, "custom_nodes"), os.path.join(os.path.dirname(os.path.realpath(__file__)), "custom_nodes")]}.values()), set())'
SINGLE='folder_names_and_paths["custom_nodes"] = ([os.path.join(base_path, "custom_nodes")], set())'

def apply(root):
 path=root/'folder_paths.py';raw=path.read_bytes();text=raw.decode('utf-8')
 if NEW in text:print('Already applied');return
 if text.count(SINGLE)==1 and OLD not in text:
  print('Already unique upstream single-root source; no patch needed');return
 if text.count(OLD)!=1:raise ValueError('Unknown host source; patch not applied')
 backup=path.with_name('folder_paths.py.pre_closeout20261020')
 if backup.exists() and backup.read_bytes()!=raw:raise ValueError('Different backup exists; preserve and investigate')
 if not backup.exists():shutil.copy2(path,backup)
 path.write_bytes(text.replace(OLD,NEW).encode('utf-8'))
 print('before_sha256='+hashlib.sha256(raw).hexdigest())
 print('after_sha256='+hashlib.sha256(path.read_bytes()).hexdigest())
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('host',type=Path);apply(parser.parse_args().host.resolve())
