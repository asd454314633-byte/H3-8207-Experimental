"""ComfyUI transport only. Thread executor keeps sampling/event loop responsive."""
import asyncio
from aiohttp import web
from director_http_core import DirectorCore, PREFIX

def register_routes(routes):
    core = DirectorCore()
    async def handle(request):
        try:
            if request.method == 'POST':
                origin=request.headers.get('Origin')
                if origin and origin != f'{request.scheme}://{request.host}':
                    return web.json_response({'error':'ORIGIN_REJECTED'},status=403)
                if request.content_length is None or not 0 < request.content_length <= 262144:
                    return web.json_response({'error':'INVALID_BODY_SIZE'},status=413)
                payload=await request.json()
            else:payload=None
            result=await asyncio.to_thread(core.dispatch,request.method,request.path,payload)
            return web.json_response(result,headers={'Cache-Control':'no-store'})
        except (ValueError,RuntimeError) as exc:
            return web.json_response({'error':str(exc)},status=404 if str(exc)=='NOT_FOUND' else 422)
        except Exception as exc:
            print(f'[h3-director] {exc}',flush=True)
            return web.json_response({'error':'DIRECTOR_INTERNAL_ERROR'},status=500)
    async def asset(request):
        data,kind=core.asset(request.path.removeprefix('/h3-director'))
        return web.Response(body=data,content_type=kind,headers={'Cache-Control':'no-store'})
    for path in ('status','models','preferences','activity','state','groups/latest'):
        routes.get(PREFIX+'/'+path)(handle)
    for path in ('preferences','model/warm','planner/generate','generate','continue','refine','confirm','new-story','groups/save','groups/confirm'):
        routes.post(PREFIX+'/'+path)(handle)
    for path in ('director','six','six_ui.js'):
        routes.get('/h3-director/'+path)(asset)
    return core
