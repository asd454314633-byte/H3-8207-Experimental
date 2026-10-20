"""8207 opt-in long soundtrack adapter. No model/sampler patches."""
import functools
import hashlib
import json
import math
import os
import subprocess
import time
import uuid
from pathlib import Path
import numpy as np
import torch
import folder_paths
from .timeline_contract import validate_plan_chain

SR = 48000

def sha(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def interval(frames, previous_kept, prefix, start, fps=24, external_first=False,
             output_discard_frames=0):
    if fps != 24 or not math.isfinite(start) or start < 0:
        raise ValueError('长歌当前只支持原生24fps；起始秒须有限且非负')
    if frames < 48 or frames % 17 != 5:
        raise ValueError('生成帧数须为合法17k+5网格；参考音频由适配器内部限长')
    if prefix not in (0, 39) or output_discard_frames not in (0, 39):
        raise ValueError('非法Native前缀或输出裁剪帧数')
    if prefix and output_discard_frames:
        raise ValueError('Native保护前缀与Clean Rebase输出裁剪不能同时使用')
    overlap = prefix + output_discard_frames
    if overlap >= frames:
        raise ValueError('前缀/裁剪长度必须小于模型帧数')
    if previous_kept < overlap and not (external_first and previous_kept==0 and prefix==39):
        raise ValueError('非法Native前缀或已保存帧数')
    begin = start + (previous_kept - overlap) / fps
    return {'source_start': begin, 'source_end': begin + frames / fps,
            'frames': frames, 'prefix_frames': prefix,
            'output_discard_frames': output_discard_frames,
            'kept_frames': frames-overlap,
            'output_start': start + previous_kept / fps,
            'output_end': start + (previous_kept + frames-overlap) / fps}

@functools.lru_cache(maxsize=2)
def decode(path, digest):
    # Full MP4 is decoded for audio only; the original remains untouched.
    data = subprocess.run(['ffmpeg','-v','error','-i',path,'-map','0:a:0',
        '-vn','-ac','2','-ar',str(SR),'-f','f32le','pipe:1'],
        capture_output=True, check=True, timeout=90).stdout
    return torch.from_numpy(np.frombuffer(data, dtype='<f4').copy().reshape(-1,2).T).unsqueeze(0)

def probe_frames(path):
    p = subprocess.run(['ffprobe','-v','error','-select_streams','v:0',
        '-show_entries','stream=nb_frames,avg_frame_rate','-of','json',str(path)],
        capture_output=True, text=True, encoding='utf-8', check=True, timeout=15)
    stream=json.loads(p.stdout)['streams'][0]
    a,b=map(int,stream['avg_frame_rate'].split('/'))
    if a/b != 24: raise ValueError('前段实际视频帧率不是24fps')
    return int(stream['nb_frames'])

def inherited_plan(output_root, receipt, index):
    """Resolve only the exact accepted ancestor named by the existing receipt."""
    parent=receipt.get('inherited_from',{}).get('project_id')
    if not parent or len(parent)>64 or any(not(c.isalnum() or c in '-_') for c in parent):return None
    directory=Path(output_root)/'h3_continuation'/parent
    path=directory/'long_song_timeline.json'
    if not path.exists():return None
    records=json.loads((directory/'six_acceptance.json').read_text('utf-8'))
    original=records.get(str(index),{})
    if original.get('status')!='SUCCESS' or any(original.get(k)!=receipt.get(k) for k in ('prompt_id','video_sha256','latent_sha256')):
        raise ValueError('长歌历史时间轴与继承SUCCESS回执不匹配')
    plan=json.loads(path.read_text('utf-8')).get(str(index))
    if not isinstance(plan,dict):return None
    if 'fps' in plan:
        saved=plan.get('execution_receipt')
        if (not isinstance(saved,dict) or saved.get('prompt_id')!=original.get('prompt_id') or
                saved.get('project_id')!=original.get('project_id') or
                saved.get('group_id')!=original.get('group_id') or
                saved.get('execution_version')!=original.get('execution_version') or
                saved.get('source_sha256','').lower()!=plan.get('source_sha256','').lower()):
            raise ValueError('新版长歌时间轴缺少与SUCCESS回执匹配的执行身份')
    return plan

class H3LongSongSegment:
    CATEGORY='H3/长歌曲'
    RETURN_TYPES=('AUDIO','STRING','AUDIO')
    RETURN_NAMES=('完整原曲本段音轨','时间轴JSON','模型参考音频（最多15秒）')
    FUNCTION='slice'
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'source':('STRING',{'default':''}),
            'start_seconds':('FLOAT',{'default':0.,'min':0}),
            'frames':('INT',{'default':243,'min':48}),
            'project_id':('STRING',{'default':''}),
            'segment_index':('INT',{'default':0,'min':0,'max':5}),
            'inherit':('BOOLEAN',{'default':False}),
            'clean_rebase':('BOOLEAN',{'default':False}),
            'fps':('FLOAT',{'default':24})},'optional':{
                'cross_group_json':('STRING',{'default':''}),
                'clean_rebase_output_discard_frames':('INT',{'default':0,'min':0,'max':39})}}
    @classmethod
    def IS_CHANGED(cls, **kw): return float('nan')  # exact predecessor receipt is runtime state
    def slice(self, source, start_seconds, frames, project_id, segment_index,
              inherit, clean_rebase, fps=24,cross_group_json='',
              clean_rebase_output_discard_frames=0):
        if not project_id or len(project_id)>64 or any(not(c.isalnum() or c in '-_') for c in project_id):
            raise ValueError('非法长歌项目标识')
        path=Path(source) if Path(source).is_absolute() else Path(folder_paths.get_annotated_filepath(source))
        path=path.resolve(strict=True); digest=sha(path)
        cross=None
        if cross_group_json:
            from .cross_group import verify_contract
            cross=verify_contract(cross_group_json)
            if not inherit or cross['source_project']==project_id or digest.lower()!=cross['song_sha256'] or start_seconds!=cross['song_start']:
                raise ValueError('跨组歌曲/起点/目标身份不匹配')
            if segment_index==0 and clean_rebase:raise ValueError('跨组第1段不能Clean Rebase')
        if clean_rebase_output_discard_frames not in (0,39):
            raise ValueError('Clean Rebase输出裁剪只允许0或39帧')
        if clean_rebase_output_discard_frames and (not clean_rebase or segment_index <= 0):
            raise ValueError('Clean Rebase输出裁剪只允许用于续接段')
        root=Path(folder_paths.get_output_directory())/'h3_continuation'/project_id
        timeline_path=root/'long_song_timeline.json'
        timeline=json.loads(timeline_path.read_text('utf-8')) if timeline_path.exists() else {}
        previous_kept=0
        origin_index=segment_index
        # Use actual accepted output frames, never multiply the current length by index.
        if inherit and segment_index>0:
            receipts=json.loads((root/'six_acceptance.json').read_text('utf-8'))
            last=timeline.get(str(segment_index-1)) or inherited_plan(folder_paths.get_output_directory(),receipts.get(str(segment_index-1),{}),segment_index-1)
            if not last:raise ValueError('前段缺少绑定歌曲时间轴')
            origin_index=int(last.get('origin_index',0))
            for i in range(origin_index,segment_index):
                receipt=receipts.get(str(i),{}); prior=timeline.get(str(i))
                if not prior:prior=inherited_plan(folder_paths.get_output_directory(),receipt,i)
                if receipt.get('status')!='SUCCESS' or not prior:
                    raise ValueError('缺少前序真实SUCCESS长歌时间轴，禁止猜测音频位置')
                if prior['source_sha256']!=digest or prior['song_start']!=start_seconds:
                    raise ValueError('歌曲或起始时间已变化，请开启新的六段项目')
                if prior.get('cross_group')!=cross:raise ValueError('跨组前驱绑定与本组历史不匹配')
                video=Path(receipt['video_path'])
                if sha(video).upper()!=receipt['video_sha256'].upper():
                    raise ValueError('前段视频SHA不匹配')
                actual=probe_frames(video)
                if actual!=prior['kept_frames']: raise ValueError('前段实际保存帧数与长歌时间轴不符')
                previous_kept+=actual
                timeline[str(i)]={**prior,'project_id':project_id}
        prefix=39 if inherit and (segment_index>0 or cross) and not clean_rebase else 0
        base=cross['global_boundary'] if cross else float(start_seconds)
        output_discard = int(clean_rebase_output_discard_frames)
        plan=interval(int(frames),previous_kept,prefix,base,float(fps),
                      external_first=bool(cross and segment_index==0),
                      output_discard_frames=output_discard)
        if cross:plan.update(cross_group=cross,group_start_seconds=base)
        waveform=decode(str(path),digest)
        begin=round(plan['source_start']*SR); end=begin+round(frames/fps*SR)
        if begin<0 or end>waveform.shape[-1]: raise ValueError('源歌曲不足以覆盖该段，禁止静默补音或循环')
        audio={'waveform':waveform[...,begin:end].clone(),'sample_rate':SR}
        reference={'waveform':audio['waveform'][...,:15*SR],'sample_rate':SR}
        plan.update(reference_source_start=plan['source_start'],
                    reference_source_end=plan['source_start']+reference['waveform'].shape[-1]/SR)
        plan.update(source=str(path),source_sha256=digest,song_start=start_seconds,
                    segment_index=segment_index,project_id=project_id,origin_index=origin_index,
                    clean_rebase=bool(clean_rebase),fps=float(fps))
        # Pending timeline is never authority without the original SUCCESS receipt.
        root.mkdir(parents=True,exist_ok=True); timeline[str(segment_index)]=plan
        validate_plan_chain(timeline,segment_index,digest,start_seconds,cross,
                            require_from_zero=False)
        tmp=timeline_path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            payload=json.dumps(timeline,ensure_ascii=False,indent=2).encode('utf-8')
            with tmp.open('wb') as stream:
                stream.write(payload);stream.flush();os.fsync(stream.fileno())
            for retry in range(6):
                try:
                    os.replace(tmp,timeline_path);break
                except PermissionError:
                    if retry==5:raise
                    time.sleep(.01*(retry+1))
        finally: tmp.unlink(missing_ok=True)
        print('[H3 LongSong] '+json.dumps(plan,ensure_ascii=False),flush=True)
        return audio,json.dumps(plan,ensure_ascii=False),reference

class H3LongSongLock:
    CATEGORY='H3/长歌曲'
    RETURN_TYPES=('LATENT',)
    FUNCTION='lock'
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'latent':('LATENT',),'audio':('AUDIO',),'audio_vae':('VAE',)}}
    def lock(self,latent,audio,audio_vae):
        import nodes
        from comfy.nested_tensor import NestedTensor
        # Native audio length is round(video_duration * 40). Its grid can be
        # up to half an audio step shorter than the video (362 frames: 8.333ms).
        # Align only the VAE encoder input; final output uses the full original PCM.
        capacity=latent['samples'].unbind()[1].shape[-1]/40
        sr=int(audio['sample_rate']); limit=round(capacity*sr)
        waveform=audio['waveform']
        if waveform.shape[-1]>limit:
            if (waveform.shape[-1]-limit)/sr > .5/40+1/sr:
                raise ValueError('音频长于Native音频latent容量，超出40Hz时间步量化容差')
            encoder_audio={'waveform':waveform[...,:limit],'sample_rate':sr}
        else:encoder_audio=audio
        result=nodes.NODE_CLASS_MAPPINGS['H3ExactAudioLock']().apply(latent,True,encoder_audio,audio_vae)[0]
        # Preserve Native's video prefix mask; lock ONLY the audio modality.
        if 'noise_mask' in latent:
            video_mask=latent['noise_mask'].unbind()[0]
            audio_mask=result['noise_mask'].unbind()[1]
            result['noise_mask']=NestedTensor((video_mask,audio_mask))
        return (result,)

NODE_CLASS_MAPPINGS={c.__name__:c for c in (H3LongSongSegment,H3LongSongLock)}
