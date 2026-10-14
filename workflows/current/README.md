# 8207 工作流选择指南 / Workflow selector

### Adaptive V1 / 2026-10-14

六段主图仍选wf_05，公开JSON与默认参数本轮不改。更新main节点源码后按[自适应说明](../../docs/ADAPTIVE_V1.md)使用；旧v0.1.0-preview ZIP不包含本次代码。作者本机PDD8六段与合并已PASS，[54.25秒实测记录](../../docs/8207_SIX_SEGMENT_GPU_ACCEPTANCE_20261014.md)不等于所有下载环境GPU PASS。Configure your own references; no private movie assets are bundled.


> **实验预览仓库，不是 8197 正式生产版。** 此目录有 **12 份脱敏 JSON**，涵盖 H3 视频导演台与其它独立图像实验。文件名 `h3_8207_wf_XX.json` 是发布时的统一编号，**不代表每一份都是 H3 视频工作流，也不代表 01→12 的执行顺序**。这里的类别来自公开 JSON 中的节点结构与工作流标识；**不意味着每条工作流已通过当前预览版 GPU 端到端验收**。

## 从哪个文件开始？

| 文件 | 识别结果（静态检查） | 使用建议 |
|---|---|---|
| [wf_05](h3_8207_wf_05.json) | **MiniMax-H3 六段视频导演台**，181 节点；含 `MiniMaxH3ImageToVideo`、`MiniMaxH3ReferenceToVideo`、六段面板与连续执行组件 | **要研究六段 H3 视频功能，从这里开始**；严格区分实验版与正式版 |
| [wf_01](h3_8207_wf_01.json) | Lustify v10 + Krea2，First Pass 图像生成（13 节点） | 仅用于对应的图像实验；不是 H3 六段视频 |
| [wf_04](h3_8207_wf_04.json) | 同类 Lustify First Pass 图像生成（13 节点） | 与 wf_01 属于同类别的不同 JSON，勿假设效果/依赖完全一致 |
| [wf_02](h3_8207_wf_02.json) | Lustify v10 + Krea2，Identity Edit 图像编辑（14 节点） | 仅用于图像编辑 |
| [wf_03](h3_8207_wf_03.json) | 同类 Identity Edit 图像编辑（32 节点） | 结构不同于 wf_02，勿盲目互换 |
| [wf_06](h3_8207_wf_06.json) | Identity Edit（14 节点） | **内容与 wf_02 Git Blob SHA 相同**；保留发布原件，不在此索引中重复推荐 |
| [wf_07](h3_8207_wf_07.json) | Lustify v10 单图风格参考实验（16 节点） | 实验路线，未据此确认稳定性 |
| [wf_08](h3_8207_wf_08.json) | 同类单图风格参考的 causal-r1 实验变体（16 节点） | 实验变体，勿视作已晋升稳定版 |
| [wf_09](h3_8207_wf_09.json) | 小型图像处理/比对图，含 `SaveImageAdvanced`、`ImageCompare`（7 节点） | 打开 JSON 内的 `Note: Usage` 核对具体功能及依赖 |
| [wf_10](h3_8207_wf_10.json) | 同类图像处理/比对图（8 节点） | 打开内部说明，不应据编号推断模型功能 |
| [wf_11](h3_8207_wf_11.json) | 小型图像工作流（5 节点，含第三方 UUID 节点） | 具体模型语义需核对节点/内部说明，**未确认** |
| [wf_12](h3_8207_wf_12.json) | 同类图像处理/比对图（6 节点） | 打开内部说明，**不属于六段视频生成链** |

**需要冻结正式 H3 工作流而非实验版？** 使用独立的 [8197 正式仓库](https://github.com/asd454314633-byte/H3-Chinese-Director) 中唯一公开工作流；**不要混装正式与实验版本的节点和缓存**。

## H3 六段工作流的内存优化选项

`wf_05` 内置 **H3 内存优化** 高级开关，**默认关闭**；只有选择适用的 **Ref2VA PDD 多参考8步** 路线后，才应评估手动开启。作者本机实测开启后首步采样准备加快、磁盘读取压力减轻，效果与内存/显存及模型环境有关，**不是对所有用户的保证**。请阅读 [内存优化使用指南](../../docs/H3_MEMORY_OPTIMIZATION.md)。本仓库不改变原工作流的默认状态。

## 下载与安全边界

1. 用 GitHub 文件页的 **Raw / Download raw file** 下载需要的 JSON；也可以从 [v0.1.0-preview 发布附件](https://github.com/asd454314633-byte/H3-8207-Experimental/releases/tag/v0.1.0-preview) 获取冻结预发布包。
2. 导入前阅读 [README](../../README.md)、[模型路径/依赖说明](../../config/third_party_nodes.json) 和 [版本锁](../../config/baseline.lock.json)。模型权重及私人素材**不随仓库发布**。
3. 先在隔离的实验 ComfyUI 副本检查缺失节点、模型、输入资源；不要将实验 JSON 直接覆盖 8197 正式生产工作流。
4. [公开预览验收门禁](../../PUBLIC_RELEASE_GATE.md)：当前 8207 公开候选**完整六段 GPU E2E = NOT_TESTED**；混尺寸自动合并仍 **HOLD**。历史 8197 成功和图像分支历史验证不等于本版全量通过。

## English summary

- **For MiniMax-H3 six-segment video:** start with [h3_8207_wf_05.json](h3_8207_wf_05.json), a 181-node experimental workflow, **not the frozen production edition**.
- **Image generation/editing experiments:** wf_01–04 and wf_06–08 contain Lustify/Krea2 image workflows. wf_02 and wf_06 have identical Git blob content.
- **Smaller image/compare templates:** wf_09–12 contain image and comparison/third-party nodes. Check each workflow's `Note: Usage` and model dependencies. Some exact capabilities remain **unconfirmed**.
- The public 8207 preview has **no same-version full six-segment GPU end-to-end acceptance**. For the validated frozen 8197 line, use the [production repository](https://github.com/asd454314633-byte/H3-Chinese-Director).

以上仅为公开工作流**结构索引**，不是新增加的运行验收报告。
