"""Per-segment image Guides, applied after Native/cache/seam routing, never in TE bake."""
import copy,json,math
from pathlib import Path
from . import production as p

SCHEMA='H3_SIX_USER_GUIDE_V1'
SPEC='SIX_USER_GUIDE_SPEC'
RESERVED={'USER_GUIDE_IMAGE','USER_GUIDE_BEFORE','USER_GUIDE_APPLY','USER_GUIDE_AFTER'}

def resolve_frame(frames,protected,mode,value):
    if type(frames) is not int or frames<48 or frames%17!=5:raise ValueError('关键帧：无法确认当前段实际17k+5生成帧数')
    if protected not in (0,39):raise ValueError('关键帧：Native保护区必须为0或39帧')
    if type(value) is bool:raise ValueError('关键帧位置须填写数字')
    try:n=float(value)
    except (TypeError,ValueError):raise ValueError('关键帧位置须填写数字')
    if not math.isfinite(n):raise ValueError('关键帧位置须为有限数字')
    visible_frames=frames-protected
    if mode in ('frame','from_end'):
        if not n.is_integer():raise ValueError('关键帧帧号须为整数')
        if mode=='from_end' and n<1:raise ValueError('倒数帧号须从1开始')
        visible=int(n) if mode=='frame' else visible_frames-int(n)
    elif mode=='seconds':visible=math.floor(n*24+.5)
    else:raise ValueError('关键帧位置类型无效')
    if n<0 or not 0<=visible<visible_frames:raise ValueError(f'关键帧超出本段可见范围：共{visible_frames}帧，合法索引0～{visible_frames-1}')
    internal=visible+protected
    if internal<protected:raise ValueError('关键帧与Native39帧保护区冲突')
    if internal>9999:raise ValueError('关键帧超出官方AddGuide帧号上限')
    return {'frames':frames,'protected_frames':protected,'visible_frames':visible_frames,'visible_frame':visible,'model_frame':internal}

def source_info(source,expected=None):
    import folder_paths
    from PIL import Image,ImageOps
    import numpy as np
    if not isinstance(source,str) or not source or Path(source).is_absolute() or source.endswith((' [output]',' [temp]')):raise ValueError('关键帧图片须为本机input目录的已上传文件')
    root=Path(folder_paths.get_input_directory()).resolve()
    path=Path(folder_paths.get_annotated_filepath(source)).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise ValueError('关键帧图片丢失或不在input目录，请重新上传')
    digest=p.codec.file_sha(path)
    if expected and str(expected).upper()!=digest:raise ValueError('关键帧图片SHA256已变化，请重新上传并确认')
    try:
        with Image.open(path) as image:
            if getattr(image,'n_frames',1)!=1:raise ValueError('每段只允许一张静态关键帧图片，不接受动画或多帧文件')
            image=ImageOps.exif_transpose(image)
            if image.mode.startswith(('I','F')):raise ValueError('当前关键帧仅接受标准8位图片，请转为RGB PNG/JPEG后上传')
            pixels=(np.asarray(image.convert('RGB')).astype(np.float32)/255.0)[None]
    except (OSError,ValueError) as ex:raise ValueError('关键帧图片无法读取：'+str(ex))
    if p.codec.file_sha(path)!=digest:raise ValueError('关键帧图片在校验期间发生变化，请重新上传')
    return {'source':path.relative_to(root).as_posix(),'source_sha256':digest,'pixel_sha256':p.codec.digest(pixels.tobytes()),'image_shape':list(pixels.shape)}

def frame_policy(graph,index,inherit):
    if type(index) is not int or index not in range(6):raise ValueError('关键帧段号无效')
    fps=p.scalar(graph.get('764',{}).get('inputs',{}).get('fps',24),graph)
    if float(fps)!=24:raise ValueError('本段关键帧当前只支持实际24fps')
    length=p.scalar(graph.get('136',{}).get('inputs',{}).get('length'),graph)
    if length is None and 'PREBAKE_LOAD' in graph:length=json.loads(graph['PREBAKE_LOAD']['inputs']['contract_json'])['frames']
    if type(length) not in (int,float) or not math.isfinite(length) or int(length)!=length:raise ValueError('关键帧：无法解析实际生成帧数')
    frames=max(5,int(length));frames+=(5-frames%17)%17
    prep=next((n['inputs'] for n in graph.values() if n['class_type']=='H3ContinuationPrepare'),None)
    if prep is None:raise ValueError('关键帧缺少现有Native Prepare，禁止猜测保护区')
    rebase=inherit and prep.get('clean_rebase_enabled') is True and int(prep.get('clean_rebase_segment',-1))==index
    return frames,0 if not inherit or rebase else 39,rebase

def preflight(graph,index,config,inherit,snapshot_id):
    if not config or config.get('enabled') is not True:return None
    if not isinstance(snapshot_id,str) or not snapshot_id:raise ValueError('关键帧缺少执行快照身份')
    frames,protected,rebase=frame_policy(graph,index,inherit)
    resolved=resolve_frame(frames,protected,config.get('mode'),config.get('value'))
    if rebase and resolved['model_frame']==0:raise ValueError('关键帧冲突：Clean Rebase首帧0已用于自动衔接，请选择中途帧')
    source=source_info(config.get('source'),config.get('source_sha256'))
    draft={'enabled':True,'mode':config['mode'],'value':config['value'],'source':source['source'],'source_sha256':source['source_sha256']}
    return {'schema':SCHEMA,'segment_index':index,'snapshot_id':snapshot_id,'config':draft,**resolved,**source}

def spec(graph,index=None):
    node=graph.get(SPEC)
    if not node:return None
    if node.get('class_type')!='PrimitiveStringMultiline':raise ValueError('关键帧快照节点类型不匹配')
    try:value=json.loads(node['inputs']['value'])
    except (KeyError,TypeError,ValueError):raise ValueError('关键帧执行快照格式错误')
    if value.get('schema')!=SCHEMA or type(value.get('segment_index')) is not int or index is not None and value['segment_index']!=index:raise ValueError('关键帧执行快照串段或版本不匹配')
    return value

def fingerprint(graph,index):
    value=spec(graph,index)
    if value is None:return None
    # Submission identity is immutable execution metadata, not the conditioning cache key.
    return {k:copy.deepcopy(v) for k,v in value.items() if k!='snapshot_id'}

def verify_spec(graph,index):
    value=spec(graph,index)
    if value is None:return None
    prep=next(n['inputs'] for n in graph.values() if n['class_type']=='H3ContinuationPrepare')
    actual=preflight(graph,index,value['config'],prep.get('enabled') is True,value['snapshot_id'])
    if actual!=value:raise ValueError('关键帧帧数、保护区、图片或执行快照已变化；未提交GPU')
    return value

def policy_hash(policy):return p.codec.digest(p.codec.canonical({k:v for k,v in policy.items() if k!='stage'}))

def existing_positions(graph):
    root=graph['126']['inputs']['conditioning'];positions=[]
    for node in p.prune(graph,[root[0]]).values():
        if node['class_type']=='MiniMaxH3AddGuide':
            pos=p.scalar(node['inputs'].get('frame_idx'),graph)
            if type(pos) is not int:raise ValueError('已有Guide帧号无法解析，禁止与用户关键帧混合')
            positions.append(pos)
        elif node['class_type']=='H3GuideTimeline':raise ValueError('旧965时间线仍在执行链，请旁路旧时间线并使用六段框关键帧')
    return positions

def apply(graph,context,index,attempt_id,managed=True):
    value=verify_spec(graph,index)
    if value is None:return graph,None
    if RESERVED.intersection(graph):raise ValueError('当前段用户关键帧被重复注入')
    frame=value['model_frame']
    positions=[x if x>=0 else value['frames']+x for x in existing_positions(graph)]
    if frame in positions:raise ValueError(f'关键帧重复冲突：模型帧{frame}已有Guide')
    vae=graph.get('122',{}).get('inputs',{}).get('vae')
    if not vae:raise ValueError('关键帧缺少当前视频VAE，未提交GPU')
    prepare=next(k for k,n in graph.items() if n['class_type']=='H3ContinuationPrepare')
    policy={**copy.deepcopy(value),'context':copy.deepcopy(context),'attempt_id':attempt_id,'managed':managed}
    if graph[prepare]['inputs'].get('segment_index')!=index or graph[prepare]['inputs'].get('project_id')!=context['project_id']:raise ValueError('关键帧与实际Native段号或项目不匹配')
    common={'latent':copy.deepcopy(graph['125']['inputs']['latent_image']),'image':['USER_GUIDE_IMAGE',0],'plan_json':[prepare,1],'segment_index':index,'project_id':context['project_id']}
    graph['USER_GUIDE_IMAGE']={'class_type':'LoadImage','inputs':{'image':value['source']}}
    graph['USER_GUIDE_BEFORE']={'class_type':'H3SixUserGuideAudit','inputs':{**copy.deepcopy(common),'conditioning':copy.deepcopy(graph['126']['inputs']['conditioning']),'guide_json':json.dumps({**policy,'stage':'before'},ensure_ascii=False)}}
    graph['USER_GUIDE_APPLY']={'class_type':'MiniMaxH3AddGuide','inputs':{'positive':['USER_GUIDE_BEFORE',0],'latent':['USER_GUIDE_BEFORE',1],'image':['USER_GUIDE_BEFORE',2],'vae':copy.deepcopy(vae),'frame_idx':frame}}
    graph['USER_GUIDE_AFTER']={'class_type':'H3SixUserGuideAudit','inputs':{**copy.deepcopy(common),'conditioning':['USER_GUIDE_APPLY',0],'guide_json':json.dumps({**policy,'stage':'after'},ensure_ascii=False)}}
    graph['126']['inputs']['conditioning']=['USER_GUIDE_AFTER',0]
    # Preserve the contract through pruning and all actual execution snapshots.
    graph['USER_GUIDE_BEFORE']['inputs']['spec_json']=[SPEC,0]
    graph['USER_GUIDE_AFTER']['inputs']['spec_json']=[SPEC,0]
    p.prune(graph,['126']) # Reject a conditioning/latent loop before any queue submission.
    return graph,policy

def submission_check(graph,context,index,attempt,history=False):
    saved=attempt.get('snapshot',{}).get('user_guide')
    current=spec(graph,index)
    present=bool(RESERVED.intersection(graph))
    if saved is None:
        if current is not None or present:raise ValueError('关键帧提交绑定未经过准备，不允许临时插入')
        return
    if history:
        from .adaptive_bridge import history_graph_matches
        matches=history_graph_matches(attempt,graph)
    else:matches=p.graph_digest(graph)==attempt.get('graph_sha256')
    if current is None or not present or not matches:raise ValueError('关键帧提交图或执行快照被删除/修改，未提交GPU')
    verify_spec(graph,index)
    for key,stage in [('USER_GUIDE_BEFORE','before'),('USER_GUIDE_AFTER','after')]:
        policy=json.loads(graph[key]['inputs']['guide_json'])
        if policy.get('stage')!=stage or policy_hash(policy)!=policy_hash(saved):raise ValueError('关键帧段号/执行身份不匹配')
    if saved['context']!=context or saved['segment_index']!=index or saved['attempt_id']!=attempt['attempt_id']:raise ValueError('关键帧与本段尝试身份不匹配')

class H3SixUserGuideAudit:
    CATEGORY='H3/六段关键帧'
    RETURN_TYPES=('CONDITIONING','LATENT','IMAGE')
    FUNCTION='audit'
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'conditioning':('CONDITIONING',),'latent':('LATENT',),'image':('IMAGE',),'plan_json':('STRING',),'guide_json':('STRING',),'spec_json':('STRING',),'segment_index':('INT',),'project_id':('STRING',)}}
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def audit(self,conditioning,latent,image,plan_json,guide_json,spec_json,segment_index,project_id):
        import torch
        from comfy.ldm.minimax.model import FRAME_PER_TOKEN
        policy=json.loads(guide_json);original=json.loads(spec_json)
        if any(policy.get(k)!=v for k,v in original.items()):raise ValueError('关键帧执行快照绑定发生串段')
        source=source_info(policy['source'],policy['source_sha256'])
        if source['pixel_sha256']!=policy['pixel_sha256'] or list(image.shape)!=policy['image_shape'] or image.shape[0]!=1 or p.codec.digest(image.detach().to('cpu',torch.float32).contiguous().numpy().tobytes())!=policy['pixel_sha256']:raise ValueError('关键帧实际模型图片与上传来源不一致')
        plan=json.loads(plan_json)
        if int(plan['video_prefix_frames'])!=policy['protected_frames'] or plan.get('segment_index',segment_index)!=policy['segment_index'] or segment_index!=policy['segment_index'] or project_id!=policy['context']['project_id']:raise ValueError('关键帧实际Native保护区/段号不匹配')
        video=latent['samples'].unbind()[0]
        frames=sum(FRAME_PER_TOKEN[k%5] for k in range(video.shape[2]))
        if frames!=policy['frames']:raise ValueError('关键帧实际采样帧数与编译值不匹配')
        if policy['managed']:
            from comfy_execution.utils import get_executing_context
            executing=get_executing_context()
            if executing is None or not executing.prompt_id:raise ValueError('关键帧缺少实际服务器执行prompt_id')
            ctx=policy['context'];_,data=p.bound_context(ctx);entry=data['segments'][str(policy['segment_index'])];attempt=entry.get('attempt',{})
            p.attempt_check(ctx,policy['segment_index'],data,attempt)
            if attempt.get('attempt_id')!=policy['attempt_id'] or attempt.get('prompt_id')!=executing.prompt_id or policy_hash(attempt.get('snapshot',{}).get('user_guide',{}))!=policy_hash(policy):raise ValueError('关键帧实际执行任务身份与本段快照不匹配')
        positions=[k.get('resolved_frame_index') for item in conditioning for k in item[1].get('minimax_keyframes',[])]
        count=positions.count(policy['model_frame'])
        if policy['stage']=='before' and count or policy['stage']=='after' and count!=len(conditioning):raise ValueError('关键帧实际位置缺失或与已有Guide重复冲突')
        return conditioning,latent,image

def register():
    import asyncio
    from aiohttp import web
    from server import PromptServer
    @PromptServer.instance.routes.post('/h3/six-guide/preflight')
    async def preflight_route(request):
        try:
            data=await request.json()
            value=await asyncio.to_thread(preflight,data['graph'],int(data['index']),data.get('config'),data.get('inherit') is True,data['snapshot_id'])
            return web.json_response({'guide':value})
        except Exception as ex:return web.json_response({'error':str(ex)},status=400)
    @PromptServer.instance.routes.post('/h3/six-guide/compile')
    async def compile_route(request):
        try:
            data=await request.json();graph=p.clean_graph(data['graph'])
            graph,policy=await asyncio.to_thread(apply,graph,data['context'],int(data['index']),data['attempt_id'],False)
            return web.json_response({'graph':graph,'guide':policy})
        except Exception as ex:return web.json_response({'error':str(ex)},status=400)
