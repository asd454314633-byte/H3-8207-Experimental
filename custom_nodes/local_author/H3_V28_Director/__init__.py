"""H3 全中文导演台 V28.2 —— Gemma4 文本剧情导演。

一句话：用户给「总剧情构想 + 中性参考槽映射 + 用途说明」，Gemma4 不看图，拆成
SEG1..N，每段编成一条合规的 H3 Ref2VA 提示词，然后交给 V27 原图连续生成。
用户只做三件事：生成 / 重生成 / 接受并下一步。

本包只注册一个零输出、零执行连线的纯 UI 节点 `H3V28DirectorConsole`。
提交时共享 helper 会把它从 prompt 中摘除；导演逻辑仍只通过本机 HTTP 接口驱动
V27 已有节点。关掉面板时 V27 生成行为不变（§36 DIRECTOR_OFF_BEHAVIOR_CHANGE = NO）。

分层与不变量：
  L0 `v28_paths`         唯一路径与常量；原子写；禁止端口清单。
  L0 `v28_schemas`       三套 JSON schema + 严格白名单校验；shot 数 == segment 数。
  L1 `v28_provider`      DirectorProvider 抽象；JSON-only + 最多 2 次 repair + 预算。
  L1 `v28_bonsai_*`      唯一允许懂 llama.cpp 方言的模块；PHASE A 生命周期与释放确认。
  L1 `v28_mock_provider` 离线替身，用于不占显存地验证 L2/L3。
  L1 `v28_prompt_compiler` 确定性六段 H3 编译与结构闸门（airlock 在这里，不在 LLM 里）。
  L2 `v28_state_machine`  显式状态枚举；接受是原子的且绝不 queue。
  L3 `v28_orchestrator`   PHASE A 一次性规划后卸载；PHASE B 无 LLM。
  L3 `v28_routes`         仅 127.0.0.1 的同源接口。

零第三方依赖：只用标准库（唯一可选依赖 psutil 有 fallback）。不新建 ComfyUI
环境、不新建 venv、不使用除 8197 之外的 H3 实例端口。
"""
from __future__ import annotations

import logging

__version__ = "0.28.2-gate6b"

# --- L0/L1/L2/L3: importing the package is the whole "installation" ---------
from . import v28_paths as _paths          # noqa: E402  (must be first: constants)
from . import v28_schemas as _schemas      # noqa: E402
from . import v28_prompt_compiler as _pc   # noqa: E402
from . import v28_director_core as _core   # noqa: E402
from . import v28_provider as _provider    # noqa: E402
from . import v28_runtime_contract as _runtime_contract  # noqa: E402
from . import v28_bonsai_runtime as _rt    # noqa: E402
from . import v28_bonsai_provider as _bp   # noqa: E402
from . import v28_gemma_provider as _gp    # noqa: E402
from . import v28_mock_provider as _mp     # noqa: E402
from . import v28_project as _pj           # noqa: E402
from . import v28_state_machine as _sm     # noqa: E402
from . import v28_orchestrator as _or      # noqa: E402
from . import v28_ui_node as _ui           # noqa: E402  (UI_REFACTOR_01)

# UI_REFACTOR_01 (H3_DIRECTOR_V28_IN_WORKFLOW_UI_REFACTOR_01)：V28 现在注册
# 唯一一个「纯 UI 工作流节点」H3V28DirectorConsole（【V28 剧情自动导演】）。
# 它只是 Director API 的 VIEW：RETURN_TYPES=()、零连线、不喂任何执行输入，
# 不会出现在任何执行路径上；提交级由前端 h3_workflow_ux.js 的
# stripUiOnlyNodes() 白名单摘除（与 H3ContinuationSelector 同一机制）。
# 真实导演逻辑仍全部在 /h3_director/* + Gemma4/状态机，本节点不做推理。
NODE_CLASS_MAPPINGS: dict = {"H3V28DirectorConsole": _ui.H3V28DirectorConsole}
NODE_DISPLAY_NAME_MAPPINGS: dict = {"H3V28DirectorConsole": "【V28 剧情自动导演】"}

WEB_DIRECTORY = "./web"


def _attach_routes() -> bool:
    try:
        from . import v28_routes
        v28_routes.register_director_routes()
        return v28_routes._registered
    except Exception as exc:                                  # noqa: BLE001
        logging.getLogger("h3_v28_director").warning(
            "导演接口挂载失败（%s: %s）；V27 本身不受影响。", type(exc).__name__, exc)
        return False


def _defer_attach() -> None:
    """If PromptServer is not up yet, attach on the next event-loop iteration
    instead of silently losing the endpoints."""
    import asyncio

    async def waiter():
        for _ in range(240):
            if _attach_routes():
                return
            await asyncio.sleep(0.5)
        logging.getLogger("h3_v28_director").error("导演接口始终未能挂载，请重启 ComfyUI")

    try:
        asyncio.get_running_loop().create_task(waiter())
    except RuntimeError:
        _attach_routes()


if not _attach_routes():
    _defer_attach()

try:
    _paths.ensure_dirs()
except OSError as exc:                                        # pragma: no cover
    logging.getLogger("h3_v28_director").warning("运行目录创建失败: %s", exc)

logging.getLogger("h3_v28_director").info(
    "H3_V28_Director %s：导演台以纯 UI 节点 + 本机接口挂载；"
    "提供方=%s；默认=%s",
    __version__, _provider.available_providers(),
    _paths.os.environ.get("H3_V28_DIRECTOR", "gemma4"))

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY",
           "__version__"]
