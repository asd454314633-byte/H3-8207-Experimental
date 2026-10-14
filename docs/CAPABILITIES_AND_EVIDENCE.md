# H3 8207 实验导演台｜功能、模式、证据与 48 项测试（v0.1.0-preview）

> **独立实验源码预览，不是 8197 生产版升级。** 本页按 GitHub `main` 的公开文件、`v0.1.0-preview` 发布记录、[发布门禁](../PUBLIC_RELEASE_GATE.md)、[预览校验清单](../manifests/preview_validation.json)整理。2026-10-14 的这个说明更新**未进行任何 GPU 采样、真实 ComfyUI 浏览器 E2E 或生产晋升**。
>
> `EXPERIMENTAL_PUBLICATION_READY=PASS` 只表示公开源码审查与指定离线测试通过；`CURRENT_BUILD_GPU_E2E=NOT_TESTED`、`PRODUCTION_PROMOTION=HOLD`。

## 一、仓库里到底有什么

| 项目 | 核实数量 / 用法 | 不要误读 |
|---|---|---|
| 当前工作流 | **12 份 JSON**，位于 `workflows/current/` | 文件编号不是执行顺序；**只有 wf_05 是六段 H3 视频导演台主图** |
| 脱敏历史工作流 | **181 份 JSON**，位于 `workflows/history/` | 静态留档，不是 181 次 GPU 成功 |
| 全部工作流 | **193 份 JSON** | 193 是隐私扫描与文件数量，不是 GPU 测试次数 |
| 核心六段工作流 | [h3_8207_wf_05.json](../workflows/current/h3_8207_wf_05.json)，**181 个顶层节点** | 受保护/实验节点及默认关闭分支需按实际路由辨别 |
| 其他当前图像实验 | Lustify / Krea2 图像生成、Identity Edit、风格参考，以及小型图像与对比图 | 不是 H3 六段视频链的必装前置 |
| AI Director | 可选剧情文本生成、不同本地语言模型 Provider 接口 | **手动写六段提示词无需 AI Director**，不宣称所有提供者在线推理验收 |

[12 份 JSON 逐项识别索引](../workflows/current/README.md)包含文件用途和静态节点证据。

## 二、六段导演台实际功能

| 子系统 | 已有源码/合同描述 | 公开候选验证边界 |
|---|---|---|
| 全中文控制与六段编辑 | 六段提示词面板；每段独立草稿、提交与结果管理 | 源码与脱敏工作流存在；当前版浏览器端到端 **NOT_TESTED** |
| Story / Execution 分离 | 故事身份与不可变提交快照独立；后续草稿编辑不能污染已提交任务 | 指定 CPU/前后端测试覆盖合同，不代表浏览器并发生产验收 |
| 单段提交与排队 | 只对所选段落排队；各次执行有独立 attempt/提交身份；队列等待与执行计时分开 | JS/CPU 层回归；真实 ComfyUI 队列/网络传输未验 |
| 自动续接与有效前序 | 检查合法前序 SUCCESS、prompt 身份、latent SHA，旧回执不允许冒用 | CPU 回执/缓存资格验证；未完成本公开候选完整六段 GPU E2E |
| Native masked continuation | 从实际前段音视频潜空间续接；同分辨率保持原对应数据，跨分辨率时**重采样视频 latent 前缀**并在计划中记录变换；音频前缀保持原样 | 11 项 synthetic spatial 真实准备代码 CPU 测试；**不宣称跨分辨率输出画质等价或 latent 原始字节相等** |
| Conditioning PreBake | 只对实际提交的段落按依赖补建或重用缓存；接受数据的身份/完整性校验 | 11 项 CPU 状态及 safetensors 测试；没有当前候选 GPU 缓存命中率 |
| 安全恢复与失效 | 重做上游段只使**实际依赖它**的后继失效；保留合法历史 SUCCESS 版本；尝试身份避免重复派发 | 已记录源代码与离线合同；重启与真实 UI 全链仍待 GPU/浏览器验收 |
| 自动六段合并 | 合并合法、选定故事身份和视频结果 | **混分辨率自动合并 HOLD**；当前公开版完整合并 E2E 不得借用 8197 历史 PASS |

### 视频和图像路线：不要混成一项功能

- `wf_05` 含 MiniMax-H3 的多参考 Ref2VA、FL2VA 首帧/首尾帧、图片/音频/视频参考路由、不同模型/采样/注意力的节点或分支。**节点/开关存在不代表所有组合已在这个发布版本真实运行通过**。
- 一采默认 / 画质优先 / 高速平衡；PDD 多参考 8 步、FastH3 VSA 4 步以及独立的 FastH3 V2 8 步，按所选路线与启用状态区分。**FL2VA 4 步不是 Ref2VA 四图证据**。
- 关键帧/Guide 时间线、Pose/Depth Fun ControlNet、V2V/RV2V、二采窗口修复等在实验画布和/或候选功能矩阵中有结构与节点记录，其中部分默认关闭或 `PARTIAL`。未单独确认的分支**不宣传为正式可用**。
- `wf_01`～`wf_04`、`wf_06`～`wf_12` 为独立图像实验或小型辅助模板；其中历史 Qwen Image 2.1 四项 GPU `PASS` 是**原历史环境**的 4/4，不是当前脱敏 JSON 的 4/4 重新验收。

## 三、补充：长期使用的音色参考、音频专项与真实人物控制

**音色克隆参考不是仅停留在功能设想。** 2026-10-14，项目所有者已明确确认 H3 导演台的音色克隆/音色参考能力经过真实测试，并持续稳定使用：记录为 `OWNER_CONFIRMED_LONG_TERM_USE`。当前本 GitHub 仓库提供可复核的源码接口，但 **8207 当前脱敏 `v0.1.0-preview` 没有与这项长期生产使用逐一绑定的新版公开 GPU 回执**；应分开陈述，不可把长期成功错写成“从未测试”，也不可把历史使用等同于 8207 完整 E2E 通过。

| 核心能力 | 公开节点/前端 | 状态与补充说明 |
|---|---|---|
| **三路独立人声音色参考** | `H3Audio8ReferencePreflight`、`H3_AudioUpgrade/H3AudioReferencePack`、`ref_audios` | 用户确认该音色参考功能长期实际可用；新增来源与音色组合需按当前后端检验 |
| **视频本身的音轨参考** | `ref_video_audios`、`<VideoSoundtrack>` | 与三条独立人声来源不同，编号自动映射 |
| **角色/声音绑定** | `<Audio 1/2/3>` 与可选第三角色说明 `role3` | 避免多角色声音对应关系混乱 |
| **参考音频的严谨输入检查** | 单条独立音色参考 2–15 秒、启用参考音频合计 ≤15 秒、拒绝未上传和无效 PCM | 预检验证的是合法输入，不会自动裁切/重采样原始 PCM |
| **高级音频专项** | Stock20（音色优先）、8 步 Audio 模式、指定音轨、读取一采缓存精修 | 与“参考音色克隆”不同；精修和 Stock20 等部分支路不得冒称本次实验版全面通过 |
| **人物身份/素材控制** | Ref2VA 图片/视频/音频的真实连接与提示词角色标号 | 公开 JSON 含 9 个图片输入接口，但每条 4步/VSA 分支真实启用数应单独核对，不能由槽位数量断言多图实测通过 |
| **连续性的两种手段** | Native 视频/音频 latent 续接；Clean Rebase + 官方单帧 Guide（原8197验证） | 后者的 **2026-10-09 GPU PASS 属 8197 历史生产**，不属于 8207 当前公开候选 GPU 证明 |

补充生产来源：[8197 正式版完整模式与用户实际使用说明](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/docs/CAPABILITY_CATALOG.md)；**不得套用 8197 回执为 8207 的发布 E2E**。

## 四、测试数字：每一个数字代表的东西## 三、测试数字：每一个数字代表的东西

| 公开记录 | 结果 | 性质 |
|---|---|---|
| Native 跨尺寸 / 前缀 | **11 PASS** | CPU synthetic latent，运行真实 Native 准备与审计代码；没有模型采样 |
| PreBake 状态与 safetensors | **11 PASS** | CPU 合同与缓存状态测试 |
| 发布防护 / 回执检查 | **9 PASS** | CPU 发布门禁测试 |
| 工作流 helper | **16 PASS** | JavaScript 离线回归 |
| 前端模块到 Python 状态桥接 | **1 PASS** | 真实模块 + Python 状态逻辑；DOM/队列传输为夹具 |
| **上述独立 CPU/JavaScript 合计** | **48 PASS / 0 FAIL** | `11+11+9+16+1=48`；**不是 48 次 GPU 视频测试** |
| 公开工作流隐私扫描 | **193 份** | 12 current + 181 history 静态扫描，不是运行性能测试 |
| 源码清单 | **140 个来源文件** | 预览发布清单的静态一致性校验口径 |
| 固定 Qwen 目标源码重建 | **11/11** | 精确版本与源码检查，**不等于模型已成功推理** |
| 历史 Qwen Image 2.1 | **4/4 GPU PASS (HISTORICAL)** | 历史独立图像路线，不自动迁移到当前公开候选 |
| 8197 历史六段视频 | **SUCCESS + 自动合并 PASS (HISTORICAL)** | 仅属 8197 版本证据，不计入 8207 公共候选的 E2E |

来源：[机器可读校验结果](../manifests/preview_validation.json)、[发布范围与证据分级](../PUBLIC_RELEASE_GATE.md)、[正式预览说明](PREVIEW_RELEASE_NOTES.md)、[R2 阻断修复](BLOCKER_RESOLUTION.md)。

## 四、关键工程升级与风险

**相对 8197 的主要实验方向：** 故事/提交快照分离、提交执行身份、运行中编辑和待执行排队、缓存依赖精确恢复、跨尺寸 Native 视频 latent 空间映射；这些是**实验特性**，不是免安装、无需验证的生产升级。

**仍然 HOLD / NOT_TESTED：**

- 公开候选的完整同版本六段 GPU E2E；
- 公开候选的真实浏览器、ComfyUI 队列与视频传输 E2E；
- 混分辨率的自动合并输出画布归一；
- 部分旧 8207 与 8197 的前端/恢复/持久化合同差异；
- 与作者私有生产环境的完整运行等价性；
- 部分图像模型的当前候选 GPU 重验。

一些旧报告开头仍保留了历史 `PUBLICATION_APPROVED=HOLD`，需结合 [更新后的 R2 修复说明](BLOCKER_RESOLUTION.md) 与 [最终独立发布门禁](../PUBLIC_RELEASE_GATE.md) 阅读；**不能把旧冻结候选 HOLD 误当当前公开预览从未发布，也不能把源码发布 PASS 当成 GPU 生产 PASS**。

## 五、导航与下载

- **只需要冻结稳定 8197 线：** [H3-Chinese-Director 正式仓库](https://github.com/asd454314633-byte/H3-Chinese-Director)（独立版本/独立验收）。
- **研究 8207 H3 六段实验：** [wf_05](../workflows/current/h3_8207_wf_05.json) → [源码/依赖重建](../REPRODUCIBILITY_REPORT.md) → [实验版 Release](https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.1.0-preview)。
- **选择图像生成与编辑工作流：** [12 份工作流中文索引](../workflows/current/README.md)。
- **许可与隐私边界：** [THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES.md) · [隐私审核](../PRIVACY_SANITIZATION_REPORT.md)。

**本文件展示的是可核查的工程范围与测试口径，不新增任何当前候选 GPU 或真实用户 E2E 验收。**
