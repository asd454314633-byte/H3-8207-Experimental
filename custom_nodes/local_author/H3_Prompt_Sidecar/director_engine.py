"""Standalone director. Only its provider may perform model I/O."""
from __future__ import annotations
import copy, importlib.util, json, os, re, sys, threading, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import director_rules as rules
ROOT=Path(__file__).resolve().parent
if 'h3_sidecar_model_providers' not in sys.modules:
    spec=importlib.util.spec_from_file_location('h3_sidecar_model_providers',ROOT/'providers/__init__.py',submodule_search_locations=[str(ROOT/'providers')])
    pkg=importlib.util.module_from_spec(spec);sys.modules[spec.name]=pkg;spec.loader.exec_module(pkg)
from h3_sidecar_model_providers import create_provider,ModelRequest,ProviderError
from h3_sidecar_model_providers.base import FallbackableError,GenerationLoopError
from generation_guard import check_repetition

class DirectorError(ValueError):pass

def _parse_director_json(text):
    """Parse model output as JSON with deterministic tail repair.

    Returns (obj, tail_repair) where tail_repair is None when the raw text
    parsed as-is, or {'missing_closers': n, 'original_error': str} when ONLY
    trailing closing brackets were missing (author ruling 2026-10-04: repair
    is allowed because nothing but tail closers is touched — no model call,
    no content change).  Raises DirectorError('JSON_PARSE_FAIL: ...') when
    the output is not repairable."""
    src=rules._strip_fence(text)
    try:
        return json.loads(src),None
    except json.JSONDecodeError as exc:
        repaired=rules.json_tail_repair(src)
        if repaired is not None:
            try:
                return json.loads(repaired),{'missing_closers':len(repaired)-len(src),'original_error':str(exc)[:200]}
            except json.JSONDecodeError:
                pass   # not a pure tail defect after all; report the original error
        raise DirectorError('JSON_PARSE_FAIL: 模型输出不是合法 JSON，且不是仅缺尾部闭合括号；'+str(exc)[:200])

def _json_response_validator(text):
    """AUTO-chain validator (author ruling 2026-10-04).  Applied by
    registry._chain_generate to each member response BEFORE it is accepted:
    valid JSON (after deterministic tail repair) passes; an unrepairable
    JSON_PARSE_FAIL raises FallbackableError so the chain may move to the
    next model.  Only ever invoked for AUTO chains — manual selection keeps
    strict single-model semantics via DirectorError at parse time."""
    try:
        _,_= _parse_director_json(text)   # noqa: validation only
        return rules._strip_fence(text)
    except DirectorError as exc:
        raise FallbackableError(str(exc)[:280]) from exc

def atomic(path,data):
    from h3_sidecar_model_providers.model_manager import atomic_json
    path.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(path,data)


def section(text,name):
    match=re.search(r'^\s*'+name+r':[ \t]*\r?$',text,re.M)
    if not match:return ''
    rest=text[match.end():];end=re.search(r'^\s*(?:'+ '|'.join(rules.SECTION_RE)+r'):[ \t]*\r?$',rest,re.M)
    return (rest[:end.start()] if end else rest).strip()

def validate(en,zh,declared,*,generated=True):
    errors=[]
    if not rules._sections_ok(en) or not rules._sections_ok(zh):errors.append('两稿需要完整且依次排列的六段标题')
    if rules._undeclared_refs(en,declared) or rules._undeclared_refs(zh,declared):errors.append('存在未声明的参考标签')
    if generated:
        ok,reason=rules._zh_is_chinese(zh,en)
        if not ok:errors.append(reason)
    if not en.strip() or not zh.strip():errors.append('两稿不能为空')
    check_repetition(json.dumps({'english_prompt':en,'chinese_prompt':zh},ensure_ascii=False))
    if errors:raise DirectorError('PROMPT_QUALITY: '+'；'.join(errors))

class Director:
    def __init__(self,data_dir=None,provider=None):
        self.data_dir=Path(data_dir or os.environ.get('H3_SIDECAR_DATA', str(ROOT/'director_data')));self.path=self.data_dir/'store.json'
        self.provider=provider or create_provider(ROOT/'sidecar.ini');self.lock=threading.RLock()
        if not self.path.exists():atomic(self.path,self.empty())
    @staticmethod
    def empty():return {'story_id':uuid.uuid4().hex,'revision':0,'continuity':copy.deepcopy(rules.EMPTY_LEDGER),'drafts':{},'accepted':[],'global_settings':''}
    def read(self):return json.loads(self.path.read_text(encoding='utf-8'))
    def state(self):
        with self.lock:
            s=self.read();latest=next(reversed(s['drafts'].values()),None) if s['drafts'] else None
            return {'story_id':s['story_id'],'revision':s['revision'],'continuity':s['continuity'],'draft':latest,'global_settings':s['global_settings']}
    def generate(self,payload,mode='generate'):
        if not self.lock.acquire(blocking=False):raise DirectorError('DIRECTOR_BUSY: 请等待当前操作完成')
        try:
            s=self.read();settings=str(payload.get('global_settings','')).strip();delta=str(payload.get('delta','')).strip()
            if not settings:raise DirectorError('请填写全局设定与参考职责；只需语义标签，不需要素材文件')
            if mode=='continue':delta=delta or '继续'
            if not delta:raise DirectorError('请填写本段要求')
            auto=mode=='continue' or rules.is_auto_continue(delta)
            ledger=copy.deepcopy(s['continuity'])
            if auto and not ledger['current_end_state']:raise DirectorError('NO_ACCEPTED_STORY: 请先生成首段并确认；未确认草稿不是剧情历史')
            head=('【模式】AUTO_CONTINUE：只从最后确认状态推进，选择open_threads，禁止重演已完成事件或旧对白。\nIMPORTANT: This is a NEW segment AFTER the accepted ending. All actions described in current_end_state and completed_events are ALREADY FINISHED, not instructions to perform again. Start a new timeline at 00:00.000 from that resulting state; never repeat the prior ending action or replay its timestamps. Design at least one genuinely NEW action and update the end state.\n' if auto else '【模式】NORMAL：按本段要求设计新片段。\n')
            if mode=='refine':
                draft_en=str(payload.get('english_prompt','')).strip();draft_zh=str(payload.get('chinese_prompt','')).strip()
                if not draft_en:raise DirectorError('Refine需要当前编辑后的英文稿')
                head='【模式】REFINE：用户主动要求修订以下草稿；它不是已确认历史。\n'
                delta+='\n【用户当前编辑稿】\n'+draft_en+'\n【中文对照】\n'+draft_zh
            guide=(ROOT/'frozen_h3_rules.md').read_text(encoding='utf-8')
            messages=rules.build_messages(settings,guide,ledger,delta,head)
            declared=rules._declared_resources(settings,json.dumps(ledger,ensure_ascii=False),delta)
            deadline=time.monotonic()+180;attempts=[]
            for attempt in range(2):
                try:
                    response=self.provider.generate(ModelRequest(messages=messages,max_tokens=5500,temperature=.3,top_p=.9,structured_output=rules.OUTPUT_SCHEMA,timeout=max(.01,deadline-time.monotonic()),metadata={'model_key':payload.get('model_key'),'response_validator':_json_response_validator},on_text=check_repetition))
                    if response.finish_reason=='length':raise GenerationLoopError('OUTPUT_TRUNCATED',response.text)
                    check_repetition(response.text)
                    break
                except GenerationLoopError as exc:
                    attempts.append({'error':str(exc),'partial_text':exc.partial_text})
                    if attempt or time.monotonic()>=deadline:
                        atomic(self.data_dir/'failed'/f'{uuid.uuid4().hex}.json',{'attempts':attempts});raise
                    messages=messages[:2]+[{'role':'user','content':'刚才因循环或截断中止。最多2镜头、2句新对白，返回完整双语JSON。不要重复段落。'}]
            did=uuid.uuid4().hex
            model_audit={'model_key':response.raw_metadata.get('model_key'),
                         'model_label':response.raw_metadata.get('model_label',response.model),
                         'requested_model_key':response.raw_metadata.get('requested_model_key'),
                         'actual_model_key':response.raw_metadata.get('actual_model_key'),
                         'actual_model_label':response.raw_metadata.get('actual_model_label'),
                         'fallback_count':response.raw_metadata.get('fallback_count',0),
                         'chain_attempts':response.raw_metadata.get('chain_attempts'),
                         'response_cost':response.raw_metadata.get('response_cost'),
                         'context_budget':response.raw_metadata.get('context_budget'),
                         'provider':response.provider,'model':response.model,
                         'timestamp':datetime.now(timezone.utc).isoformat(),'finish_reason':response.finish_reason,
                         'latency_ms':response.latency_ms,
                         'token_usage':{'prompt_tokens':response.prompt_tokens,'completion_tokens':response.completion_tokens,'total_tokens':response.total_tokens}}
            atomic(self.data_dir/'audit'/f'{did}.json',{'status':'RECEIVED','model_audit':model_audit,'raw_output':response.text,'attempts':attempts})
            obj,tail_repair=_parse_director_json(response.text)
            if tail_repair:model_audit['json_tail_repair']=tail_repair
            for key in ('english_prompt','chinese_prompt'):
                if isinstance(obj.get(key),dict):
                    parts=obj[key]
                    if set(parts)!=set(rules.SECTION_RE) or not all(isinstance(v,str) and v.strip() for v in parts.values()):
                        raise DirectorError('INVALID_SECTIONS: 六段正文必须全部非空')
                    obj[key]='\n\n'.join(name+':\n'+parts[name].strip() for name in rules.SECTION_RE)
            normalized=rules.normalize_output(json.dumps(obj,ensure_ascii=False),delta);zh,en,candidate=rules.parse_model_output(normalized)
            if not candidate:raise DirectorError('INVALID_JSON_STATE: 模型没有返回完整JSON/state_delta')
            validate(en,zh,declared)
            previous={re.sub(r'\W','',v).casefold() for v in ledger['recent_dialogue']}
            for line in candidate['new_dialogue']:
                if line not in en or line not in zh or re.sub(r'\W','',line).casefold() in previous:raise DirectorError('DIALOGUE_QUALITY: 台词不一致或重复旧对白')
            draft={'id':did,'story_id':s['story_id'],'base_revision':s['revision'],'status':'DRAFT','english_prompt':en,'chinese_prompt':zh,'candidate_state_delta':candidate,'global_settings':settings,'delta':delta,'auto_continue':auto,'model':response.model,'provider':response.provider,'latency_ms':response.latency_ms,'llm_attempts':attempt+1}
            draft.update(model_audit)
            s['drafts'][did]=draft;s['global_settings']=settings
            # Audit full output separately; never replay it as continuation context.
            atomic(self.data_dir/'audit'/f'{did}.json',{'draft':draft,'raw_output':response.text,'usage':{'prompt_tokens':response.prompt_tokens,'completion_tokens':response.completion_tokens},'attempts':attempts})
            s['drafts']=dict(list(s['drafts'].items())[-20:]);atomic(self.path,s)
            return copy.deepcopy(draft)
        finally:self.lock.release()
    def confirm(self,payload):
        with self.lock:
            s=self.read();did=str(payload.get('draft_id',''));d=s['drafts'].get(did)
            if not d:raise DirectorError('DRAFT_NOT_FOUND: 请从当前故事的草稿确认')
            if d['status']=='ACCEPTED':
                if payload.get('english_prompt')==d['english_prompt'] and payload.get('chinese_prompt')==d['chinese_prompt']:return {'status':'ACCEPTED','revision':s['revision'],'continuity':s['continuity'],'already_confirmed':True}
                if d.get('accepted_revision')!=s['revision']:
                    raise DirectorError('后续剧情已经确认；请通过新的草稿调整当前剧情')
                # Explicit correction of the most recently accepted segment replaces
                # its prior delta instead of appending duplicate events.
                s['continuity']=copy.deepcopy(d['ledger_before'])
                d['base_revision']=s['revision']
            if d['story_id']!=s['story_id'] or d['base_revision']!=s['revision']:raise DirectorError('DRAFT_HISTORY_CHANGED: 确认历史已推进，请生成新的草稿')
            en=str(payload.get('english_prompt','')).strip();zh=str(payload.get('chinese_prompt','')).strip();settings=str(payload.get('global_settings',d['global_settings'])).strip()
            declared=rules._declared_resources(settings)
            # Resource declarations inside an edited accepted draft are also explicit user semantic input.
            declared|=rules._declared_resources(section(en,'subject_definitions'),section(zh,'subject_definitions'))
            validate(en,zh,declared,generated=False)
            edited=en!=d['english_prompt'] or zh!=d['chinese_prompt']
            prior_ledger=copy.deepcopy(s['continuity'])
            if not edited and not payload.get('final_text_only', False):
                delta=copy.deepcopy(d['candidate_state_delta']);ledger=rules.commit_ledger(s['continuity'],delta)
                ledger['open_threads']=delta['open_threads'][-rules.LEDGER_MAX_THREADS:]
                memory_source='AI_CANDIDATE_USER_CONFIRMED'
            else:
                body=section(en,'detailed_description');paras=[p.strip() for p in re.split(r'\n\s*\n|\n(?=(?:At |\[Shot|\d\d:))',body) if p.strip()]
                spoken=re.findall(r'<d>\s*(?:\[[^\]]+\]\s*)?(.*?)</d>',body,re.S)
                # Literal final text only. Never use the superseded AI candidate for edited drafts.
                delta={'end_state':{'accepted_end_description':(paras[-1] if paras else body)[-1600:]},'new_completed_events':[p[:400] for p in paras[-6:]],'new_dialogue':spoken[-6:],'open_threads':(['最终确认文字（待续事项只从该文字判读，不继承旧模型推断）：'+body[-1600:]] if payload.get('final_text_only') else [])}
                ledger=rules.commit_ledger(s['continuity'],delta);ledger['open_threads']=delta['open_threads']
                memory_source='EDITED_FINAL_TEXT_LITERAL'
            d.update(status='ACCEPTED',english_prompt=en,chinese_prompt=zh,global_settings=settings,accepted_memory_source=memory_source,accepted_state_delta=delta)
            d['ledger_before']=prior_ledger;d['accepted_revision']=s['revision']+1
            s['continuity']=ledger;s['revision']+=1;s['accepted'].append({'draft_id':did,'revision':s['revision']});s['global_settings']=settings
            atomic(self.data_dir/'accepted'/f'{did}.json',d);atomic(self.path,s)
            return {'status':'ACCEPTED','revision':s['revision'],'continuity':ledger,'memory_source':memory_source}
    def new_story(self):
        with self.lock:
            s=self.read();atomic(self.data_dir/'archive'/f"{s['story_id']}.json",s);new=self.empty();new['global_settings']=s.get('global_settings','');atomic(self.path,new)
            return self.state()
