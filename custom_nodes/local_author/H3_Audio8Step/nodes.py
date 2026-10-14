"""Candidate-only reference validation. Never mutate PCM, latent, model or masks."""
import re
import torch

class H3Audio8ReferencePreflight:
    CATEGORY='H3/8步音频参考'
    FUNCTION='check'
    RETURN_TYPES=('AUDIO','AUDIO','AUDIO','AUDIO','STRING')
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'prompt':('STRING',{'forceInput':True}),
            **{k:('BOOLEAN',{'default':False}) for k in ['audio1_enabled','audio2_enabled','audio3_enabled','soundtrack_enabled']},
            'role3':('STRING',{'default':''})},
            'optional':{k:('AUDIO',{'lazy':True}) for k in ['audio1','audio2','audio3','soundtrack']}}
    def check_lazy_status(self,**kw):
        return [k for k in ['audio1','audio2','audio3','soundtrack'] if kw.get(k+'_enabled') and kw.get(k) is None]
    def check(self,prompt,audio1_enabled=False,audio2_enabled=False,audio3_enabled=False,soundtrack_enabled=False,role3='',**kw):
        total=0.; values={};mapping={};ordinal=1
        for key,enabled in [('soundtrack',soundtrack_enabled),('audio1',audio1_enabled),('audio2',audio2_enabled),('audio3',audio3_enabled)]:
            if not enabled:continue
            a=kw.get(key)
            if a is None:raise ValueError('已启用的参考音频为空：'+key)
            w=a.get('waveform');sr=a.get('sample_rate')
            if not isinstance(w,torch.Tensor) or w.ndim!=3 or w.shape[0]!=1 or w.shape[1] not in (1,2) or w.shape[-1]==0 or not isinstance(sr,(int,float)) or sr<=0:
                raise ValueError('参考音频须为有效单条 mono/stereo：'+key)
            if not torch.isfinite(w).all():raise ValueError('参考音频包含 NaN/Inf：'+key)
            seconds=w.shape[-1]/sr
            if (key!='soundtrack' and not 2<=seconds<=15) or seconds>15:raise ValueError('音色参考须为2～15秒，视频音轨不得超过15秒：'+key)
            total+=seconds;values[key]=a
            if key!='soundtrack':mapping[int(key[-1])]=ordinal
            ordinal+=1
        if total>15+1e-6:raise ValueError(f'启用的参考音频合计 {total:.4f} 秒，超过15秒；预检不修改输入，请自行缩短。')
        if not values:return None,None,None,None,prompt
        if audio3_enabled and role3.strip():prompt+='\n<Audio 3> '+role3.strip()
        def remap(m):
            i=int(m.group(1))
            if i not in mapping:raise ValueError(f'提示词引用未开启音频 <Audio {i}>')
            return f'<Audio {mapping[i]}>'
        prompt=re.sub(r'<Audio\s+(\d+)>',remap,prompt,flags=re.I)
        if '<VideoSoundtrack>' in prompt:
            if not soundtrack_enabled:raise ValueError('视频音轨参考未启用')
            prompt=prompt.replace('<VideoSoundtrack>','<Audio 1>')
        return *(values.get('audio'+str(i)) for i in [1,2,3]),values.get('soundtrack'),prompt

NODE_CLASS_MAPPINGS={'H3Audio8ReferencePreflight':H3Audio8ReferencePreflight}
