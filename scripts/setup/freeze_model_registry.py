"""Hash explicitly selected local models; never edits weights or contacts a service."""
import argparse,hashlib,json,os,shutil,tempfile
from pathlib import Path
ROLES={'h3','te','video_vae','audio_vae'}
def freeze(models,registry):
 if set(models)!=ROLES:raise ValueError('Supply exactly h3, te, video_vae and audio_vae; no inferred substitutes')
 rows=[]
 for role in sorted(ROLES):
  path=Path(models[role]).expanduser().resolve(strict=True)
  if not path.is_file():raise ValueError('Model must be a file: '+str(path))
  before=path.stat();digest=hashlib.sha256()
  with path.open('rb') as f:
   for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
  after=path.stat()
  if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Model changed while hashing: '+str(path))
  rows.append({'role':role,'path':str(path),'sha256':digest.hexdigest().upper(),'bytes':after.st_size,'mtime_ns':after.st_mtime_ns})
 registry=registry.resolve();registry.parent.mkdir(parents=True,exist_ok=True)
 if registry.is_file():
  old_sha=hashlib.sha256(registry.read_bytes()).hexdigest();backup=registry.with_name(registry.name+'.before_'+old_sha)
  if not backup.exists():shutil.copy2(registry,backup)
 fd,name=tempfile.mkstemp(prefix='.registry_',dir=registry.parent)
 try:
  with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:json.dump(rows,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(name,registry)
 finally:
  if Path(name).exists():Path(name).unlink()
 return rows
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--registry',type=Path,required=True);parser.add_argument('--model',action='append',required=True,help='role=absolute file path; repeat four times');args=parser.parse_args();models={}
 for item in args.model:
  role,sep,path=item.partition('=')
  if not sep or role in models:raise ValueError('Duplicate or malformed model role')
  models[role]=path
 rows=freeze(models,args.registry);print(json.dumps({'registry':str(args.registry.resolve()),'models':[{'role':r['role'],'bytes':r['bytes'],'sha256':r['sha256']} for r in rows]},indent=2))
