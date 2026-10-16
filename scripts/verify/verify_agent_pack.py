"""Verify an extracted full Agent Pack without installing dependencies or using GPU."""
from pathlib import Path
import argparse,csv,hashlib,json
def verify(root):
 manifest=root/'05_来源许可及校验/包内文件SHA256.csv'
 with manifest.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
 expected={r['相对路径']:r for r in rows}
 actual={p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and p!=manifest}
 if expected.keys()!=actual.keys():raise ValueError('Manifest file set mismatch')
 for rel,p in actual.items():
  if p.stat().st_size!=int(expected[rel]['字节数']) or hashlib.sha256(p.read_bytes()).hexdigest()!=expected[rel]['SHA256']:raise ValueError('File hash mismatch: '+rel)
  if p.name.startswith('restore_history_once.') or p.suffix.lower() in {'.pyc','.sqlite','.db','.jsonl'}:raise ValueError('Runtime artifact: '+rel)
  # Upstream third-party directories can contain JSONC templates named .json.
  # Preserve their pinned bytes; strict JSON parsing applies to first-party/config/workflows.
  if p.suffix.lower()=='.json' and '04_第三方_依法分发' not in p.parts:json.loads(p.read_text('utf-8-sig'))
 source=root/'02_完整节点源码/02_8207运行时自研源码'
 update=json.loads((root/'05_来源许可及校验/20261016源码同步.json').read_text('utf-8'))
 for row in update['files']:
  if hashlib.sha256((source/row['path']).read_bytes()).hexdigest()!=row['package_sha256']:raise ValueError('Update source mismatch')
 workflows=list((root/'01_完整工作流/12份当前JSON').glob('*.json'))
 if len(workflows)!=12:raise ValueError('Expected 12 current workflows')
 print(f'PACK_INTEGRITY=PASS files={len(actual)} updated_sources={len(update["files"])} workflows=12 GPU=NOT_TESTED')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);args=parser.parse_args();verify(args.root.resolve())
