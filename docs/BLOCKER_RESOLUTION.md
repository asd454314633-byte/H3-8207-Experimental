# 四类阻断项修复进度（R2）

EXPERIMENTAL_PUBLICATION_READY = PASS
PUBLICATION_APPROVED = PASS (EXPERIMENTAL SOURCE SCOPE ONLY)
PRODUCTION_PROMOTION = HOLD
CURRENT_CANDIDATE_GPU_E2E = NOT_TESTED

本副本从冻结的 370 文件候选派生；冻结目录、单次干净提交和原压缩包保持不变。此前报告是冻结基线的历史结论；本文件更新其四类阻断项状态，不扩大其它审计范围。

| 阻断项 | 本轮实证结果 | 仍然保留的限制 |
|---|---|---|
| 两项依赖 | Krea2Edit bdfa8b267fdb13730868d435b277dcfe696ec083：本机清单 10/10 文件一致；Combined 40c74969fd805174bf3e1aed1f83f66ef7de6838：两个源码文件一致，使用固定上游 GPL-3.0 文本。两项实际获取和重复安装均成功 | 只安装源码，未安装模型、运行 pip 或验证模型节点推理；其余已锁定依赖不重复安装 |
| Qwen 精确源码重建 | 固定 0.36.0 基础提交 + overlays/qwen21-backport.patch；应用前/后逐文件 SHA256 检查，11/11 目标源码与原实验一致 | 模型执行端到端未测；源码重建通过不能解除 Qwen 运行 HOLD |
| 六段 / PreBake | 定点补回绑定、编辑同步、后台提交/恢复/去重和共享锁；9 项动态 CPU 状态/真实 safetensors 测试、1 项实际前端模块至 Python 状态逻辑测试通过 | DOM 与队列传输是夹具，没有启动真实 ComfyUI 或进行视频生成；不能声明视频端到端通过 |
| 历史 fixture | 找回合法归档，自其中提取不含控件、提示词或素材名的 184 节点 / 228 连线拓扑；与 Native20 原有连线前缀精确相同；原断言恢复，不再跳过 | 归档原验收状态仍是 HOLD；结构夹具通过不把该历史工作流升级为运行 PASS |

## 可重复验证

```sh
python scripts/setup/install_deps.py --comfyui-root <ISOLATED_ROOT> --node comfyui-krea2edit --node MiniMax-H3-Combined-Image-And-Reference-to-Video
python scripts/rebuild/rebuild_from_8197.py --baseline <PINNED_PUBLIC_BASELINE> --host <PINNED_COMFYUI> --out <EMPTY_OUTPUT>
python tests/test_prebake_runtime_contract.py --host <REBUILT_COMFYUI_SOURCE>
# Use an existing CPU-capable ComfyUI Python with torch/safetensors; no model installation needed.
# Set H3_TEST_PYTHON and H3_TEST_HOST before running this integration test:
node --test tests/prebake_frontend_backend.test.cjs
node --test custom_nodes/local_author/h3_workflow_helpers/tests/*.test.cjs
python -B tests/test_release_guards.py
```

运行原目录、GPU 测试、真实视频生成、远端发布都没有执行。实验版源代码发布门禁见 [PUBLIC_RELEASE_GATE.md](../PUBLIC_RELEASE_GATE.md)：MANUAL_ACCEPTANCE=USER_CONFIRMED；自动GPU端到端仍为 NOT_TESTED，不得将其记为 PASS。生产晋升继续 HOLD。
