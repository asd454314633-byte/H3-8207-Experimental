"""Candidate-only H3 audio upgrade. No global model or sampler patches."""
import logging
import math
import os
import re
import tempfile
import torch
import torchaudio
import folder_paths
from comfy.nested_tensor import NestedTensor

CATEGORY = 'H3/音频专项升级'
FAST = '高速音频（保留当前8步引擎）'
STOCK = '音色优先 Stock20（原生模型·无Turbo）'
OFF = '关闭'
WITH = '随一采精修'
ONLY = '仅精修已缓存一采（不重跑画面）'

def av_parts(latent):
    s = latent['samples']
    if not getattr(s, 'is_nested', False) or len(s.unbind()) != 2:
        raise ValueError('需要 H3 音视频双流 latent。')
    v, a = s.unbind()
    if v.ndim != 5 or v.shape[1] != 24 or a.ndim != 4 or a.shape[1:3] != (32, 2):
        raise ValueError('H3 latent 形状不合法。')
    return v, a

def normalize(audio, reference=False):
    if audio is None:
        raise ValueError('已开启音频，但文件为空或源视频没有音轨。')
    w, sr = audio['waveform'], int(audio['sample_rate'])
    if w.ndim != 3 or w.shape[0] != 1 or w.shape[1] not in (1, 2) or sr <= 0 or w.shape[-1] == 0:
        raise ValueError('音频须为单条 mono/stereo，且采样率和长度有效。')
    if not torch.isfinite(w).all():
        raise ValueError('音频含 NaN/Inf。')
    duration = w.shape[-1] / sr
    if reference and not 2 <= duration <= 15:
        raise ValueError(f'独立音色参考须为 2～15 秒；当前 {duration:.4f} 秒。')
    w = w.float()
    if sr != 32000:
        w = torchaudio.functional.resample(w, sr, 32000)
    if w.shape[1] == 1:
        w = w.repeat(1, 2, 1)
    pad = (-w.shape[-1]) % 800
    if pad:
        w = torch.nn.functional.pad(w, (0, pad))
    logging.info('[H3 Audio] %.4fs, %sHz -> 32000Hz stereo; tail pad=%s (head preserved)', duration, sr, pad)
    return {'waveform': w, 'sample_rate': 32000}, duration

class H3AudioModelRoute:
    CATEGORY = CATEGORY
    FUNCTION = 'route'
    RETURN_TYPES = ('MODEL', 'SAMPLER', 'SIGMAS')
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'profile': ([FAST, STOCK],)}, 'optional': {
            'fast_model': ('MODEL', {'lazy': True}), 'fast_sampler': ('SAMPLER', {'lazy': True}),
            'fast_sigmas': ('SIGMAS', {'lazy': True}), 'stock_model': ('MODEL', {'lazy': True})}}
    def check_lazy_status(self, profile, **kw):
        names = ['stock_model'] if profile == STOCK else ['fast_model', 'fast_sampler', 'fast_sigmas']
        return [n for n in names if kw.get(n) is None]
    def route(self, profile, **kw):
        if profile == FAST:
            return kw['fast_model'], kw['fast_sampler'], kw['fast_sigmas']
        from comfy_extras.nodes_custom_sampler import BasicScheduler
        import comfy.samplers
        model = kw['stock_model']
        # stock_model comes directly from N620 through native SigmaShift 12/3.
        return model, comfy.samplers.ksampler('res_multistep'), BasicScheduler.execute(model, 'beta', 20, 1.0)[0]

class H3AudioFile:
    CATEGORY = CATEGORY
    FUNCTION = 'load'
    RETURN_TYPES = ('AUDIO',)
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'audio': ('STRING', {'default': ''})}}
    @classmethod
    def IS_CHANGED(cls, audio):
        import hashlib
        if not audio:
            return ''
        path = folder_paths.get_annotated_filepath(audio)
        if not os.path.isfile(path):
            return 'missing'
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for b in iter(lambda: f.read(1048576), b''):
                h.update(b)
        return h.hexdigest()
    def load(self, audio):
        if not audio:
            raise ValueError('已开启音频功能，请先上传对应音频文件。')
        from comfy_extras.nodes_audio import LoadAudio
        return (LoadAudio.execute(audio)[0],)

class H3AudioReferencePack:
    CATEGORY = CATEGORY
    FUNCTION = 'prepare'
    RETURN_TYPES = ('AUDIO', 'AUDIO', 'AUDIO', 'AUDIO', 'STRING')
    RETURN_NAMES = ('音色1', '音色2', '音色3', '视频音轨', '映射后提示词')
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'prompt': ('STRING', {'forceInput': True}),
            'audio1_enabled': ('BOOLEAN', {'default': False}), 'audio2_enabled': ('BOOLEAN', {'default': False}),
            'audio3_enabled': ('BOOLEAN', {'default': False}), 'soundtrack_enabled': ('BOOLEAN', {'default': False}),
            'role3': ('STRING', {'default': '', 'multiline': True})},
            'optional': {n: ('AUDIO', {'lazy': True}) for n in ['audio1', 'audio2', 'audio3', 'soundtrack']}}
    def check_lazy_status(self, **kw):
        return [n for n in ['audio1', 'audio2', 'audio3', 'soundtrack'] if kw.get(n + '_enabled') and kw.get(n) is None]
    def prepare(self, prompt, audio1_enabled, audio2_enabled, audio3_enabled, soundtrack_enabled, role3='', **kw):
        flags = [audio1_enabled, audio2_enabled, audio3_enabled]
        audios, durations, mapping = [None] * 3, [], {}
        track = None
        ordinal = 1
        if soundtrack_enabled:
            track, duration = normalize(kw.get('soundtrack'))
            if duration > 15:
                raise ValueError('参考视频音轨超过15秒，请先截取对应参考片段。')
            durations.append(duration)
            ordinal += 1
        for i, enabled in enumerate(flags):
            if enabled:
                audios[i], duration = normalize(kw.get(f'audio{i+1}'), True)
                durations.append(duration)
                mapping[i+1] = ordinal
                ordinal += 1
        if sum(durations) > 15 + 1e-6:
            raise ValueError(f'启用的参考音频合计 {sum(durations):.4f} 秒，超过15秒；请缩短参考片段。')
        if audio3_enabled and role3.strip():
            prompt += '\n<Audio 3> ' + role3.strip()
        def remap(m):
            i = int(m.group(1))
            if i not in mapping:
                raise ValueError(f'提示词引用了未开启的音色槽位 <Audio {i}>。')
            return f'<Audio {mapping[i]}>'
        # Source <Audio 1/2/3> always denotes the standalone source slot.
        # Native H3 numbers soundtrack first; <VideoSoundtrack> is an explicit alias.
        prompt = re.sub(r'<Audio\s+(\d+)>', remap, prompt, flags=re.I)
        if '<VideoSoundtrack>' in prompt:
            if not soundtrack_enabled:
                raise ValueError('提示词引用视频音轨，但视频音轨参考未开启。')
            prompt = prompt.replace('<VideoSoundtrack>', '<Audio 1>')
        return *audios, track, prompt

class H3ExactAudioLock:
    CATEGORY = CATEGORY
    FUNCTION = 'apply'
    RETURN_TYPES = ('LATENT',)
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'latent': ('LATENT',), 'enabled': ('BOOLEAN', {'default': False})},
            'optional': {'audio': ('AUDIO', {'lazy': True}), 'audio_vae': ('VAE', {'lazy': True})}}
    def check_lazy_status(self, enabled, **kw):
        return [n for n in ['audio', 'audio_vae'] if enabled and kw.get(n) is None]
    def apply(self, latent, enabled, audio=None, audio_vae=None):
        if not enabled:
            return (latent,)
        video, target = av_parts(latent)
        normalized, duration = normalize(audio)
        max_duration = target.shape[-1] / 40
        if duration > max_duration + 1e-6:
            raise ValueError(f'指定音轨 {duration:.4f} 秒长于合法生成时长 {max_duration:.4f} 秒；请延长视频，禁止静默裁掉台词。')
        if int(getattr(audio_vae, 'audio_sample_rate', 0)) != 32000:
            raise ValueError('指定音轨需要原生 H3 32kHz Audio VAE。')
        w = normalized['waveform']
        target_samples = target.shape[-1] * 800
        w = torch.nn.functional.pad(w, (0, target_samples - w.shape[-1]))
        encoded = audio_vae.encode(w.movedim(1, -1))
        if encoded.shape != target.shape:
            raise ValueError(f'Audio VAE 对齐失败：{encoded.shape} != {target.shape}')
        out = latent.copy()
        out['samples'] = NestedTensor((video, encoded.to(target.device)))
        out['noise_mask'] = NestedTensor((torch.ones_like(video), torch.zeros_like(target)))
        # Original PCM is kept separately from lossy VAE reconstruction.
        pcm = audio['waveform'].detach().cpu().clone()
        n = round(max_duration * int(audio['sample_rate']))
        pcm = torch.nn.functional.pad(pcm, (0, n - pcm.shape[-1]))
        out['_h3_locked_audio'] = {'waveform': pcm, 'sample_rate': int(audio['sample_rate'])}
        return (out,)

def cache_path(name):
    base = os.path.realpath(os.path.join(folder_paths.get_output_directory(), 'h3_audio_cache'))
    path = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, path]) != base or not name.endswith('.pt'):
        raise ValueError('缓存文件须在 h3_audio_cache 中，且以 .pt 结尾。')
    return path

class H3AudioSampleStore:
    CATEGORY = CATEGORY
    FUNCTION = 'store'
    RETURN_TYPES = ('LATENT',)
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'latent': ('LATENT',), 'cache_name': ('STRING', {'default': 'v282_audio_latest.pt'})}}
    def store(self, latent, cache_name):
        video, audio = av_parts(latent)
        data = {k: v for k, v in latent.items() if k not in ('samples', 'noise_mask')}
        data['video'], data['audio'] = video.detach().cpu(), audio.detach().cpu()
        data['_h3_audio_cache_version'] = 1
        path = cache_path(cache_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), suffix='.tmp')
        os.close(fd)
        try:
            torch.save(data, temp)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
        logging.info('[H3 Audio] pass1 cached: %s', path)
        return (latent,)

class H3AudioRefineGate:
    CATEGORY = CATEGORY
    FUNCTION = 'run'
    RETURN_TYPES = ('LATENT',)
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'mode': ([OFF, WITH, ONLY],), 'steps': ('INT', {'default': 6, 'min': 4, 'max': 6}),
            'denoise': ('FLOAT', {'default': 0.5, 'min': 0.1, 'max': 1, 'step': 0.05}),
            'seed': ('INT', {'default': 0, 'min': 0, 'max': 0xffffffffffffffff}),
            'cache_name': ('STRING', {'default': 'v282_audio_latest.pt'})},
            'optional': {'latent': ('LATENT', {'lazy': True}), 'stock_model': ('MODEL', {'lazy': True}),
                         'positive': ('CONDITIONING', {'lazy': True})}}
    def check_lazy_status(self, mode, **kw):
        names = ([] if mode == ONLY else ['latent']) + ([] if mode == OFF else ['stock_model', 'positive'])
        return [n for n in names if kw.get(n) is None]
    def run(self, mode, steps, denoise, seed, cache_name, latent=None, stock_model=None, positive=None):
        if mode == ONLY:
            path = cache_path(cache_name)
            if not os.path.isfile(path):
                raise ValueError('还没有一采缓存。请先关闭精修并完成一次生成。')
            data = torch.load(path, map_location='cpu', weights_only=True)
            if data.pop('_h3_audio_cache_version', None) != 1:
                raise ValueError('该缓存不是音频升级版保存的一采缓存。')
            v, a = data.pop('video'), data.pop('audio')
            latent = {**data, 'samples': NestedTensor((v, a))}
        if mode == OFF:
            return (latent,)
        if '_h3_locked_audio' in latent:
            raise ValueError('指定音轨已锁定，不允许音频精修改写；请选择关闭精修。')
        from .vendor.nodes import H3AudioRefineSampler
        video, _ = av_parts(latent)
        result = H3AudioRefineSampler().refine(stock_model, positive, positive, latent,
            seed, steps, 1.0, 'euler', 'simple', denoise, video_denoise=0.0)[0]
        _, refined = av_parts(result)
        # Explicit exact preservation even if a future core changes mask blending.
        result['samples'] = NestedTensor((video, refined))
        return (result,)

class H3AudioOutput:
    CATEGORY = CATEGORY
    FUNCTION = 'route'
    RETURN_TYPES = ('AUDIO',)
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'latent': ('LATENT',)}, 'optional': {'generated_audio': ('AUDIO', {'lazy': True})}}
    def check_lazy_status(self, latent, generated_audio=None):
        return ['generated_audio'] if '_h3_locked_audio' not in latent and generated_audio is None else []
    def route(self, latent, generated_audio=None):
        return (latent.get('_h3_locked_audio', generated_audio),)

NODE_CLASS_MAPPINGS = {c.__name__: c for c in (H3AudioModelRoute, H3AudioReferencePack,
    H3ExactAudioLock, H3AudioSampleStore, H3AudioRefineGate, H3AudioOutput, H3AudioFile)}
NODE_DISPLAY_NAME_MAPPINGS = {'H3AudioModelRoute': '音频质量档', 'H3AudioReferencePack': '三路音色预检与角色映射',
    'H3ExactAudioLock': '指定音轨驱动', 'H3AudioSampleStore': '保存一采音视频缓存',
    'H3AudioRefineGate': '音频精修（可只读一采缓存）', 'H3AudioOutput': '原音轨/生成音频输出', 'H3AudioFile': '升级音频文件（按需读取）'}
