"""Six consecutive drafts using the existing single-segment Director."""
import copy
import json
import tempfile
import uuid
import time
from pathlib import Path
from director_engine import Director, DirectorError, atomic, rules, ModelRequest

PLAN_SCHEMA={'type':'object','required':['segments'],'additionalProperties':False,'properties':{'segments':{'type':'array','minItems':6,'maxItems':6,'items':{'type':'string','minLength':1,'maxLength':1000}}}}

def context_seed(base_ledger, continuing):
    """新 context_group 的上下文种子（H3_DIRECTOR_SIX_GROUP_CONTEXT_ISOLATION_V1 第3-4节）。

    每次点击"生成六段剧情"= 新建独立语义上下文：
    - 普通生成：种子为空账本。禁止继承上一组的 current_end_state、completed_events、
      recent_dialogue、open_threads，以及任何 planner/compiler 历史文本。
    - 显式"继续六段"：只继承白名单内的结构化状态——上一组最终确认末态
      （current_end_state）、最近必要对白状态（recent_dialogue）、未完成事件
      （open_threads）。completed_events（已结束剧情的冗余描述）与一切原始
      文本不得进入种子。组内连续性仍由 stage 账本按段提交，机制不变。

    H3_SIX_GROUP_CONTEXT_ISOLATION_FINAL_CLOSEOUT 第A节收紧：
    current_end_state 只允许携带 previous_group_final_confirmed_end_state
    （上一组最后一段、经用户确认/最终编辑后的最终末态）。禁止继承
    segment1~5 的 ending，也禁止继承六段 ending 数组本身——即使它是 JSON
    序列化的结构化数据。因此 confirm() 写入的 accepted_group_final_endings
    键在此处被显式剔除；上一组最终末态只由 accepted_end_description
    （第六段收束段）承载。
    """
    if not continuing:
        return copy.deepcopy(rules.EMPTY_LEDGER)
    final_state = copy.deepcopy(base_ledger.get('current_end_state', {}))
    final_state.pop('accepted_group_final_endings', None)
    return {
        'current_end_state': final_state,
        'completed_events': [],
        'recent_dialogue': list(base_ledger.get('recent_dialogue', []))[-rules.LEDGER_MAX_DIALOGUE:],
        'open_threads': list(base_ledger.get('open_threads', []))[-rules.LEDGER_MAX_THREADS:],
    }

def _latest_accepted_context_id(directory, story_id):
    """显式继续时的 parent_context_group_id：最近一组 ACCEPTED 组的 context_group_id。"""
    for path in sorted(directory.glob('*/group.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try: prior = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError): continue
        if prior.get('status') == 'ACCEPTED' and prior.get('story_id') == story_id:
            return (prior.get('context_group') or {}).get('context_group_id') or prior.get('id')
    return None


class SixSegmentDirector:
    def __init__(self, director):
        self.director = director
        self.directory = director.data_dir / 'groups'

    def path(self, group_id):
        if not isinstance(group_id, str) or len(group_id) != 32 or any(c not in '0123456789abcdef' for c in group_id):
            raise DirectorError('GROUP_NOT_FOUND')
        return self.directory / group_id / 'group.json'

    def read(self, group_id):
        path = self.path(group_id)
        if not path.is_file(): raise DirectorError('GROUP_NOT_FOUND')
        return json.loads(path.read_text(encoding='utf-8'))

    def latest(self):
        story_id = self.director.state()['story_id']
        paths = sorted(self.directory.glob('*/group.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths:
            group = json.loads(path.read_text(encoding='utf-8'))
            if group['story_id'] == story_id: return group
        return None

    def generate(self, payload):
        if not self.director.lock.acquire(blocking=False): raise DirectorError('DIRECTOR_BUSY')
        session = None
        try:
            started = time.perf_counter()
            base = self.director.read()
            goal = str(payload.get('delta', '')).strip()
            if not goal: raise DirectorError('请填写六段剧情要求')
            continuing = goal in ('继续六段', '继续', '继续剧情')
            if continuing and not base['continuity']['current_end_state']:
                raise DirectorError('NO_ACCEPTED_STORY: 请先确认上一组六段')
            # 每次生成都是新 context_group：普通生成空种子，显式继续才继承白名单末态。
            seed = context_seed(base['continuity'], continuing)
            parent_id = _latest_accepted_context_id(self.directory, base['story_id']) if continuing else None
            group_id = uuid.uuid4().hex
            path = self.path(group_id)
            stage = Director(path.parent / 'provisional', self.director.provider)
            stage_state = copy.deepcopy(base)
            stage_state['continuity'] = copy.deepcopy(seed)
            atomic(stage.path, stage_state)
            # Follow the selected Director unless an independent Planner is explicit.
            plan_key = payload.get('model_key') or self.director.provider.selected
            if payload.get('planner_model_key') not in (None, '', plan_key):
                raise DirectorError('SELECTED_MODEL_MISMATCH')
            payload = dict(payload, model_key=plan_key)
            from contextlib import ExitStack
            session = ExitStack()
            session.enter_context(self.director.provider.planner_session(plan_key))
            # Planner 输入同样从本组种子出发：普通生成不带 accepted_continuity，
            # 显式继续只携带白名单内的结构化末态。
            planner_input = {'global_settings': payload.get('global_settings', ''), 'story_goal': goal}
            if continuing:
                planner_input['accepted_continuity'] = copy.deepcopy(seed)
            plan_response=self.director.provider.generate(ModelRequest(
                messages=[{'role':'system','content':'你是连续剧情规划师。把同一个故事按因果和时间拆成六个连续片段，不是六种方案。每段约10秒、最多两个镜头，只推进一个新的主要动作。逐段明确开头状态、这一段的新动作和结尾状态；下一段开头必须承接上一段结尾。不要在前两段完成全部任务，不要重复拿起、翻阅、合上或重演已完成动作。第六段满足用户指定的最终结果。只返回六条剧情计划的JSON。'},
                          {'role':'user','content':json.dumps(planner_input,ensure_ascii=False)}],
                structured_output=PLAN_SCHEMA,max_tokens=1800,timeout=300,metadata={'model_key':plan_key}))
            atomic(path.parent/'plan_audit.json',{'raw_output':plan_response.text,'finish_reason':plan_response.finish_reason,'model':plan_response.model,'provider':plan_response.provider,'usage':plan_response.raw_metadata})
            if plan_response.finish_reason=='length':raise DirectorError('六段计划被截断；未生成或提交新组')
            plan=json.loads(rules._strip_fence(plan_response.text)).get('segments')
            if not isinstance(plan,list) or len(plan)!=6 or not all(isinstance(p,str) and p.strip() for p in plan):raise DirectorError('INVALID_SIX_SEGMENT_PLAN')
            segments = []
            allowed_tags=sorted(rules._declared_resources(str(payload.get('global_settings',''))))
            for index in range(6):
                delta = (f'整组六段是一条按时间推进的故事，不是六个候选版本。整体目标：{goal}。'
                         f'整组既定计划：{json.dumps(plan,ensure_ascii=False)}。现在只生成第{index+1}/6段：{plan[index]}。约10秒，最多两个镜头。'
                         '只能完成这一段计划中的动作，禁止提前执行后续段落计划；如果计划开头与账本不一致，以账本中的真实结尾为起点。'
                         '承接所给current_end_state中的位置、姿态、道具、场景、因果与对白，推进新动作，不重演已完成事件。'
                         '前五段留下自然的下一步，第六段形成这一分钟故事块的结尾；每段都返回完整H3双语稿和state_delta。')
                delta+=f'资源格式契约：只允许这些已声明标签：{allowed_tags}。不得自行加入Video/Audio/Picture/Subject标签；尤其未声明Video时，summary视频续写也绝不代表存在<Video 1>参考资源。'
                start_continuity=copy.deepcopy(stage.read()['continuity'])
                if segments and start_continuity['current_end_state']!=segments[-1]['end_state']:
                    raise DirectorError('SEGMENT_START_STATE_MISMATCH')
                request=dict(payload,delta=delta)
                mode='continue' if index or continuing else 'generate'
                prior_audits=set((stage.data_dir/'audit').glob('*.json'))
                try:
                    draft=stage.generate(request,mode)
                except DirectorError as error:
                    # One clean resource-format retry; never feed the rejected
                    # output back or add a third attempt after the loop retry.
                    received=set((stage.data_dir/'audit').glob('*.json'))-prior_audits
                    if '未声明的参考标签' not in str(error) or not received: raise
                    audit=json.loads(max(received,key=lambda p:p.stat().st_mtime).read_text(encoding='utf-8'))
                    if audit.get('attempts'): raise
                    request['delta']=delta+f'\n一次干净格式重试：正文、summary和state_delta都只能引用{allowed_tags}；未列出的Video/Audio/Subject/Picture标签全部禁止。不要加入任何参考资源。'
                    draft=stage.generate(request,mode)
                    draft['group_format_attempts']=2
                segments.append({'number':index+1, 'draft':draft, 'english_prompt':draft['english_prompt'], 'status':'草稿', 'start_state':copy.deepcopy(start_continuity['current_end_state']), 'start_continuity':start_continuity, 'end_state':copy.deepcopy(draft['candidate_state_delta']['end_state'])})
                # This ledger is provisional only. The real store is never touched.
                provisional = stage.read()
                provisional['continuity'] = rules.commit_ledger(provisional['continuity'], draft['candidate_state_delta'])
                provisional['continuity']['open_threads'] = draft['candidate_state_delta']['open_threads'][-rules.LEDGER_MAX_THREADS:]
                atomic(stage.path, provisional)
            group = {'id':group_id, 'story_id':base['story_id'], 'base_revision':base['revision'],
                     'status':'DRAFT', 'global_settings':payload.get('global_settings', ''),
                     'context_group':{'context_group_id':group_id, 'parent_context_group_id':parent_id,
                                      'seed_mode':'CONTINUATION' if continuing else 'NEW',
                                      'inherited_ledger_keys':sorted(key for key, value in seed.items() if value)},
                     'continuity_contract':'SEGMENT_N_PLUS_1_START_EQUALS_SEGMENT_N_END', 'total_director_time_ms':round((time.perf_counter()-started)*1000),
                     'goal':goal, 'model_key':payload.get('model_key'), 'planner_model_key':plan_key, 'segment_plan':plan, 'segments':segments}
            atomic(path, group)
            return group
        finally:
            if session is not None:
                session.__exit__(*__import__("sys").exc_info())
            self.director.lock.release()

    def save(self, payload):
        with self.director.lock:
            group = self.read(payload.get('group_id'))
            index = payload.get('segment_index')
            if type(index) is not int or not 0 <= index < 6: raise DirectorError('INVALID_SEGMENT')
            text = payload.get('english_prompt')
            if not isinstance(text, str): raise DirectorError('INVALID_PROMPT')
            group['segments'][index].update(english_prompt=text, status='已修改')
            atomic(self.path(group['id']), group)
            return group['segments'][index]

    def confirm(self, payload):
        with self.director.lock:
            group = self.read(payload.get('group_id'))
            current = self.director.read()
            texts = payload.get('prompts')
            if not isinstance(texts, list) or len(texts) != 6 or not all(isinstance(t, str) for t in texts):
                raise DirectorError('需要六段最终Prompt')
            if group['status'] == 'ACCEPTED' and texts == [s['english_prompt'] for s in group['segments']]:
                return {'status':'ACCEPTED', 'continuity':current['continuity'], 'already_confirmed':True}
            if group['story_id'] != current['story_id'] or group['base_revision'] != current['revision']:
                raise DirectorError('确认历史已推进，请从当前结尾生成下一组六段')
            # Replay the existing manual confirmation in an isolated store, then
            # publish its result atomically. A bad sixth edit cannot commit five.
            with tempfile.TemporaryDirectory(dir=self.director.data_dir) as temp:
                stage = Director(temp, self.director.provider)
                atomic(stage.path, copy.deepcopy(current))
                for segment, text in zip(group['segments'], texts):
                    state = stage.read()
                    draft = copy.deepcopy(segment['draft'])
                    draft.update(base_revision=state['revision'], status='DRAFT')
                    state['drafts'][draft['id']] = draft
                    atomic(stage.path, state)
                    result = stage.confirm({'draft_id':draft['id'], 'english_prompt':text,
                                            'chinese_prompt':draft['chinese_prompt'], 'global_settings':group['global_settings'], 'final_text_only':True})
                final = stage.read()
                # Preserve the six literal endings as an ordered factual source.
                final['continuity']['current_end_state']['accepted_group_final_endings']=json.dumps([final['drafts'][s['draft']['id']]['accepted_state_delta']['end_state']['accepted_end_description'] for s in group['segments']],ensure_ascii=False)
                final['continuity']['current_end_state']['memory_source']='FINAL_EDITED_SIX_PROMPTS'
                result['continuity']=copy.deepcopy(final['continuity'])
                for accepted in (Path(temp) / 'accepted').glob('*.json'):
                    atomic(self.director.data_dir / 'accepted' / accepted.name, json.loads(accepted.read_text(encoding='utf-8')))
                atomic(self.director.path, final)
            for segment, text in zip(group['segments'], texts): segment.update(english_prompt=text)
            group.update(status='ACCEPTED', accepted_revision=final['revision'])
            atomic(self.path(group['id']), group)
            return result
