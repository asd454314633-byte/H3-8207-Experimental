> R2 UPDATE: See docs/BLOCKER_RESOLUTION.md (from docs/: BLOCKER_RESOLUTION.md). Earlier blocker statements below describe the frozen baseline. Exact source/dependency/CPU-contract results have advanced; runtime E2E and publication remain HOLD.

# 8207 最终差异复核

原始分类仍为 1965 REUSE_PASS、10 DELTA_REVIEW、182 UNKNOWN_HOLD；这不是可分发计数。

| 原始文件 | 实际变化与候选处置 |
|---|---|
| H3_ChineseDirectorUI/js/chinese_director.js | 仅在 8207 激活；删去 node 991 Guide 权威同步，不能声称只是新增 UI；开关兼容性 HOLD |
| H3_NativeContinuation/core.py | 相对 8197 移除唯一临时文件、fsync 与 latent 原子替换，存储并发/崩溃语义 HOLD |
| H3_Prompt_Sidecar/native_merge_control.py | 相对 8197 删除持久恢复和提交去重；本轮补回活动组及接受 prompt 身份复查，重启/并发仍 HOLD |
| H3_Prompt_Sidecar/six_resume.py | 原版削弱回执/视频校验；本轮要求 SUCCESS 回执、prompt_id、latent 哈希及真实 SaveVideo，CPU 身份门禁测试通过，集成仍 HOLD |
| H3_Prompt_Sidecar/web/h3_six_execute.js | 从后台保留 id/提交/超时回收退回普通 Queue，默认等待达四小时；后台恢复契约 HOLD |
| H3_Prompt_Sidecar/web/h3_six_segment_director.js | 删除故事身份恢复、编辑同步和刷新状态恢复；不等同于 8197 新功能扩展 |
| h3_conditioning_prebake/cache_codec.py | 原始差异仅硬编码缓存目录；本轮替换为环境变量与相对默认目录，不冒称新缓存算法 |
| h3_conditioning_prebake/web/production.js | 删除绑定故事/提交/恢复调用，和保留后端的协议关系仍 HOLD |
| execution.py | 增加正式 PreBake 的 RAM headroom 与 TE 前释放钩子；改为固定宿主的 103 行 GPL 补丁 |
| extra_model_paths.yaml | 增加只读 Krea/Qwen 模型查询路径；原配置不分发，只交付待配置的例子 |

138 条旧公开差异 = 130 个 REUSE 文件 + 8 个 DELTA 文件。其中 91 条仅横幅/换行、1 条 JSON 序列化、31 条其它内容脱敏、15 条破坏了 Python 语法的整行脱敏。它们是旧本地发布快照对原环境的比较，不是 138 份新代码，也不是当前 GitHub 固定版本的最新差异计数。逐项的四方哈希与 diff 证据保存在私有审计区。
