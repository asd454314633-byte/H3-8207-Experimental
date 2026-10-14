Current preview checks and their limits are listed in [PREVIEW_RELEASE_NOTES](../docs/PREVIEW_RELEASE_NOTES.md). The frontend bridge now asserts that a draft edit preserves the submitted task. The following R2 results are historical, not a substitute for checking this preview.

# 离线验证（R2）

本轮结果与边界见 [BLOCKER_RESOLUTION.md](../docs/BLOCKER_RESOLUTION.md)。

- `python -B tests/test_release_guards.py`：9 项 CPU 防护测试通过。
- `python -B tests/test_prebake_runtime_contract.py --host <REBUILT_HOST>`：9 项动态 CPU 状态及真实 safetensors 测试通过，使用已具备 torch/safetensors 的 Python。
- 设置 `H3_TEST_PYTHON`、`H3_TEST_HOST` 后运行 `node --test tests/prebake_frontend_backend.test.cjs`：1 项真实前端模块到 Python 状态逻辑测试通过；DOM/队列传输使用夹具。
- `node --test custom_nodes/local_author/h3_workflow_helpers/tests/*.test.cjs`：16 项通过、0 跳过；历史 Native20 原断言使用脱敏拓扑夹具恢复。
- `python -B tests/smoke_test.py`、`python -B scripts/verify/verify_integrity.py`、`python -B scripts/sanitize/sanitize_workflows.py --selfcheck`：JSON、139 项来源清单哈希、集合和 193 份工作流静态隐私检查通过。

GPU、真实 ComfyUI 服务、浏览器 UI、Qwen 模型执行和视频端到端均未测试。其它依赖完整安装或外部 Skill 的旧测试没有被上述测试冒充全部通过。PUBLICATION_APPROVED = HOLD。
