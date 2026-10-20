"""Exact MiniMaxH3 residency release after sampling, before all VAE branches."""

import folder_paths
import json
import logging
import os
from pathlib import Path
import sys
import time
import comfy.model_management as mm


def audit_module():
    path=Path(__file__).parent.parent/'h3_sampler_to_vae_residency_probe'/'__init__.py'
    for module in tuple(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if filename and Path(filename)==path and hasattr(module,'model_snapshot'):
            return module
    raise RuntimeError('Loaded read-only transition observer unavailable')


class H3SelectiveDiffusionUnloadBeforeVAE:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'latent':('LATENT',)},'hidden':{'prompt':'PROMPT','unique_id':'UNIQUE_ID'}}
    RETURN_TYPES=('LATENT',)
    RETURN_NAMES=('latent',)
    FUNCTION='release'
    CATEGORY='H3/diagnostics'
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')

    def release(self,latent,prompt,unique_id):
        record={'schema':'H3_SELECTIVE_DIFFUSION_UNLOAD_BEFORE_VAE_CANARY_V1','pid':os.getpid(),'epoch':time.time(),'status':'FAIL_CLOSED'}
        folder=Path(folder_paths.get_user_directory())/'h3_selective_diffusion_unload'
        folder.mkdir(parents=True,exist_ok=True)
        output=folder/f'release_{os.getpid()}_{time.time_ns()}.json'
        try:
            audit=audit_module()
            ancestors=set()
            def visit(nid):
                nid=str(nid)
                if nid in ancestors:return
                ancestors.add(nid)
                for value in prompt[nid]['inputs'].values():
                    if isinstance(value,list) and len(value)==2 and str(value[0]) in prompt:visit(value[0])
            visit(unique_id)
            loaders=[n for nid,n in prompt.items() if str(nid) in ancestors and n['class_type']=='UNETLoader']
            pdds=[n for nid,n in prompt.items() if str(nid) in ancestors and n['class_type']=='MiniMaxH3PDDAccApply']
            if len(loaders)!=1 or loaders[0]['inputs'].get('unet_name')!='minimax_h3_ref2va_pruned_int8_convrot.safetensors' or len(pdds)!=1 or pdds[0]['inputs'].get('pdd_file')!='MiniMax-H3-Ref2VA-Acc-8Step.safetensors':
                raise RuntimeError('Unique graph INT8 H3/PDD identity not proven')
            targets=[]
            for entry in tuple(mm.current_loaded_models):
                patcher=entry.model
                if patcher is not None and type(patcher.model).__module__=='comfy.model_base' and type(patcher.model).__qualname__=='MiniMaxH3':
                    targets.append((entry,patcher,patcher.model))
            record['H3_MATCH_COUNT']=len(targets)
            if len(targets)!=1:raise RuntimeError('Expected exactly one exact MiniMaxH3 LoadedModel')
            entry,patcher,model=targets[0]
            if entry.real_model is None or entry.real_model() is not model or entry.model is not patcher or not patcher.is_dynamic():
                raise RuntimeError('LoadedModel/patcher/model identity mismatch')
            if not 19<=entry.model_memory()/audit.shared.GIB<=20.5 or len(patcher.patches)!=308:
                raise RuntimeError('H3 model size / PDD 308 patch guard failed')
            before=audit.shared.snapshot()
            before['target']=audit.model_snapshot(entry)
            record['before']=before
            target=before['target']
            if before['MEASUREMENT_ERRORS'] or target['errors'] or target['pins']['TE_PIN_REGISTERED_GIB']<18:
                raise RuntimeError('Pre-release measurement insufficient')
            peers=tuple(id(x) for x in mm.current_loaded_models if x is not entry)
            record['identities']={'entry':id(entry),'patcher':id(patcher),'model':id(model)}
            record['MODEL_UNLOAD_CALLED']=True
            result=entry.model_unload(memory_to_free=None,unpatch_weights=True)
            if result is not True:raise RuntimeError('Full unload not reported')
            if entry.model is not patcher or patcher.model is not model:raise RuntimeError('Target identity changed')
            for i,x in enumerate(mm.current_loaded_models):
                if x is entry:
                    del mm.current_loaded_models[i]
                    break
            if tuple(id(x) for x in mm.current_loaded_models if x is not entry)!=peers:
                raise RuntimeError('Peer entry changed')
            after=audit.shared.snapshot()
            after['target']=audit.model_snapshot(entry)
            after['H3_ENTRY_PRESENT_AFTER']=any(x is entry for x in mm.current_loaded_models)
            record['after']=after
            record['H3_UNLOAD_FREED_PINNED_GIB']=target['pins']['TE_PIN_REGISTERED_GIB']-after['target']['pins']['TE_PIN_REGISTERED_GIB']
            post=after['target']
            if after['MEASUREMENT_ERRORS'] or post['errors'] or after['H3_ENTRY_PRESENT_AFTER'] or record['H3_UNLOAD_FREED_PINNED_GIB']<18 or post['pins']['TE_PIN_REGISTERED_GIB']>.05 or post['pins']['TE_HOSTBUFFER_GIB']>.05 or post['loaded_size_gib']>.05:
                raise RuntimeError('Insufficient H3 release; VAE branches blocked')
            record['status']='PASS'
            # Arm existing read-only VAE load/decode observer AFTER successful release.
            audit.H3SamplerToVAEResidencyProbe().observe(latent)
            return {'ui':{'text':[json.dumps(record)]},'result':(latent,)}
        except Exception as e:
            record['error']=f'{type(e).__name__}: {e}'
            raise
        finally:
            output.write_text(json.dumps(record,indent=2),encoding='utf-8')
            logging.info('H3SelectiveDiffusionUnload status=%s path=%s',record['status'],output)


NODE_CLASS_MAPPINGS={'H3SelectiveDiffusionUnloadBeforeVAE':H3SelectiveDiffusionUnloadBeforeVAE}
