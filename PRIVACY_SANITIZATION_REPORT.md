## v0.1.0-preview scope

Only audited source, sanitized workflows/configuration, synthetic tests and four exact hash-whitelisted historical showcase assets are included. No private runtime state, incident snapshots, absolute workstation paths or raw model replies are exported. The showcase has redacted prompts and is explicitly separate from current-build acceptance.

# 最终隐私脱敏说明

本轮以初始 455 个实际 Git 跟踪文件和全部旧候选 Git 对象为范围，发现并修复了旧报告未覆盖的原始模型回复、剧情存档、运行日志、参考素材名、嵌套短提示词及公开清单中的个人路径。旧历史已保存在私有审计区，不能用旧版 PASS 作为最终门禁。

12 份当前工作流和 181 份保留历史工作流经过递归 JSON、JSON 字符串、文本控件、素材字段和运行状态检查。主图和子图的节点 id/type/mode、输入输出接口与完整连线契约在脱敏前后相等；私人故事、台词、预览和运行状态被中性化。历史名称换成不包含个人剧情的编号，原名映射只留私有审计区。

191 份原历史文件中，7 份未单独核实许可的 Krea 示例和 3 份废版已隔离。429 条 H3 历史记录对应 181 份公开历史、242 条原 HOLD 和 6 条指向不存在旧 current 名称的记录；后 6 条保留 HOLD，不伪造与另一工作流的等价关系。历史验收标签保持原记录（多数 UNKNOWN）；文件名中的 PASS 不升级为运行验收。

生成的时间线 JavaScript 按 JSON literal 解析后清理素材，合并 API 模板只更换素材值，模型注册表示例清空私人运行指纹。扫描工具中的检测词与普通技术文句分别判读；没有通过整目录排除扫描来掩盖命中。

静态脱敏和结构保真不证明模型效果、视频质量、实际 UI 加载或 GPU 运行成功。最终对象扫描和压缩包核验结果见私有终审报告。
