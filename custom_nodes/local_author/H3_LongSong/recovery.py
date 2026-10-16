"""Explicit decode-only recovery from an interrupted task's own saved Native AV."""
import copy,hashlib,json,uuid
from pathlib import Path
import folder_paths

def digest(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest().upper()

def production_module():
    # ComfyUI loads custom packages under path-derived module names, not a
    # shared custom_nodes parent package. Reuse the already registered guard.
    import nodes,sys
    package=nodes.NODE_CLASS_MAPPINGS['H3AttemptGuard'].__module__.rsplit('.',1)[0]
    return sys.modules[package+'.production']

def source_record(project_id,prompt_id,segment_index,expected_sha=None):
    from server import PromptServer
    from safetensors import safe_open
    p=production_module()
    p.token(project_id);uuid.UUID(prompt_id)
    history=PromptServer.instance.prompt_queue.get_history(prompt_id=prompt_id).get(prompt_id)
    if not history:raise ValueError('Recovery requires the exact original task history')
    graph=history['prompt'][2]
    errors=[d for e,d in history['status'].get('messages',[]) if e=='execution_interrupted']
    if len(errors)!=1 or errors[0].get('node_type')!='VAEDecode':
        raise ValueError('Only interrupted video decode with completed sampler is recoverable here')
    samplers=[k for k,n in graph.items() if n['class_type']=='SamplerCustomAdvanced']
    stores=[(k,n) for k,n in graph.items() if n['class_type']=='H3ContinuationSave' and n['inputs'].get('enabled') is True]
    if len(samplers)!=1 or len(stores)!=1 or samplers[0] not in errors[0].get('executed',[]) or stores[0][0] not in errors[0].get('executed',[]):
        raise ValueError('Original history does not prove completed sampler and Native save')
    inputs=stores[0][1]['inputs']
    if inputs.get('project_id')!=project_id or inputs.get('segment_index')!=segment_index:raise ValueError('Source project/segment mismatch')
    path=Path(folder_paths.get_output_directory())/'h3_continuation'/project_id/('seg_%05d.safetensors'%segment_index)
    sha=digest(path)
    if expected_sha and sha!=expected_sha.upper():raise ValueError('Recovery source SHA changed')
    with safe_open(str(path),framework='pt',device='cpu') as f:
        meta=f.metadata()
        if meta.get('prompt_id')!=prompt_id or meta.get('provider')!='CORE_NATIVE_MASKED_AV' or int(meta['segment_index'])!=segment_index:raise ValueError('Recovery source Native metadata mismatch')
    return history,path,sha,meta

class H3RecoveredNativeLatent:
    CATEGORY='H3/长歌曲';FUNCTION='load'
    RETURN_TYPES=('LATENT','CONDITIONING')
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'source_project':('STRING',),'source_prompt':('STRING',),'segment_index':('INT',),'source_sha256':('STRING',)}}
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def load(self,source_project,source_prompt,segment_index,source_sha256):
        _,path,_,_=source_record(source_project,source_prompt,segment_index,source_sha256)
        from safetensors.torch import load
        from comfy.nested_tensor import NestedTensor
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest().upper()!=source_sha256.upper():raise ValueError('Recovery source changed while reading')
        state=load(raw)
        if set(state)!= {'video','audio'}:raise ValueError('Recovery requires an AV Native store')
        # Empty conditioning is an unused passthrough for the existing task claim guard.
        # This graph has no sampler and never pretends to re-encode conditioning.
        return {'samples':NestedTensor((state['video'],state['audio']))},[]

def register():
    from server import PromptServer
    from aiohttp import web
    server=PromptServer.instance
    @server.routes.post('/h3/long-song/recover-export')
    async def recover(request):
        try:
            p=production_module()
            origin=request.headers.get('Origin')
            if origin and origin!=f'{request.scheme}://{request.host}':raise ValueError('Origin rejected')
            body=await request.json();ctx=body['context'];i=int(body['index'])
            # First-segment recovery is the only case required and validated here.
            if i!=0:raise ValueError('This recovery endpoint currently supports segment 1 only')
            running,queued=server.prompt_queue.get_current_queue()
            if running or queued:raise ValueError('Queue must be idle before recovery preparation')
            source_pid=body['source_prompt_id']
            h,path,sha,meta=source_record(ctx['project_id'],source_pid,i)
            original=p.read_state(p.ledger_path(ctx))['segments'][str(i)]
            if original.get('attempt',{}).get('prompt_id')!=source_pid or original['attempt'].get('stop_reason')!='TIMEOUT_300S':raise ValueError('Not the selected timed-out attempt')
            g=p.clean_graph(h['prompt'][2]);text=g['138']['inputs']['value']
            texts=body['texts']
            if len(texts)!=6 or texts[i]!=text:raise ValueError('Current first prompt differs from timed-out snapshot; refusing silent substitution')
            binding=p.execution_state.prepare({'submission_id':uuid.uuid4().hex,'context':ctx,'start_index':0,'start_mode':'resume','requested_index':i,'texts':texts,'graph':g},getattr(server,'h3_acceptance_state_lock',None))['binding']
            context={**binding,'fps':24}
            for n in g.values():
                if n['class_type'].startswith('H3Continuation') and 'project_id' in n['inputs']:n['inputs']['project_id']=binding['project_id']
            g['LONG_SONG']['inputs']['project_id']=binding['project_id']
            planned=p.plan({'graph':g,'texts':texts,'context':context,'requested_index':i,'require_predecessor':False},getattr(server,'h3_acceptance_state_lock',None))
            context.update(planned['binding']);current=planned['plans'][i]
            if current['status']!='DYNAMIC_FALLBACK':raise ValueError('Recovery expected the original dynamic audio route')
            result=p.fallback({'graph':g,'context':context,'index':i,'text':text,'cache_key':current['cache_key'],'anchor_clean_rebase':False},getattr(server,'h3_acceptance_state_lock',None))
            g=result['graph']
            g['RECOVER_NATIVE']={'class_type':'H3RecoveredNativeLatent','inputs':{'source_project':ctx['project_id'],'source_prompt':source_pid,'segment_index':i,'source_sha256':sha}}
            g['ATTEMPT_GUARD']['inputs'].update(conditioning=['RECOVER_NATIVE',1],latent=['RECOVER_NATIVE',0])
            g['122']['inputs']['samples']=['ATTEMPT_GUARD',1]
            save=next(k for k,n in g.items() if n['class_type']=='H3ContinuationSave')
            g[save]['inputs']['latent']=['ATTEMPT_GUARD',1]
            g['961']['inputs']['filename_prefix']='RecoveredNative_20261016/segment_01'
            g=p.prune(g,['961',save])
            if any(n['class_type'] in ('SamplerCustomAdvanced','UNETLoader','MiniMaxH3ReferenceToVideo','CLIPLoader') for n in g.values()):raise ValueError('Recovery graph unexpectedly includes generation')
            ledger=p.read_state(p.ledger_path(context));attempt=ledger['segments'][str(i)]['attempt']
            attempt.update(graph_sha256=p.graph_digest(g),recovery={'mode':'DECODE_ONLY_FROM_NATIVE','source_prompt_id':source_pid,'source_project_id':ctx['project_id'],'source_latent_sha256':sha,'frames':int(meta['frames'])})
            p.atomic_json(p.ledger_path(context),ledger)
            # Exact source timeline, copied only into the new execution; original remains intact.
            timeline=json.loads((path.parent/'long_song_timeline.json').read_text('utf-8'))
            entry=copy.deepcopy(timeline[str(i)]);entry['project_id']=context['project_id']
            p.atomic_json(p.ledger_path(context).parent/'long_song_timeline.json',{str(i):entry})
            response=await server.h3_attempt_manager.submit({'context':context,'index':i,'attempt_id':result['attempt_id'],'graph':g,'workflow':body.get('workflow'),'client_id':body.get('client_id')})
            return web.json_response({**response,'binding':context,'recovery':attempt['recovery']})
        except Exception as ex:return web.json_response({'error':str(ex)},status=409)
