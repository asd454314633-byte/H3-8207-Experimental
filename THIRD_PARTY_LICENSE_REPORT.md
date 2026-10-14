> R2 UPDATE: See docs/BLOCKER_RESOLUTION.md (from docs/: BLOCKER_RESOLUTION.md). Earlier blocker statements below describe the frozen baseline. Exact source/dependency/CPU-contract results have advanced; runtime E2E and publication remain HOLD.

# 最终归属与许可范围

按文件区分 ORIGINAL、MODIFIED_UPSTREAM、THIRD_PARTY 和 UNKNOWN_HOLD。同哈希仅用于复用内容核对，不是原创或许可证明。

复用固定公开 8197 基线的 MIT 声明、节点归属与已核实上游材料，不重审其相同第三方源码。1751 个“不搬运源码”的 REUSE 文件没有进入候选；77 个空归属 REUSE 中原先进入的 75 个运行/实验材料已经隔离，另外 2 个宿主示例原本未入包。

- H3 独立代码、编排、公开脚本/文档：项目作者 MIT 声明；文件来源映射保留，不把脱敏或换行改变算作新开发。
- `H3_AudioUpgrade` 包装层为基于上游的修改；`vendor/nodes.py` 是 Adudeguyman 的第三方代码，原 MIT 署名与许可文本随 `vendor/LICENSE` 保留。该逐字文件不是本项目原创。
- ComfyUI `execution.py`：GPL-3.0 宿主源码，整文件副本已排除；只交付检查哈希的 `overlays/execution-prebake.patch`，附 `overlays/LICENSE-GPL-3.0.txt` 和修改声明。环境配置模板同样不按原创宿主源码宣称 MIT。
- SDPose 和 Qwen 子图：Comfy-Org/workflow_templates 的 MIT 模板派生内容，包含本地编排和脱敏修改。上游固定版本 `cdccb2ee7a7cd0baee4630cf7186283a98ab408f`，许可全文在 `licenses/workflow_templates-MIT.txt`。没有宣称整张工作流或全部子图原创。
- MiniMax 官方提示 Skill 三份正文：复用 8197 当前归属审计确认的 LICENSE_HOLD，已经排除，改留来源指针。
- NoteShim：不以旧准备清单的 published_local_author/YES 解除 HOLD。当前公开 8197 固定版本实际登记 NOT_DISTRIBUTED，未找到足够逐文件创作/许可链，故排除。
- krea-reference 171 文件和 comfyui-krea2edit 10 文件：不分发其节点源码；仅登记来源/安装信息。7 份额外 Krea 历史模板也已隔离。

第三方依赖表保存在 `config/third_party_nodes.json`。H3-Optimizations 的 Apache-2.0 仅覆盖 native 子树，不能覆盖整个节点包；两个宿主示例是 ComfyUI GPL-3.0，旧报告中的 MIT 错误已纠正。MiniMax Combined 缺少上游身份，继续 HOLD。对运行时调用的法律衍生关系不作推定。

## 2026-10-14 Adaptive V1增量

新增adaptive_bridge.py与adaptive_v1包为本项目独立恢复/适配代码，沿用根MIT声明，标准库实现，无新增vendored第三方源码或依赖。三份宿主整合文件保留原有许可/来源；ComfyUI、模型与其他节点许可证不变。仅同步6份已验收源码，未搬运CPU隔离工具、私人样本或本机回滚脚本。
