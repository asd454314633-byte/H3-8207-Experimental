# H3 六段独立编译器桥（8207侧最小适配，2026-10-19）
#
# 目的：8210 冻结编译器（H3_中文提示词编译器，127.0.0.1:8210）不支持跨域，
# 浏览器页面（同源 127.0.0.1:8207）无法直接调用其公开 HTTP API。
# 本扩展只做一件事：把同源 /h3/compiler/* 请求**原样转发**到 127.0.0.1:8210/*。
#
# 硬边界：
#   * 只转发，不改写请求与响应、不缓存、不重试、不做任何编译逻辑；
#   * 8210 不可达时如实返回 502，由前端按任务要求阻断提交，不回退原稿；
#   * 不触碰 8197；不新增节点；不改变队列行为；
#   * 8210 冻结源码零改动（仅使用其既有 /api/* 接口）。
from aiohttp import ClientSession, ClientTimeout, web
from server import PromptServer

UPSTREAM = "http://127.0.0.1:8210"
_session = None


async def _proxy(request):
    global _session
    origin = request.headers.get("Origin")
    if origin and origin != f"{request.scheme}://{request.host}":
        return web.json_response({"error": "Origin rejected"}, status=403)
    tail = request.match_info["tail"]
    body = await request.read()
    if _session is None:
        _session = ClientSession(timeout=ClientTimeout(total=300))
    try:
        async with _session.request(
            request.method,
            f"{UPSTREAM}/{tail}",
            data=body,
            headers={"Content-Type": request.headers.get("Content-Type", "application/json")},
        ) as upstream:
            payload = await upstream.read()
            return web.Response(
                status=upstream.status,
                body=payload,
                content_type=upstream.headers.get("Content-Type", "application/json").split(";")[0],
            )
    except Exception as ex:  # 8210 不可达：如实上报，绝不回退
        return web.json_response({"error": f"8210 unreachable: {ex}"}, status=502)


def register():
    server = PromptServer.instance
    if getattr(server, "h3_compiler_bridge_installed", False):
        return
    server.h3_compiler_bridge_installed = True
    server.routes.route("*", "/h3/compiler/{tail:.*}")(_proxy)


register()
