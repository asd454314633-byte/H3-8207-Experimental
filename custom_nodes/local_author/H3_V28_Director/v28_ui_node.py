"""H3V28DirectorConsole —— 【V28 剧情自动导演】工作流内 UI 节点（VIEW only）。

TASK_ID = H3_DIRECTOR_V28_IN_WORKFLOW_UI_REFACTOR_01

边界（不得越界）：
  - 本节点只承载 UI 与 Director API 交互（/h3_director/state|prepare|
    submitted|candidate|accept），由前端 web/h3_director_v28.js 挂 DOM Widget。
  - 不做模型推理、不做 sampler、不碰 latent、不碰 H3 forward。
  - RETURN_TYPES=()：无输出、零连线，永远不会成为任何输出节点的祖先，
    因此在 ComfyUI 执行模型下不可被执行（FUNCTION 永远不会真正跑）。
  - 提交级保险：前端 h3_workflow_ux.js 的 UI_ONLY_SELECTOR_TYPES 白名单
    会在 /prompt 序列化时摘掉「零连线的本类型节点」（与 H3ContinuationSelector
    同一机制、同一保守边界：一旦被接线绝不静默删除）。
  - 状态唯一事实源 = V28_PROJECTS + SESSION_STATE.json + 后端状态机。
    本节点不保存任何项目状态；页面刷新后由前端重新读取 /state。
"""

from __future__ import annotations


class H3V28DirectorConsole:
    """纯 UI 承载节点：导演台的画布内容器（前端 addDOMWidget 挂载点）。"""

    @classmethod
    def INPUT_TYPES(cls):
        # 刻意最小：没有任何输入控件；节点内全部 UI 由前端 DOM Widget 提供。
        return {"required": {}}

    CATEGORY = "H3_V28"
    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "view_only"
    DESCRIPTION = (
        "【V28 剧情自动导演】：工作流内的剧情导演面板。"
        "只负责 UI 与导演接口交互，不参与视频生成执行链；"
        "不要给它连线，也不需要连任何输出。"
    )

    def view_only(self, **kwargs):  # pragma: no cover - 永远不会被调度执行
        return ()
