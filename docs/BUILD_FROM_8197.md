> R2 UPDATE: See docs/BLOCKER_RESOLUTION.md (from docs/: BLOCKER_RESOLUTION.md). Earlier blocker statements below describe the frozen baseline. Exact source/dependency/CPU-contract results have advanced; runtime E2E and publication remain HOLD.

# 从固定公开基线重建

SOURCE_EXPORT 与 HOST_PATCH 已在独立空目录验证；等价运行、完整依赖安装和 GPU 渲染仍为 HOLD / NOT_TESTED。

固定 H3 公开基线：`88ccf86f2ed2a638451c864b4358a6ef7adc965d`。
固定 ComfyUI：`ee71d5c4993f29086b27fde1629a945ae48425bf`（0.36.0）。机器上的 Qwen 2.1 宿主提交无法从该上游获取，不能声称 Qwen 运行已重建。

```sh
python scripts/rebuild/rebuild_from_8197.py --baseline <EMPTY_PUBLIC_BASELINE_DIR> --host <EMPTY_COMFYUI_DIR> --out <EMPTY_REBUILT_DIR> --fetch-sources
python scripts/setup/install_deps.py --comfyui-root <REBUILT_DIR> --dry-run
python scripts/verify/verify_integrity.py
python scripts/sanitize/sanitize_workflows.py --selfcheck
python -B tests/test_release_guards.py
python tests/smoke_test.py
```

重建脚本只导出固定版本的源码，先取 8197 的 `8197_production_line`，再逐节点叠加公开 8207 副本到 `custom_nodes/<node>`，检查宿主文件哈希后应用 GPL 补丁。不会复制私人模型、输入、输出、缓存、旧 Git 历史，也不会启动服务或执行 pip。输出目录须为空且与源目录互不包含。

第三方依赖锁定情况：11 个完整 Git commit、2 个宿主内置示例；`comfyui-krea2edit` 只有版本声明，`MiniMax-H3-Combined-Image-And-Reference-to-Video` 缺少可信来源。安装器对这两项返回 HOLD（退出码 2），对克隆/版本错误返回失败。支持 `--node <name>` 检查或安装明确的一项。没有把自动克隆等同于 Python 依赖、GPU、节点注册或工作流运行验收。

`extra_model_paths.example.yaml` 和 `model_registry.json` 是待配置的模板。模型注册表中的哈希/大小/时间字段已清空；须为自己的模型生成真实指纹。PreBake 缓存可用 `H3_CONDITIONING_CACHE` 配置，默认 `output/h3_conditioning_cache`。本地 Director 模型后端与官方提示指南须另行配置；原始回复、模型运行时与私人实验结果不分发。

`.disabled` 目录保持禁用，重建器不启用它们。NoteShim 与无再分发许可的官方 Skill 正文已排除。缺少相应外部条件的功能保持 HOLD。不要对正式生产目录执行重建或依赖安装。
