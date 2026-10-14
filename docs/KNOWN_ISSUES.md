> R2 UPDATE: See docs/BLOCKER_RESOLUTION.md (from docs/: BLOCKER_RESOLUTION.md). Earlier blocker statements below describe the frozen baseline. Exact source/dependency/CPU-contract results have advanced; runtime E2E and publication remain HOLD.

# 公开发布门禁

PUBLICATION_APPROVED = HOLD

本地终审发现的隐私、归属、宿主交付与安装脚本问题已经修复或隔离；旧报告中的 A–G 全 PASS 结论作废。最终 Git 对象和发布压缩包以本轮私有终审记录为准。

具体未决项：

1. 两项第三方依赖缺少可重建的固定上游版本，完整依赖安装尚未通过。
2. Qwen 2.1 原宿主提交无法从记录的上游取得；当前固定 0.36.0 宿主源码导出不等于原实验运行环境。
3. 六段/PreBake 差异删除了持久恢复、提交去重和编辑同步等 8197 保护，剩余并发/重启语义与前后端集成尚无充分离线验收；不能声称与 8197 的运行行为兼容。候选中修复了缺失回执、错误 prompt 身份、latent 哈希及视频存在性检查，但未做新的 GPU 验收。

当前目录是供审查的独立实验候选，不是发布许可。只允许用户单独授权后的 GitHub 操作；本轮无 push、远端建仓或 Release。
