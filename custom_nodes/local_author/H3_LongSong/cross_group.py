"""Opt-in, authenticated sixth-to-first continuation. No synthetic receipts."""
import asyncio,copy,json,math,subprocess,uuid
from pathlib import Path
import folder_paths
from .nodes import sha,probe_frames,inherited_plan
from .recovery import production_module

SCHEMA='H3_CROSS_GROUP_V1'

def directory(project):
    if not isinstance(project,str) or not project or len(project)>64 or any(not(c.isalnum() or c in '-_') for c in project):
        raise ValueError('跨组前驱项目身份无效')
    return Path(folder_paths.get_output_directory())/'h3_continuation'/project

def read(path):return json.loads(path.read_text('utf-8'))

def source_proof(project,seen=()):
    if project in seen or len(seen)>12:raise ValueError('跨组旧链循环或层级异常')
    root=directory(project);receipts=read(root/'six_acceptance.json');last=receipts.get('5',{})
    group=last.get('group_id')
    p=production_module();p.token(group)
    ledger=read(root/('prebake_'+group+'.json'));binding=ledger.get('execution',{})
    if ledger.get('project_id')!=project or binding.get('project_id')!=project or binding.get('group_id')!=group:
        raise ValueError('上一组项目/PreBake执行身份不匹配')
    timeline=read(root/'long_song_timeline.json');index=read(root/'index.json')
    plans=[];frames=[]
    from safetensors import safe_open
    for i in range(6):
        r=receipts.get(str(i),{})
        if r.get('status')!='SUCCESS':raise ValueError(f'上一组第{i+1}段没有真实成功回执')
        p.verify_predecessor({'project_id':project,'group_id':group},i+1)
        latent=root/('seg_%05d.safetensors'%i)
        with safe_open(str(latent),framework='pt',device='cpu') as f:meta=f.metadata()
        if meta.get('provider')!='CORE_NATIVE_MASKED_AV' or int(meta.get('segment_index',-1))!=i or meta.get('prompt_id')!=r.get('prompt_id'):
            raise ValueError('上一组Native Latent元数据/任务/段号不匹配')
        video=Path(r['video_path']).resolve()
        if not video.is_relative_to(Path(folder_paths.get_output_directory()).resolve()) or sha(video).upper()!=r.get('video_sha256','').upper():
            raise ValueError('上一组真实视频缺失或SHA256不匹配')
        plan=timeline.get(str(i)) or inherited_plan(folder_paths.get_output_directory(),r,i)
        if not plan:raise ValueError('上一组缺少真实音频时间轴')
        actual=probe_frames(video);prefix=int(plan['prefix_frames'])
        trims=[e for e in index.get('trim_events',[]) if int(e['segment_index'])==i]
        if prefix not in (0,39) or actual!=plan['kept_frames'] or int(meta['frames'])-prefix!=actual:
            raise ValueError('上一组实际保存帧数/39帧裁剪记录不一致')
        if (prefix==39 and (len(trims)!=1 or trims[0]['frames']!=39)) or (prefix==0 and trims):
            raise ValueError('上一组39帧不是仅裁剪一次')
        if abs(plan['source_start']+prefix/24-plan['output_start'])>1e-8 or abs(plan['output_end']-plan['output_start']-actual/24)>1e-8:
            raise ValueError('上一组音频时间轴与真实帧数不符')
        if plans and (abs(plan['output_start']-plans[-1]['output_end'])>1e-8 or plan['source_sha256']!=plans[0]['source_sha256'] or plan['song_start']!=plans[0]['song_start']):
            raise ValueError('上一组六段音频链不连续')
        plans.append(plan);frames.append(actual)
    parent=plans[0].get('cross_group')
    if parent:
        verified=verify_contract(parent,seen+(project,))
        if abs(plans[0]['output_start']-verified['global_boundary'])>1e-8:raise ValueError('旧跨组链边界不匹配')
    elif plans[0]['output_start']!=plans[0]['song_start'] or plans[0]['prefix_frames']!=0:
        raise ValueError('上一组独立起点与原始歌曲起点不匹配')
    song=Path(plans[0]['source'])
    if sha(song).lower()!=plans[0]['source_sha256'].lower():raise ValueError('原歌曲内容已变化，旧链不可复用')
    return {'schema':SCHEMA,'source_project':project,'source_group':group,
            'source_execution_version':binding['execution_version'],'source_segment_index':5,
            'source_prompt_id':last['prompt_id'],'source_latent_sha256':sha(root/'seg_00005.safetensors').upper(),
            'source_video_sha256':last['video_sha256'].upper(),'song_sha256':plans[0]['source_sha256'].lower(),
            'song_start':plans[0]['song_start'],'group_output_start':plans[0]['output_start'],
            'global_boundary':plans[-1]['output_end'],'saved_frames':sum(frames),'prefix_frames':39}

def verify_contract(contract,seen=()):
    if isinstance(contract,str):contract=json.loads(contract)
    if not isinstance(contract,dict) or contract.get('schema')!=SCHEMA:raise ValueError('跨组前驱绑定缺失或格式错误')
    actual=source_proof(contract.get('source_project'),seen)
    if contract!=actual:raise ValueError('跨组旧链/前驱回执/时间轴已变化，请重新核验绑定；未提交GPU')
    return actual

def check_requested_start(proof,value,origin,continuous,independent):
    value=float(value)
    if not math.isfinite(value) or (origin!='起始秒设置' and abs(value-proof['global_boundary'])>1e-8) or (origin=='起始秒设置' and value not in (proof['song_start'],proof['global_boundary'])):
        raise ValueError(f'音频位置冲突：上一组已到{proof["global_boundary"]}秒，本次要求{value}秒')
    if not continuous or independent:raise ValueError('请启用连续生成并选择连续续跑；跨组不能独立开始')

def graph_contract(graph):
    raw=graph.get('LONG_SONG',{}).get('inputs',{}).get('cross_group_json','')
    return json.loads(raw) if raw else None

def verify_graph(graph,context,index,prepared=None):
    proof=graph_contract(graph)
    if prepared is not None and proof!=prepared:raise ValueError('跨组提交绑定被删除或替换')
    if not proof:
        if 'CROSS_GROUP_PREVIOUS' in graph:raise ValueError('跨组Latent缺少音频时间轴绑定')
        return None
    proof=verify_contract(proof)
    if proof['source_project']==context['project_id']:raise ValueError('跨组不得把当前组伪装成上一组')
    song=graph['LONG_SONG']['inputs']
    if song.get('project_id')!=context['project_id'] or song.get('segment_index')!=index or song.get('start_seconds')!=proof['song_start'] or song.get('inherit') is not True:
        raise ValueError('跨组音频/目标项目/段号不匹配')
    if index==0:
        for kind in ('H3ContinuationPrepare','H3ContinuationGuides','H3ContinuationTrimOnce','H3ContinuationSave','H3ContinuationAssemble'):
            if sum(n['class_type']==kind for n in graph.values())!=1:raise ValueError('跨组Native节点缺失或重复：'+kind)
        prep=next(n['inputs'] for n in graph.values() if n['class_type']=='H3ContinuationPrepare')
        loader=graph.get('CROSS_GROUP_PREVIOUS',{})
        if loader.get('class_type')!='H3CrossGroupPrevious' or loader.get('inputs',{}).get('cross_group_json')!=song['cross_group_json'] or loader['inputs'].get('target_project')!=context['project_id']:
            raise ValueError('跨组第1段必须显式绑定真实第6段Latent')
        if prep.get('enabled') is not True or prep.get('prev_latent')!=['CROSS_GROUP_PREVIOUS',0] or (prep.get('clean_rebase_enabled') and prep.get('clean_rebase_segment')==0):
            raise ValueError('跨组第1段Native继承接口/模式不正确')
        for kind in ('H3ContinuationGuides','H3ContinuationTrimOnce'):
            node=next(n['inputs'] for n in graph.values() if n['class_type']==kind)
            if node.get('enabled') is not True:raise ValueError('跨组39帧Guide保护/裁剪未启用')
            if kind=='H3ContinuationTrimOnce' and node.get('trim_frames',39)!=39:raise ValueError('跨组必须仅裁39帧')
        audit=graph.get('CROSS_GROUP_AUDIT',{})
        if audit.get('class_type')!='H3CrossGroupPrefixAudit' or audit.get('inputs',{}).get('cross_group_json')!=song['cross_group_json']:
            raise ValueError('跨组缺少真实Native前缀核验')
        prepare_id=next(k for k,n in graph.items() if n['class_type']=='H3ContinuationPrepare')
        if prep.get('project_id')!=context['project_id'] or prep.get('segment_index')!=0:raise ValueError('跨组Native目标身份不匹配')
        guide=next(n['inputs'] for n in graph.values() if n['class_type']=='H3ContinuationGuides')
        if guide.get('protected_frames',39) not in (39,[prepare_id,2]):raise ValueError('跨组Guide保护区不是39帧')
        trim_id=next(k for k,n in graph.items() if n['class_type']=='H3ContinuationTrimOnce');trim=graph[trim_id]['inputs']
        if trim.get('project_id')!=context['project_id'] or trim.get('segment_index')!=0 or (trim.get('clean_rebase_enabled') and trim.get('clean_rebase_segment')==0):raise ValueError('跨组第1段裁剪身份或策略不正确')
        if trim.get('audio')!=['LONG_SONG',0] or graph['764']['inputs'].get('images')!=[trim_id,0] or graph['764']['inputs'].get('audio')!=[trim_id,1]:raise ValueError('跨组成片未使用唯一一次裁剪的视频及原曲音轨')
        if audit['inputs'].get('latent')!=[prepare_id,0] or audit['inputs'].get('plan_json')!=[prepare_id,1]:raise ValueError('跨组前缀核验未连接实际Native输出')
        sampler=graph['125']['inputs']['latent_image']
        if sampler==['LONG_SONG_LOCK',0]:sampler=graph['LONG_SONG_LOCK']['inputs']['latent']
        if sampler!=['CROSS_GROUP_AUDIT',0]:raise ValueError('跨组采样器未使用已核验的Native Latent')
    elif 'CROSS_GROUP_PREVIOUS' in graph:raise ValueError('跨组第2至6段不得重复继承上一组第6段')
    return proof

class H3CrossGroupPrevious:
    CATEGORY='H3/跨组';FUNCTION='load';RETURN_TYPES=('LATENT',)
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'cross_group_json':('STRING',),'target_project':('STRING',)}}
    @classmethod
    def IS_CHANGED(cls,**kw):return float('nan')
    verify=staticmethod(verify_contract);verify_graph=staticmethod(verify_graph)
    def load(self,cross_group_json,target_project):
        proof=verify_contract(cross_group_json);directory(target_project)
        if target_project==proof['source_project']:raise ValueError('跨组目标不能覆盖上一组')
        import nodes
        return nodes.NODE_CLASS_MAPPINGS['H3PreBakePreviousState']().load(proof['source_project'],6,proof['source_group'])

class H3CrossGroupPrefixAudit:
    CATEGORY='H3/跨组';FUNCTION='audit';RETURN_TYPES=('LATENT',)
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',),'plan_json':('STRING',),'cross_group_json':('STRING',)}}
    @classmethod
    def IS_CHANGED(cls,**kw):return float('nan')
    def audit(self,latent,plan_json,cross_group_json):
        import torch
        from safetensors.torch import load_file
        proof=verify_contract(cross_group_json);plan=json.loads(plan_json)
        if not plan.get('active') or plan.get('clean_rebase') or plan.get('prev_source')!='input' or plan.get('video_prefix_frames')!=39:raise ValueError('跨组没有形成真实39帧Native保护前缀')
        previous=load_file(str(directory(proof['source_project'])/'seg_00005.safetensors'),device='cpu')
        video,audio=latent['samples'].unbind();vmask,amask=latent['noise_mask'].unbind();vt=plan['video_prefix_tokens']
        import nodes,sys
        native=sys.modules[nodes.NODE_CLASS_MAPPINGS['H3ContinuationPrepare'].__module__.rsplit('.',1)[0]]
        expected,transform=native.core.adapt_video_prefix(previous['video'],tuple(video.shape),vt,video.dtype)
        if not torch.equal(video[:,:,:vt].cpu(),expected.cpu()) or transform!=plan.get('video_prefix_transform'):
            raise ValueError('跨组前缀不等于真实上一组第6段尾部')
        if not torch.all(vmask[:,:,:vt]==0) or not torch.all(vmask[:,:,vt:]==1) or plan['audio_prefix_steps']!=0 or not torch.all(amask==1):
            raise ValueError('跨组Native视频保护或原曲音频分支掩码错误')
        return (latent,)

def chain_projects(project,seen=()):
    if project in seen:raise ValueError('跨组合并链循环')
    source_proof(project)
    parent=read(directory(project)/'long_song_timeline.json')['0'].get('cross_group')
    return (chain_projects(parent['source_project'],seen+(project,)) if parent else [])+[project]

def render_media(videos,song,start,end,target):
    """Input clips already lost their protected prefix. Never trim them again."""
    counts=[probe_frames(v) for v in videos];total=sum(counts)
    if abs(total/24-(end-start))>1e-8:raise ValueError('跨组合并真实帧数与原曲区间不符')
    formats=[]
    for video in videos:
        info=json.loads(subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,codec_name','-of','json',str(video)],check=True,capture_output=True,text=True,timeout=15).stdout)['streams'][0]
        formats.append(info)
    if any(f!=formats[0] for f in formats):raise ValueError('跨组视频尺寸或编码不一致，请保持两组输出规格一致后合并')
    listing=target.with_suffix('.concat.txt')
    listing.write_text('\n'.join("file '"+p.as_posix().replace("'","'\\''")+"'\nduration "+format(n/24,'.12f') for p,n in zip(videos,counts)),'utf-8')
    try:
        subprocess.run(['ffmpeg','-v','error','-f','concat','-safe','0','-i',str(listing),'-i',song,'-map','0:v:0','-map','1:a:0','-c:v','copy','-af',f'atrim=start={start}:end={end},asetpts=PTS-STARTPTS','-c:a','aac','-b:a','192k','-movflags','+faststart',str(target)],check=True,capture_output=True,timeout=180)
        if probe_frames(target)!=total:raise ValueError('跨组合并输出帧数不匹配')
        streams=json.loads(subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,duration','-of','json',str(target)],check=True,capture_output=True,text=True,timeout=15).stdout)['streams']
        durations={s['codec_type']:float(s['duration']) for s in streams}
        if any(abs(durations.get(k,-1)-total/24)>1/24 for k in ('audio','video')):raise ValueError('跨组合并成片音画时间轴不一致')
        return {'frames':total,'audio_duration':durations['audio'],'video_duration':durations['video'],'av_drift':abs(durations['audio']-durations['video']),'additional_prefix_trim':0}
    finally:listing.unlink(missing_ok=True)

def merge_chain(project):
    """CPU remux of already-trimmed accepted clips plus one continuous original song."""
    projects=chain_projects(project)
    if len(projects)<2:raise ValueError('当前组没有真实跨组前驱，不能跨组合并')
    videos=[];total=0;start=None;end=None;song=None;proofs=[]
    for item in projects:
        proofs.append(source_proof(item));root=directory(item);receipts=read(root/'six_acceptance.json');timeline=read(root/'long_song_timeline.json')
        for i in range(6):
            plan=timeline.get(str(i)) or inherited_plan(folder_paths.get_output_directory(),receipts[str(i)],i)
            if start is None:start=plan['output_start'];song=plan['source']
            if end is not None and abs(end-plan['output_start'])>1e-8:raise ValueError('跨组合并音频位置有重叠或缺口')
            end=plan['output_end'];video=Path(receipts[str(i)]['video_path']);videos.append(video);total+=probe_frames(video)
    if abs(total/24-(end-start))>1e-8:raise ValueError('跨组合并真实帧数与音频时长不符')
    out=Path(folder_paths.get_output_directory())/'CrossGroupMerge';out.mkdir(exist_ok=True)
    key=uuid.uuid4().hex;target=out/('cross_group_'+key+'.mp4')
    stats=render_media(videos,song,start,end,target)
    # Original source/receipt/latent identities must still be identical after remux.
    if [source_proof(p) for p in projects]!=proofs:raise ValueError('跨组合并期间源证据变化')
    report={'schema':SCHEMA,'projects':projects,**stats,'source_start':start,'source_end':end,'output_sha256':sha(target),'output':{'filename':target.name,'subfolder':'CrossGroupMerge','type':'output'}}
    target.with_suffix('.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');return report

def register():
    from aiohttp import web
    from server import PromptServer
    routes=PromptServer.instance.routes
    @routes.post('/h3/cross-group/bind')
    async def bind(request):
        try:
            data=await request.json();proof=await asyncio.to_thread(source_proof,data['source_project'])
            return web.json_response({'contract':proof})
        except Exception as exc:return web.json_response({'error':'跨组前驱校验失败：'+str(exc)},status=400)
    @routes.post('/h3/cross-group/validate')
    async def validate(request):
        try:
            data=await request.json();proof=await asyncio.to_thread(verify_contract,data['contract'])
            check_requested_start(proof,data['requested_start'],data['requested_origin'],data.get('continuous'),data.get('independent'))
            return web.json_response({'contract':proof})
        except Exception as exc:return web.json_response({'error':str(exc)},status=400)
    @routes.post('/h3/cross-group/check-graph')
    async def check_graph(request):
        try:
            import execution
            data=await request.json();graph=data['graph'];song=graph['LONG_SONG']['inputs']
            proof=await asyncio.to_thread(verify_graph,graph,{'project_id':song['project_id']},song['segment_index'])
            result=await execution.validate_prompt(str(uuid.uuid4()),graph,None)
            if not result[0]:raise ValueError('ComfyUI提交图校验失败：'+json.dumps(result[1:],ensure_ascii=False))
            return web.json_response({'valid':True,'cross_group':proof,'queue_submitted':False,'gpu_runs':0,'outputs':result[2]})
        except Exception as exc:return web.json_response({'error':str(exc)},status=400)
    @routes.post('/h3/cross-group/merge')
    async def merge(request):
        try:return web.json_response(await asyncio.to_thread(merge_chain,(await request.json())['project_id']))
        except Exception as exc:return web.json_response({'error':'跨组合并失败：'+str(exc)},status=400)
