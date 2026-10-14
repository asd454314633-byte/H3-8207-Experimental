"""H3 Sidecar adapter: current workflow context is authoritative."""
import hashlib,json
from pathlib import Path
from .scene_inputs import build_context as _context

WEB_DIRECTORY="./web"
def _sha(text):return hashlib.sha256((text or "").encode()).hexdigest()
def _scene_id(context):
    return _sha(json.dumps(context,ensure_ascii=False,sort_keys=True,separators=(',',':')))

class H3PromptSidecar:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{
            "use_ai_director":("BOOLEAN",{"default":False,"label_on":"使用AI导演","label_off":"手工模式"}),
            "delta":("STRING",{"multiline":True,"default":"","label":"本段剧情"}),
            "prompt_zh":("STRING",{"multiline":True,"default":"","label":"中文提示词"}),
            "prompt_en":("STRING",{"multiline":True,"default":"","label":"English Prompt"}),
            "delta_sha256":("STRING",{"default":"","label":"本段剧情指纹（自动记录）"}),
            "manual_prompt":("STRING",{"multiline":True,"forceInput":True,"label":"手工提示词"})},
            "optional":{
                "reference_roles":("STRING",{"multiline":True,"default":"","label":"当前参考职责（权威输入）"}),
                "scene_settings":("STRING",{"multiline":True,"default":"","label":"当前场景设定"}),
                "scene_context_sha256":("STRING",{"default":"","label":"当前故事指纹（自动记录）"})},
            "hidden":{"prompt":"PROMPT","extra_pnginfo":"EXTRA_PNGINFO","unique_id":"UNIQUE_ID"}}
    CATEGORY="H3"
    RETURN_TYPES=("STRING",)
    RETURN_NAMES=("最终Prompt",)
    FUNCTION="compile"
    OUTPUT_NODE=True  # standalone compile preview: no H3/video nodes are required
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float("nan") if kwargs.get("use_ai_director") else kwargs.get("manual_prompt")

    def compile(self,use_ai_director,delta,prompt_zh,prompt_en,delta_sha256,manual_prompt,
                reference_roles="",scene_settings="",scene_context_sha256="",prompt=None,extra_pnginfo=None,unique_id=None):
        if not use_ai_director:return (manual_prompt,)
        context=_context(prompt,extra_pnginfo,reference_roles,scene_settings,delta)
        scene_id=_scene_id(context)
        current_sha=_sha(delta)
        if (prompt_en or "").strip():
            if scene_context_sha256 != scene_id:
                raise RuntimeError("SCENE_CONTEXT_STALE: 素材/职责/场景已变化或旧稿未绑定故事；清空English Prompt后编译当前故事")
            if delta_sha256 and delta_sha256!=current_sha:
                raise RuntimeError("DELTA_CHANGED_PROMPT_STALE: 本段剧情已修改；清空English Prompt后重新编译")
            # Validate against the active Director rules; confirmation remains explicit.
            from director_engine import validate
            import director_rules
            validate(prompt_en,prompt_zh,director_rules._declared_resources(context['reference_roles'],context['scene_settings']),generated=False)
            return {"ui":{"prompt_zh":[prompt_zh],"prompt_en":[prompt_en],"delta_sha256":[current_sha],
                "scene_context_sha256":[scene_id],"reference_roles":[context["reference_roles"]],"state_commit":["NO_AUTO_CONFIRM"]},"result":(prompt_en,)}
        # Reuse the single active core; never load the retired compiler or archive.
        settings='\n'.join([context['scene_settings'],context['reference_roles'],
                            'Verified workflow assets: '+json.dumps(context['assets'],ensure_ascii=False)])
        result=H3_DIRECTOR_CORE.dispatch('POST','/api/h3-director/generate',{'global_settings':settings,'delta':delta})
        return {"ui":{"prompt_zh":[result["chinese_prompt"]],"prompt_en":[result["english_prompt"]],
            "delta_sha256":[current_sha],"scene_context_sha256":[scene_id],
            "reference_roles":[context["reference_roles"]],"run_id":[result["id"]],
            "latency_ms":[result["latency_ms"]],"auto_continue":["YES" if result["auto_continue"] else "NO"],
            "state_commit":["DRAFT_NOT_CONFIRMED"]},"result":(result["english_prompt"],)}

NODE_CLASS_MAPPINGS={"H3PromptSidecar":H3PromptSidecar}
NODE_DISPLAY_NAME_MAPPINGS={"H3PromptSidecar":"H3 提示词导演"}


class H3SixDirectorState:
    """Workflow UI state only; no model or continuation operation."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}
    CATEGORY = "H3"
    RETURN_TYPES = ()
    FUNCTION = "state_only"
    OUTPUT_NODE = False
    DESCRIPTION = "六段导演台的独立状态宿主；状态保存在工作流properties，不参与生成。"
    def state_only(self):
        return ()

NODE_CLASS_MAPPINGS["H3SixDirectorState"] = H3SixDirectorState
NODE_DISPLAY_NAME_MAPPINGS["H3SixDirectorState"] = "六段提示词导演台（独立状态）"

from .six_resume import register_routes
register_routes()

# Sole Director Core on the Comfy PromptServer; no model startup on import.
import sys as _director_sys
_director_root = str(Path(__file__).resolve().parent)
if _director_root not in _director_sys.path: _director_sys.path.insert(0, _director_root)
from server import PromptServer as _DirectorPromptServer
from comfy_director_routes import register_routes as _register_director_routes
H3_DIRECTOR_CORE = _register_director_routes(_DirectorPromptServer.instance.routes)
