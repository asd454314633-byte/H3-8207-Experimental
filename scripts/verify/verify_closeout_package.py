"""Offline exact-file verification. Does not run or certify recipient GPU behavior."""
import argparse,csv,hashlib,json
from pathlib import Path
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def verify(root):
 manifest=root/'05_来源许可及校验/包内文件SHA256.csv'
 with manifest.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
 expected={r['相对路径']:r for r in rows}
 actual={p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
 if set(expected)!=set(actual):raise ValueError('Exact package file set differs')
 for rel,p in actual.items():
  row=expected[rel]
  if p.stat().st_size!=int(row['字节数']) or sha(p)!=row['SHA256'].lower():raise ValueError('Hash mismatch: '+rel)
  if p.suffix.lower() in {'.safetensors','.gguf','.pt','.pth','.ckpt','.bin','.sqlite','.db','.pyc','.jsonl'} or p.name.startswith('restore_history_once.'):
   raise ValueError('Excluded runtime/model artifact: '+rel)
 update=json.loads((root/'05_来源许可及校验/20261020源码同步.json').read_text('utf-8'))
 for row in update['files']:
  for source in [root/'02_完整节点源码/02_8207运行时自研源码',root/'07_公开源码及回归/custom_nodes/local_author']:
   if sha(source/row['path'])!=row['package_sha256']:raise ValueError('First-party source copy mismatch: '+row['path'])
 workflows=list((root/'01_完整工作流/12份当前JSON').glob('*.json'))
 if len(workflows)!=12:raise ValueError('Expected 12 full canvas JSON files')
 for p in workflows:
  data=json.loads(p.read_text('utf-8'));assert isinstance(data.get('nodes'),list) and isinstance(data.get('links'),list),p.name
 print(f'PACKAGE_INTEGRITY=PASS files={len(actual)} current_source_files={len(update["files"])} full_workflows=12 RECIPIENT_GPU=NOT_TESTED')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);verify(parser.parse_args().root.resolve())
