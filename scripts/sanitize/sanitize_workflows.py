"""Sanitize nested workflow text/state while preserving node/link/interface contracts.
This tool does not run ComfyUI or claim rendering acceptance.
"""
from pathlib import Path
import json,csv,hashlib,re,collections,sys,argparse
PAT={
 'adult':re.compile(r'性交|阴茎|阴道|乳头|(?<!接)口交|肛交|射精|精液|裸体|全裸|脱光|淫荡|做爱|勃起|\b(?:porn(?:ographic)?|fuck(?:ing)?|blowjob|handjob|cumshot|penetrat(?:ion|e)|naked|nude|nipples?|vagina|penis|orgasm)\b',re.I),
 'credential':re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',re.I),
 'personal':re.compile(r'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s"<>]+',re.I),
 'encoded_media':re.compile(r'data:(?:image|audio|video)/[^;]+;base64,',re.I)}
def strings(v,path='$'):
 if isinstance(v,str):
  yield path,v
  if v.lstrip().startswith(('{','[')):
   try:yield from strings(json.loads(v),path+'[decoded-json]')
   except ValueError:pass
 elif isinstance(v,dict):
  for k,x in v.items():yield from strings(x,path+'.'+str(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from strings(x,path+f'[{i}]')
TRUSTED_UPSTREAM_PROMPT_SHA256={'081dc85df01bb9eaac2bc73f3793fdce0c56dca98773f7892628654636bf23d5', '4c438fcf10ce8949b9a4b9c675403ec71613d2bb88dc2ca57eb7468aec9e8e18', '88c90daedc0be46eb400739c941d14f483a4dc72ba415ba885469a30637ac44a'}
NEUTRAL='A person walks along a quiet street in daylight.'
MEDIA='REPLACE_WITH_SYNTHETIC_TEST_IMAGE'
PRIVATE=re.compile(r'(?:[A-Za-z]:[\\/]|/(?:Users)/|/home/)|\.(?:png|jpe?g|webp|gif|bmp|mp4|mov|avi|wav|mp3|flac|mkv|webm)\b|data:[^;]+;base64,',re.I)
RUNTIME=re.compile(r'^(?:six_prompt_state|h3_prebake_texts|h3_prebake_binding|h3_prebake_last_plan|video_refs|videoRefs|executionState|six_acceptance|preview|thumbnail|cookies|access_token|api_key)$',re.I)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def slots(v,path='$'):
 if isinstance(v,dict):
  for k,x in v.items():yield from slots(x,path+'.'+str(k))
 elif isinstance(v,list):
  for i,x in enumerate(v):yield from slots(x,path+f'[{i}]')
 else:yield path,v
def graph_contract(v):
 # Full structure including interface types, connection slots and subgraphs; UI labels/widgets excluded.
 if not isinstance(v,dict):return None
 def graph(g):
  nodes=[]
  for n in g.get('nodes',[]):
   nodes.append({k:n.get(k) for k in ('id','type','mode','inputs','outputs')})
  return {'nodes':nodes,'links':g.get('links',[]),'inputs':g.get('inputs',[]),'outputs':g.get('outputs',[])}
 return {'root':graph(v),'subgraphs':[graph(g) for g in v.get('definitions',{}).get('subgraphs',[])]}
def sanitize(v,log,path='$',text_node=False):
 if isinstance(v,dict):
  typ=str(v.get('type','')).lower();is_text=bool(re.search(r'cliptext|textencode|primitivestring|markdownnote|^note$|stringconstant',typ))
  out={}
  named=v.get('widgets_values_named', {})
  replacements={value:NEUTRAL for key,value in named.items() if key.lower() in ('prompt','positive_prompt','negative_prompt','instruction','dialogue') and isinstance(value,str) and value and hashlib.sha256(value.encode()).hexdigest() not in TRUSTED_UPSTREAM_PROMPT_SHA256}
  for k,x in v.items():
   if k=='widgets_values' and isinstance(x,list):x=[replacements.get(z,z) if isinstance(z,str) else z for z in x]
   loc=path+'.'+str(k)
   if RUNTIME.match(k):
    new={} if isinstance(x,dict) else [] if isinstance(x,list) else ''
    if x!=new:log.append([loc,'runtime_state_removed'])
    out[k]=new
   elif k.lower() in ('prompt','positive_prompt','negative_prompt','instruction','dialogue') and isinstance(x,str) and x and hashlib.sha256(x.encode()).hexdigest() not in TRUSTED_UPSTREAM_PROMPT_SHA256:
    out[k]=NEUTRAL;log.append([loc,'named_prompt_neutralized'])
   elif k in ('widgets_values','widgets_values_named') and is_text:
    def prompt(q,loc):
     if isinstance(q,str) and q and not q.startswith('__H3_GUIDE_NOT_SET__'):
      log.append([loc,'text_widget_neutralized']);return NEUTRAL
     if isinstance(q,list):return [prompt(z,loc+f'[{i}]') for i,z in enumerate(q)]
     if isinstance(q,dict):return {a:prompt(z,loc+'.'+a) for a,z in q.items()}
     return q
    out[k]=prompt(x,loc)
   else:out[k]=sanitize(x,log,loc)
  return out
 if isinstance(v,list):return [sanitize(x,log,path+f'[{i}]') for i,x in enumerate(v)]
 if isinstance(v,str):
  if v.startswith('__H3_GUIDE_NOT_SET__'):return v
  if v.lstrip().startswith(('{','[')):
   try:
    nested=json.loads(v);new=sanitize(nested,log,path+'[decoded-json]');return json.dumps(new,ensure_ascii=False) if new!=nested else v
   except ValueError:pass
  if PRIVATE.search(v):log.append([path,'private_media_or_path']);return MEDIA if re.search(r'\.(png|jpe?g|mp4|wav|webp)\b',v,re.I) else '<REDACTED_PRIVATE_PATH>'
  if re.fullmatch(r'[A-Za-z0-9+/=\s]{200,}',v):log.append([path,'encoded_payload_removed']);return '<REDACTED_EMBEDDED_DATA>'
  if PAT['adult'].search(v) or PAT['credential'].search(v) or PAT['personal'].search(v):log.append([path,'private_text_removed']);return NEUTRAL
 return v
def selfcheck(root):
 problems=[];scanned=0
 for f in Path(root).rglob('*.json'):
  scanned+=1
  try:d=json.loads(f.read_text(encoding='utf-8-sig'))
  except ValueError:problems.append((str(f.relative_to(root)),'INVALID_JSON'));continue
  for loc,s in strings(d):
   for kind,pat in PAT.items():
    if pat.search(s):problems.append((str(f.relative_to(root)),loc,kind))
   if s not in (MEDIA,'<REDACTED_PRIVATE_PATH>','<REDACTED_EMBEDDED_DATA>') and not s.startswith('__H3_GUIDE_NOT_SET__') and (PRIVATE.search(s) or re.fullmatch(r'[A-Za-z0-9+/=\s]{200,}',s)):problems.append((str(f.relative_to(root)),loc,'MEDIA_PATH_OR_ENCODING'))
 return scanned,problems
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--src');ap.add_argument('--out');ap.add_argument('--selfcheck',action='store_true');args=ap.parse_args()
 if args.selfcheck:
  n,problems=selfcheck(Path(__file__).resolve().parents[2]/'workflows');print('WORKFLOWS',n,'PRIVACY='+('FAIL' if problems else 'PASS'))
  for p in problems:print(p)
  return bool(problems)
 if not args.src or not args.out:ap.error('Use --src and --out, or --selfcheck')
 src,out=Path(args.src).resolve(),Path(args.out).resolve()
 if src==out or src.is_relative_to(out) or out.is_relative_to(src):raise ValueError('Source and output must not overlap')
 for f in src.rglob('*.json'):
  original=json.loads(f.read_text(encoding='utf-8-sig'));log=[];public=sanitize(original,log)
  if graph_contract(original)!=graph_contract(public):raise ValueError('Graph contract mutation refused')
  dst=out/f.relative_to(src);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(json.dumps(public,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
 print('SANITIZE=PASS; runtime and image quality remain NOT_TESTED');return 0
if __name__=='__main__':sys.exit(main())
