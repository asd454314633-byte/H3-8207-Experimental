"""CPU-only validation before PreBake, with authoritative predecessor provenance."""
import asyncio,json,math,subprocess
from pathlib import Path
import folder_paths
from .nodes import sha,inherited_plan,probe_frames

def validate_start(data):
    start=float(data['start_seconds'])
    if not math.isfinite(start) or start<0:raise ValueError('音频起点须为非负有限秒数')
    source=data['source']
    path=Path(source) if Path(source).is_absolute() else Path(folder_paths.get_annotated_filepath(source))
    path=path.resolve(strict=True)
    probe=subprocess.run(['ffprobe','-v','error','-select_streams','a:0','-show_entries','stream=duration:format=duration','-of','json',str(path)],capture_output=True,text=True,check=True,timeout=15)
    meta=json.loads(probe.stdout)
    if not meta.get('streams'):raise ValueError('源文件没有音轨')
    duration=float(meta['streams'][0].get('duration') or meta['format']['duration'])
    if start>=duration:raise ValueError('音频起点超过源音轨结尾')
    digest=sha(path)
    cross=data.get('cross_group')
    if cross:
        from .cross_group import verify_contract
        cross=verify_contract(cross)
        if digest.lower()!=cross['song_sha256'] or start!=cross['song_start']:raise ValueError('跨组原曲音频身份/起点不匹配')
    if data.get('inherit') and not (cross and int(data['segment_index'])==0):
        project=data['project_id'];index=int(data['segment_index'])
        if not project or len(project)>64 or any(not(c.isalnum() or c in '-_') for c in project) or not 1<=index<=5:raise ValueError('非法长歌续接标识')
        root=Path(folder_paths.get_output_directory())/'h3_continuation'/project
        receipts=json.loads((root/'six_acceptance.json').read_text('utf-8'))
        receipt=receipts.get(str(index-1),{})
        if receipt.get('status')!='SUCCESS':raise ValueError('前段没有真实SUCCESS回执')
        timeline_path=root/'long_song_timeline.json'
        timeline=json.loads(timeline_path.read_text('utf-8')) if timeline_path.exists() else {}
        prior=timeline.get(str(index-1)) or inherited_plan(folder_paths.get_output_directory(),receipt,index-1)
        if not prior:raise ValueError('前段缺少原曲时间轴，禁止猜测续接位置')
        if prior['source_sha256'].lower()!=digest.lower() or float(prior['song_start'])!=start:
            raise ValueError(f'音频起点或源文件已变化（前段起点{prior["song_start"]}秒，本次{start}秒）。请从第1段重新生成；旧视频和历史仍保留')
        if prior.get('cross_group')!=cross:raise ValueError('跨组旧链与当前组前驱不匹配')
    if cross:
        index=int(data['segment_index']);previous=0
        if index>0:
            # Current accepted first-to-previous clips, including inherited execution forks.
            for i in range(index):
                r=receipts.get(str(i),{});p=timeline.get(str(i)) or inherited_plan(folder_paths.get_output_directory(),r,i)
                if r.get('status')!='SUCCESS' or not p or p.get('cross_group')!=cross:raise ValueError('本组跨组时间轴/成功回执不完整')
                if sha(Path(r['video_path'])).upper()!=r.get('video_sha256','').upper():raise ValueError('本组前段视频SHA256不匹配')
                previous+=probe_frames(Path(r['video_path']))
        frames=data.get('frames')
        if frames is None and data.get('graph'):
            from .recovery import production_module
            graph=data['graph'];frames=production_module().scalar(graph['136']['inputs']['length'],graph)
        if type(frames) is not int or frames<48 or frames%17!=5:raise ValueError('跨组生成帧数无法确认')
        prefix=0 if data.get('clean_rebase') else 39
        raw_start=cross['global_boundary']+(previous-prefix)/24
        raw_end=raw_start+frames/24
        if raw_start<0 or raw_end>duration+1/48000:raise ValueError(f'原曲剩余不足：本段需到{raw_end:.6f}秒，源音轨结束于{duration:.6f}秒；请缩短本段时长，未提交GPU')
    return {'start_seconds':start,'source_sha256':digest,'duration_seconds':duration,'source':str(path)}

def register():
    from aiohttp import web
    from server import PromptServer
    @PromptServer.instance.routes.post('/h3/long-song/validate-start')
    async def route(request):
        try:return web.json_response(await asyncio.to_thread(validate_start,await request.json()))
        except Exception as exc:return web.json_response({'error':str(exc)},status=400)
