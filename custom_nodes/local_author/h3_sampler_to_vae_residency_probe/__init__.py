"""Read-only sampler -> video VAE transition snapshots. No eviction operations."""

import folder_paths
import functools
import importlib.util
import json
import logging
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import torch
import comfy.model_management as mm
from comfy.ldm.minimax.vae import MiniMaxH3VideoVAE

_spec = importlib.util.spec_from_file_location('h3_transition_shared_snapshot',Path(__file__).parent.parent/'h3_te_residency_probe'/'__init__.py')
shared=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)
ACTIVE=None
FOLDER=Path(folder_paths.get_user_directory())/'h3_sampler_to_vae_residency_probe'


def patch_snapshot(patcher,model):
    errors=[]
    tensors={}
    adapters=set()
    def walk(value):
        if isinstance(value,torch.Tensor):
            tensors[id(value)]=value
        elif isinstance(value,dict):
            for v in value.values():walk(v)
        elif isinstance(value,(list,tuple)):
            for v in value:walk(v)
        elif type(value).__module__.startswith('comfy.weight_adapter') and id(value) not in adapters:
            adapters.add(id(value));walk(value.weights)
    walk(patcher.patches)
    raw_ids=set(tensors)
    prepared_count=0
    for module in model.modules():
        for key in ('weight_lowvram_function','bias_lowvram_function'):
            fn=module.__dict__.get(key)
            if fn is not None and getattr(fn,'prepared_patches',None) is not None:
                prepared_count+=1;walk(fn.prepared_patches)
    by_device={}
    logical=0
    for ident,t in tensors.items():
        try:
            size=int(t.numel())*int(t.element_size())
            by_device.setdefault(str(t.device),[]).append((int(t.data_ptr()),int(t.data_ptr())+size))
            if ident in raw_ids:logical+=size
        except Exception as e:errors.append(str(e))
    states={id(s):s for s in getattr(model,'dynamic_pins',{}).values()}
    pin_bytes=0;host_bytes=0;seen=set()
    for state in states.values():
        for key in ('patches','patches-loaded'):
            if key in state and id(state[key][0]) not in seen:
                host,_,_,pinned,*_=state[key]
                seen.add(id(host));pin_bytes+=int(pinned[0]);host_bytes+=int(host.size)
    return {'PDD_PATCH_COUNT':len(patcher.patches),'PDD_PATCH_TENSOR_COUNT':len(raw_ids),
            'PDD_PATCH_TOTAL_GIB':logical/shared.GIB if not errors else 'UNPROVEN',
            'PDD_PATCH_TOTAL_SCOPE':'logical bytes of original patch tensors; shared tensor identities deduplicated',
            'PDD_PATCH_RUNTIME_TENSOR_GIB_BY_DEVICE':{k:shared._union_bytes(v)/shared.GIB for k,v in by_device.items()},
            'PDD_PATCH_DEVICE':sorted(by_device),
            'PDD_PATCH_PINNED_GIB':pin_bytes/shared.GIB,
            'PDD_PATCH_HOSTBUFFER_GIB':host_bytes/shared.GIB,
            'PDD_PATCH_PIN_SCOPE':'H3 dynamic patches/patches-loaded registered counters; included in H3 residency, not additional',
            'PDD_PREPARED_PATCH_MODULE_COUNT':prepared_count,
            'PDD_TRANSFORMED_STATUS':'prepared copies present' if prepared_count else 'no prepared copies attached at snapshot; earlier transformations UNPROVEN',
            'PDD_ATTACHED_TO_H3_PATCHER':bool(patcher.patches),'PDD_ERRORS':errors}


def model_snapshot(entry):
    patcher=entry.model
    model=patcher.model
    errors=[]
    cls=type(model)
    result={'class':f'{cls.__module__}.{cls.__qualname__}','loaded_id':id(entry),'patcher_id':id(patcher),'model_id':id(model),
            'model_memory_gib':entry.model_memory()/shared.GIB,'loaded_size_gib':patcher.loaded_size()/shared.GIB,
            'device':str(patcher.current_loaded_device()),'is_dynamic':patcher.is_dynamic()}
    if (cls.__module__=='comfy.model_base' and cls.__name__=='MiniMaxH3') or (cls.__module__=='comfy.ldm.minimax.vae' and cls.__name__=='MiniMaxH3VideoVAE'):
        owners=list(model.modules())
        for module in tuple(owners):
            for key in ('weight_lowvram_function','bias_lowvram_function'):
                fn=module.__dict__.get(key)
                if fn is not None and hasattr(fn,'__dict__'):owners.append(fn)
        pins=shared._host_and_pins(SimpleNamespace(modules=lambda:iter(owners),dynamic_pins=getattr(model,'dynamic_pins',{})),errors)
        for k,v in list(pins.items()):
            if k.endswith('_BYTES') and isinstance(v,(int,float)):pins[k[:-6]+'_GIB']=v/shared.GIB
        result['pins']=pins
        state_stats={}
        for device,state in getattr(model,'dynamic_pins',{}).items():
            state_stats[str(device)]={key:{'hostbuffer_gib':int(state[key][0].size)/shared.GIB,'registered_gib':int(state[key][3][0])/shared.GIB,'stack_count':len(state[key][1])} for key in ('weights','weights-loaded','patches','patches-loaded') if key in state}
        result['dynamic_pin_subsets']=state_stats
        # Include the patch HostBuffers' registration counters; LowVramPatch is not a module.
        result['registered_all_subsets_gib']=sum(v['registered_gib'] for s in state_stats.values() for v in s.values())
        if cls.__name__=='MiniMaxH3':result['pdd']=patch_snapshot(patcher,model)
    result['errors']=errors
    return result


def snapshot(phase,extra=None):
    record={'phase':phase,'epoch':time.time(),'pid':os.getpid(),'models':[],'errors':[]}
    for entry in tuple(mm.current_loaded_models):
        if entry.model is None:continue
        try:record['models'].append(model_snapshot(entry))
        except Exception as e:record['errors'].append(f'{type(e).__name__}: {e}')
    record['GLOBAL_PINNED_GIB']=mm.TOTAL_PINNED_MEMORY/shared.GIB
    memory=shared._windows_memory()
    record.update({k[:-6]+'_GIB':v/shared.GIB for k,v in memory.items() if k.endswith('_BYTES')})
    record['SYSTEM_COMMIT_PERCENT']=memory['SYSTEM_COMMIT_PERCENT']
    if torch.cuda.is_initialized():
        free,total=torch.cuda.mem_get_info();record['GPU_VRAM_USED_GIB']=(total-free)/shared.GIB
    if extra:record.update(extra)
    FOLDER.mkdir(parents=True,exist_ok=True)
    path=FOLDER/f'{os.getpid()}_{ACTIVE["run"]}_{phase}.json'
    path.write_text(json.dumps(record,indent=2),encoding='utf-8')
    logging.info('H3SamplerToVAEResidencyProbe phase=%s path=%s',phase,path)
    return record


def observe_safe(phase,extra=None):
    try:return snapshot(phase,extra)
    except Exception as e:
        logging.error('H3 transition snapshot %s failed: %s',phase,e)


_original_load=mm.load_models_gpu
_original_decode=MiniMaxH3VideoVAE.decode


@functools.wraps(_original_load)
def observed_load(models,*args,**kwargs):
    state=ACTIVE
    if not state or state.get('loaded') or not any(type(p.model) is MiniMaxH3VideoVAE for p in models):
        return _original_load(models,*args,**kwargs)
    observe_safe('B_BEFORE_VIDEO_VAE_LOAD',{'requested_memory_bytes':kwargs.get('memory_required',0)})
    calls=[]
    previous=sys.getprofile()
    # Read call/return locals only during this existing load call. No lifecycle invocation.
    def profile(frame,event,arg):
        if frame.f_code is _original_load.__code__ and event=='return':
            state['free_for_dynamic']=frame.f_locals.get('free_for_dynamic','UNPROVEN')
        elif frame.f_code is mm.free_memory.__code__ and event=='return':
            calls.append({'for_dynamic':frame.f_locals.get('for_dynamic'),
                          'memory_required':frame.f_locals.get('memory_required'),
                          'unloaded_count':len(arg) if isinstance(arg,list) else 'UNPROVEN',
                          'unloaded_classes':[type(x.model.model).__name__ for x in arg] if isinstance(arg,list) else []})
        if previous:previous(frame,event,arg)
    sys.setprofile(profile)
    try:result=_original_load(models,*args,**kwargs)
    finally:sys.setprofile(previous)
    state['loaded']=True;state['decisions']=calls
    observe_safe('B2_VIDEO_VAE_LOADED',{'free_for_dynamic':state.get('free_for_dynamic','UNPROVEN'),'free_memory_decisions':calls})
    return result


@functools.wraps(_original_decode)
def observed_decode(self,*args,**kwargs):
    global ACTIVE
    state=ACTIVE
    if not state or not state.get('loaded') or state.get('decode_started'):
        return _original_decode(self,*args,**kwargs)
    state['decode_started']=True
    observe_safe('C_VIDEO_VAE_DECODE_START',{'free_for_dynamic':state.get('free_for_dynamic','UNPROVEN'),'free_memory_decisions':state.get('decisions',[])})
    try:return _original_decode(self,*args,**kwargs)
    finally:
        observe_safe('D_VIDEO_VAE_DECODE_END')
        ACTIVE=None


mm.load_models_gpu=observed_load
MiniMaxH3VideoVAE.decode=observed_decode


class H3SamplerToVAEResidencyProbe:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'latent':('LATENT',)}}
    RETURN_TYPES=('LATENT',)
    RETURN_NAMES=('latent',)
    FUNCTION='observe'
    CATEGORY='H3/diagnostics'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def observe(self,latent):
        global ACTIVE
        ACTIVE={'run':time.time_ns()}
        observe_safe('A_SAMPLER_END')
        return (latent,)


NODE_CLASS_MAPPINGS={'H3SamplerToVAEResidencyProbe':H3SamplerToVAEResidencyProbe}
