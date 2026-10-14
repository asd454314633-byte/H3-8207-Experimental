> R2 UPDATE: See docs/BLOCKER_RESOLUTION.md (from docs/: BLOCKER_RESOLUTION.md). Earlier blocker statements below describe the frozen baseline. Exact source/dependency/CPU-contract results have advanced; runtime E2E and publication remain HOLD.

# 公开发布门禁

PUBLICATION_APPROVED = HOLD

本地终审发现的隐私、归属、宿主交付与安装脚本问题已经修复或隔离；旧报告中的 A–G 全 PASS 结论作废。最终 Git 对象和发布压缩包以本轮私有终审记录为准。

具体未决项：

1. 两项第三方依赖缺少可重建的固定上游版本，完整依赖安装尚未通过。
2. Qwen 2.1 原宿主提交无法从记录的上游取得；当前固定 0.36.0 宿主源码导出不等于原实验运行环境。
3. 六段/PreBake 差异删除了持久恢复、提交去重和编辑同步等 8197 保护，剩余并发/重启语义与前后端集成尚无充分离线验收；不能声称与 8197 的运行行为兼容。候选中修复了缺失回执、错误 prompt 身份、latent 哈希及视频存在性检查，但未做新的 GPU 验收。

当前目录是供审查的独立实验候选，不是发布许可。只允许用户单独授权后的 GitHub 操作；本轮无 push、远端建仓或 Release。

# 最终隐私脱敏说明

本轮以初始 455 个实际 Git 跟踪文件和全部旧候选 Git 对象为范围，发现并修复了旧报告未覆盖的原始模型回复、剧情存档、运行日志、参考素材名、嵌套短提示词及公开清单中的个人路径。旧历史已保存在私有审计区，不能用旧版 PASS 作为最终门禁。

12 份当前工作流和 181 份保留历史工作流经过递归 JSON、JSON 字符串、文本控件、素材字段和运行状态检查。主图和子图的节点 id/type/mode、输入输出接口与完整连线契约在脱敏前后相等；私人故事、台词、预览和运行状态被中性化。历史名称换成不包含个人剧情的编号，原名映射只留私有审计区。

191 份原历史文件中，7 份未单独核实许可的 Krea 示例和 3 份废版已隔离。429 条 H3 历史记录对应 181 份公开历史、242 条原 HOLD 和 6 条指向不存在旧 current 名称的记录；后 6 条保留 HOLD，不伪造与另一工作流的等价关系。历史验收标签保持原记录（多数 UNKNOWN）；文件名中的 PASS 不升级为运行验收。

生成的时间线 JavaScript 按 JSON literal 解析后清理素材，合并 API 模板只更换素材值，模型注册表示例清空私人运行指纹。扫描工具中的检测词与普通技术文句分别判读；没有通过整目录排除扫描来掩盖命中。

静态脱敏和结构保真不证明模型效果、视频质量、实际 UI 加载或 GPU 运行成功。最终对象扫描和压缩包核验结果见私有终审报告。
