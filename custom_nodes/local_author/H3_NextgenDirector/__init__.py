from comfy_api.latest import ComfyExtension, io
from .nodes import H3GuideTimeline

WEB_DIRECTORY = "./js"

class H3NextgenDirectorExtension(ComfyExtension):
    async def get_node_list(self):
        return [H3GuideTimeline]

async def comfy_entrypoint():
    return H3NextgenDirectorExtension()

__all__ = ["WEB_DIRECTORY"]