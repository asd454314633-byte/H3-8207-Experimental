# Current release-scope correction (2026-10-13)

For the current scoped decision, see [PUBLIC_RELEASE_GATE.md](PUBLIC_RELEASE_GATE.md) and [Feature and Evidence Matrix](docs/FEATURE_MATRIX.md). This report preserves the earlier reconstruction record; any older blocker statement below is historical and is superseded by the dated R2 evidence in [BLOCKER_RESOLUTION.md](docs/BLOCKER_RESOLUTION.md) and the current experimental release gate. The current-candidate automated GPU E2E status remains `NOT_TESTED`; this does not invalidate the owner's separate `MANUAL_ACCEPTANCE = USER_CONFIRMED` or the historical Qwen Image GPU results.

# 从固定公开基线重建

固定源码导出与宿主补丁重建已在独立空目录通过（11/11 宿主目标哈希匹配）；两个此前缺少可信锁定的可选依赖已固定来源并完成源码获取/重复安装核验。完整运行时部署、模型加载、ComfyUI 动态等价运行及 GPU 渲染仍为 HOLD / NOT_TESTED。

固定 H3 公开基线：`88ccf86f2ed2a638451c864b4358a6ef7adc965d`。
固定 ComfyUI：`ee71d5c4993f29086b27fde1629a945ae48425bf`（0.36.0）。以公开基础提交加独立 GPL-3.0 宿主补丁重建后，11/11 目标源码哈希与实验目标一致；这证明源码重建，不证明 Qwen 模型加载或运行。

```sh
python scripts/rebuild/rebuild_from_8197.py --baseline <EMPTY_PUBLIC_BASELINE_DIR> --host <EMPTY_COMFYUI_DIR> --out <EMPTY_REBUILT_DIR> --fetch-sources
python scripts/setup/install_deps.py --comfyui-root <REBUILT_DIR> --dry-run
python scripts/verify/verify_integrity.py
python scripts/sanitize/sanitize_workflows.py --selfcheck
python -B tests/test_release_guards.py
python tests/smoke_test.py
```

重建脚本只导出固定版本的源码，先取 8197 的 `8197_production_line`，再逐节点叠加公开 8207 副本到 `custom_nodes/<node>`，检查宿主文件哈希后应用 GPL 补丁。不会复制私人模型、输入、输出、缓存、旧 Git 历史，也不会启动服务或执行 pip。输出目录须为空且与源目录互不包含。

第三方依赖锁定情况：11 个完整 Git commit、2 个宿主内置示例；此前缺少锁定的 `comfyui-krea2edit` 与 `MiniMax-H3-Combined-Image-And-Reference-to-Video` 已按 R2 记录固定准确来源/提交并完成源码获取与重复安装核验。安装器支持 `--node <name>` 检查或获取明确的一项。源码获取不等于 Python 运行依赖安装、GPU、节点注册或工作流运行验收。

`extra_model_paths.example.yaml` 和 `model_registry.json` 是待配置的模板。模型注册表中的哈希/大小/时间字段已清空；须为自己的模型生成真实指纹。PreBake 缓存可用 `H3_CONDITIONING_CACHE` 配置，默认 `output/h3_conditioning_cache`。本地 Director 模型后端与官方提示指南须另行配置；原始回复、模型运行时与私人实验结果不分发。

`.disabled` 目录保持禁用，重建器不启用它们。NoteShim 与无再分发许可的官方 Skill 正文已排除。缺少相应外部条件的功能保持 HOLD。不要对正式生产目录执行重建或依赖安装。
