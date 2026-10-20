"""Read-only identity of this process; no target redirect and no model allocation."""
import os
import sys
import hashlib
from pathlib import Path
from aiohttp import web
from server import PromptServer
import folder_paths

_root=Path(__file__).resolve().parents[1]
_loaded_hashes={str(p.relative_to(_root)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (_root/'h3_partial_diffusion_evict/__init__.py',_root/'H3_V28_Director/v28_paths.py') if p.is_file()}

async def identity(request):
    return web.json_response({'id':os.environ.get('H3_INSTANCE_ID'),
        'generation':os.environ.get('H3_INSTANCE_GENERATION'),'pid':os.getpid(),
        'source':os.getcwd(),'argv':sys.argv,'startup_source_hashes':_loaded_hashes,'output':folder_paths.get_output_directory(),
        'input':folder_paths.get_input_directory(),'user':folder_paths.get_user_directory()})

if not getattr(PromptServer.instance,'h3_instance_identity_registered',False):
    @web.middleware
    async def target_identity_guard(request,handler):
        target=request.headers.get('X-H3-Instance')
        generation=request.headers.get('X-H3-Generation')
        if (target is not None or generation is not None) and (
                target!=os.environ.get('H3_INSTANCE_ID') or
                generation!=os.environ.get('H3_INSTANCE_GENERATION')):
            return web.json_response({'error':'INSTANCE_TARGET_MISMATCH'},status=409)
        return await handler(request)
    PromptServer.instance.app.middlewares.append(target_identity_guard)
    PromptServer.instance.routes.get('/h3/instance')(identity)
    PromptServer.instance.h3_instance_identity_registered=True

NODE_CLASS_MAPPINGS={}
