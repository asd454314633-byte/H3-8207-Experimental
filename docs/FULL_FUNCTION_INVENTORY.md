# H3 8207 中文导演台｜完整用户功能目录（基于源码、历史使用与版本证据）

**用途：** 让第一次访问 GitHub 的用户看到这个工作流**实际设计了什么功能、哪些长期在用、哪些有过真实运行、哪些只是候选或占位**。本目录不是新一轮 GPU 测试报告。

**审计口径（2026-10-14）：** 本仓库 `workflows/current/h3_8207_wf_05.json`（181 顶层节点）、公开 Python/JS、[8197 正式版完整能力目录](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/docs/CAPABILITY_CATALOG.md)、已记录的历史测试与作者本人实际使用陈述。相关本机私有目录和原始音视频未在此仓库重新读取或公开；**源码节点存在、历史使用、当前预览可移植、当前预览全链 GPU E2E 是四件不同的事**。

## 先看：五种功能证据身份

| 状态 | 解释 |
|---|---|
| **OWNER_LONG_TERM** | 项目所有者明确确认至少一个月长期、稳定地在本机使用过的能力；属真实使用陈述，不是凭空设想，也不冒充外部独立测试 |
| **HISTORICAL_GPU_PASS** | 有明确原版本、原场景的真实采样/人工或自动化验收记录；不能套用给每个新模型、每条模式或当前脱敏发布 |
| **SOURCE_IMPLEMENTED** | 当前公开工作流与节点有实际代码、参数、路由或控制接口；不等于其任意组合都通过效果测试 |
| **EXPERIMENTAL / BYPASSED** | 可见实验执行体、局部通过或默认旁路，需要独立条件、依赖与实际验证 |
| **PLACEHOLDER / UNAVAILABLE** | 仅架构规划、无可运行实现；**不能作为已交付功能展示** |

**不要把 `NOT_RETESTED` 写成“没有实现/不能用/历史从未通过”。** 反过来，也不能把长期使用的作者口径升级为 `CURRENT_8207_PREVIEW_GPU_E2E_PASS`。

## A. 全中文可视化操作

| 功能 | 用户看到/可以做的事 | 依据与状态 |
|---|---|---|
| A01 全中文主控台 | 在 N159 集中管理操作与生成参数，不必逐个修改底层节点 | 公开 JSON + `H3OperationSelector`；SOURCE_IMPLEMENTED |
| A02 五个实际操作阶段 | 只跑一采、检测坏段、放大/扩时、执行二采、自动检测+扩时+二采（实验） | 源码 `H3OperationSelector.MODES`；一采是主路线，其它按各自执行状态判断 |
| A03 全旁路 | 关闭所有操作阶段，避免误提交采样 | 第六项“无任何选项状态”；SOURCE_IMPLEMENTED |
| A04 操作阶段互斥与卡片执行 | 切换当前操作、查看被启用执行位，支持对应独立按钮 | `h3_workflow_ux.js` / 8197 目录；前端合同存在 |
| A05 参考模式提示 | 在面板中区分“多参考图”和“单首帧”，防止误以为四图全部输入 FL2VA | `h3_foolproof_v3_dashboard.js`；SOURCE_IMPLEMENTED |
| A06 素材上传 | 参考图、首帧、可选尾帧、参考视频、参考音频分别上传与清理 | N159 Dashboard；SOURCE_IMPLEMENTED |
| A07 生成参数 | 长宽比、百万像素、秒数、实际帧数、随机种子、步数、推荐值恢复 | Dashboard + 选择器；SOURCE_IMPLEMENTED |
| A08 分支设置 | 生成模式、采样档、Ref2VA 后端、注意力、可选内存优化 | `h3_workflow_helpers/nodes.py` 与主图；运行受版本/模型资产约束 |
| A09 一采/二采调参 | 分开的采样调节区，避免把首次生成和二次修复混为一项 | Dashboard；SOURCE_IMPLEMENTED |
| A10 UI 易用性 | 控制台/六段面板定位、缩放、面板尺寸调整、素材清理与错误提示 | 六段 UI + dashboard；源码接口存在，浏览器兼容仍需实测 |

## B. 视频生成引擎、输入与多参考

| 功能 | 用户价值与正确边界 | 依据与状态 |
|---|---|---|
| B01 Ref2VA 多参考 | 将人物外观/动作等图片、视频、声音参考送入 H3 多参考模型 | `MiniMaxH3ReferenceToVideo` 等；8197 多参考真实生成记录，8207 公开候选须分别验证 |
| B02 FL2VA 文生视频 | 不用图片也能通过提示词生成视频 | `H3ImageModeSelector` 与 `MiniMaxH3ImageToVideo`；SOURCE_IMPLEMENTED |
| B03 FL2VA 单首帧 | 上传一张起始图片指定首帧，推进成视频 | 同上；与 Ref2VA 多图模式严格分离 |
| B04 FL2VA 首尾帧 | 上传首帧、尾帧形成约束 | 源码模式存在；不可推导“多张参考图全部生效” |
| B05 多参考图片槽位 | 可显示更多输入位置，但各分支能消费的图片数量不相同 | 当前面板支持多槽；**槽位数不等于实际进入 DiT 数** |
| B06 参考视频 | 作为镜头、动作或音画来源，路由与人物身份需按提示词约束 | `LoadVideo`、`GetVideoComponents`、Ref2VA 参考路由 |
| B07 图片与视频预检 | 对上传资源缺失/格式/未连接进行提示或拦截 | SOURCE_IMPLEMENTED；不保证各种格式可用 |
| B08 首次生成输出 | H3 音视频 latent → 视频/音频 VAE → MP4/视频结果 | 主工作流与 `SaveVideo`，历史真实视频存在 |
| B09 Ref2VA 稳定8步 | 带多参考的 Stable8 路线 | **HISTORICAL_GPU_PASS（8197 指定场景）** |
| B10 Ref2VA PDD8 | PDD 加速 8 步、模型 patch/注意力的独立执行路线 | **HISTORICAL_GPU_PASS（8197 指定场景）** |
| B11 Native Ref2VA 20步 | 高级诊断档，无对应加速 LoRA | SOURCE_IMPLEMENTED / **诊断专用**，不推荐当默认生产 |
| B12 FL2VA F4 | FastH3 VSA 四步（FL2VA 家族） | 有执行分支，**绝不是“Ref2VA 四图四步已验收”** |
| B13 FastH3 V2 八步 | 官方蒸馏权重的独立实验链、默认旁路 | EXPERIMENTAL / BYPASSED；以实际模型支持模式为准 |
| B14 一采速度偏好 | 默认、画质优先、高速平衡三档；调整采样器/注意力/精度的不同实现 | 路由已实现，**未有足够同条件样本保证哪档总是最快或最好** |
| B15 注意力可选 | 标准/INT8、Sage/稀疏等分别接在特定路线 | 部分SOURCE_IMPLEMENTED/实验，**SLA 仍是纯占位** |
| B16 可选内存优化 | 仅 PDD8 分支的 H3 Memory Optimization 开关，默认关闭 | 不宣称有稳定收益 |
| B17 输出尺寸策略 | 预设或自定义尺寸、比例、32 对齐，画布记录 9:16/0.6MP 样例 | SOURCE_IMPLEMENTED；显存与画质依赖实际条件 |

## C. 音色、声音、角色与音频（重点恢复）

**作者明确确认：参考音色/音色克隆引导**早已通过实际视频生成使用，且**在本机稳定使用至少一个月**。正确身份是 **OWNER_LONG_TERM**，不是“从未验证、不可用”。记录时间为 2026-10-14；原始私有生成日志没有随 GitHub 发布，因此也**不能**虚构独立 GPU 评分或当前 8207 公开预览的同版本质量验收。

| 功能 | 具体表现 | 正确状态 |
|---|---|---|
| C01 参考音色 1/2/3 | 三路独立人声参考，分别上传、单独启停并映射到模型参考输入 | **OWNER_LONG_TERM（参考音色功能整体）** + SOURCE_IMPLEMENTED；三槽任意组合的质量不全部等同 |
| C02 音色与角色绑定 | 按已启用来源的真实顺序映射 `<Audio 1>` / `<Audio 2>` / `<Audio 3>`，支持第三角色文字用途 | SOURCE_IMPLEMENTED；有助于避免声音错位 |
| C03 视频原音轨参考 | 可独立启用视频自身音轨，以 `<VideoSoundtrack>` 引用，与三路独立音色参考区分 | SOURCE_IMPLEMENTED；音轨编号会按映射调整 |
| C04 参考音频预检 | 单条独立参考 2–15 秒、已启用独立音色总时长 ≤15 秒；检验未连接/异常输入 | `H3Audio8ReferencePreflight`、`H3AudioReferencePack`；不是“改变用户原始音频” |
| C05 参考开关控制真正提交 | 不是仅仅保存音频文件，前端会将启用状态写入对应 `ref_audios` 参考边 | `H3_Audio8Step/web/audio8.js`；SOURCE_IMPLEMENTED |
| C06 Stable8/PDD8 音色路线 | 8步 Ref2VA 的音色参考与普通视频采样组合 | 音色长期使用和 Stable8/PDD8 历史运行各有证据，**不将全部组合自动评为新版本 PASS** |
| C07 Stock20 音色优先 | 无 Turbo 的 20 步原生音色质量选择 | 有候选代码和独立路线，具体效果状态与 8 步不可混写 |
| C08 高速音频路线 | 保留当前 8 步音频路线的可选档位 | `H3_AudioUpgrade`；SOURCE_IMPLEMENTED/按使用场景验证 |
| C09 最终音轨指定 | 上传本机 WAV/TTS 等作为输出音轨；和音色参考**不是一件事** | `H3ExactAudioLock` 等；未核验不同素材下的声画同步 |
| C10 音频精修 | 随一采精修，或仅读取最近的一采缓存进行音频精修、不重新采画面 | `H3AudioRefineGate`；EXPERIMENTAL/需相关外部依赖 |
| C11 音视频双流分离/合并 | 双流 latent 的形状校验、视频与声音路径对应处理 | `H3_AudioUpgrade/nodes.py`；SOURCE_IMPLEMENTED |
| C12 多角色情绪/语气 | 在提示词中表达人物声音、音色属性、台词语气、情绪与节奏；不等于每种表达都被模型可靠遵从 | 中文导演与提示词编译相关；需要按实际人声结果判断 |
| C13 音频规则提示 | 参考音色、原音轨、TTS 驱动、背景声音各自不同；没有上传的音频不能凭空在提示词中伪称“引用音频1” | 用户长期使用纪律 + 源码提示词约束 |

**源码入口：** [Audio8 步参考预检](../custom_nodes/local_author/H3_Audio8Step/nodes.py) · [三音色前端](../custom_nodes/local_author/H3_Audio8Step/web/audio8.js) · [音频精修节点](../custom_nodes/local_author/H3_AudioUpgrade/nodes.py) · [音频 UI](../custom_nodes/local_author/H3_AudioUpgrade/web/audio_upgrade.js)。

## D. 六段故事、连续生成与剪辑

| 功能 | 实现或效果 | 状态 |
|---|---|---|
| D01 六段独立草稿 | 六段分别输入、编辑、保存状态、手动使用/执行 | 已有实际生成与 UI 记录 |
| D02 单段生成 | 选择某一段生成，不需要每次提交所有六段 | SOURCE_IMPLEMENTED |
| D03 连续生成 | 串行使用有效上一段进行续跑，支持开始段/独立起点 | 8197 **HISTORICAL_GPU_PASS**；当前 8207 预览端到端不能直接继承 |
| D04 Native AV latent 接续 | 延用前一段真正的音视频潜空间，包含声音/动作余势，而不是 MP4 拼接 | 8197 真实验收；8207 Native CPU 合同 11 PASS |
| D05 同网格接续 | 相同分辨率场景尽量保持实际前序 latent 数值 | 8207 CPU 合同；GPU 质量新候选未重验 |
| D06 跨分辨率接续 | 只对视频 latent 前缀做网格重采样并记录变换；音频前缀原样 | 8207 CPU 合同；跨尺寸画质等价未证明 |
| D07 Story/Execution 独立 | 草稿编辑不覆盖已提交执行快照，新的任务独立 attempt | 8207 回归合同；真实并发队列完整 E2E 待补 |
| D08 运行中继续编辑与排队 | 可以继续编辑后续草稿、单击提交进入队列 | 实验功能，CPU/JS 验证，不把它说成“不能用” |
| D09 PreBake 提前缓存 | Conditioning 缓存与身份校验，按实际依赖补建和失效 | 8197 历史离线验证 + 8207 CPU 回归 |
| D10 安全恢复与版本保护 | SUCCESS、prompt、前序 latent SHA/回执匹配，不用错误旧缓存冒充前序 | SOURCE_IMPLEMENTED + 离线验证 |
| D11 六段结果查看 | 视频片段可在段落面板定位预览，控制台可定位 | 已实现 UI |
| D12 六段自动合并 | 汇总同故事合法视频结果，按 SUCCESS 和身份门禁合成 | 8197 **HISTORICAL_GPU_PASS：996帧/24fps**；8207 当前候选须另验 |
| D13 混尺寸合并 | 输出画布统一与不等尺寸拼接 | **HOLD**；不得假定已解决 |
| D14 Clean Rebase + 单帧 Guide | 在独立重起段使用前段真实画面 frame0 Guide 辅助视觉衔接 | 8197 **HISTORICAL_GPU_PASS_WITHIN_SCOPE**，不同于多时间点 Guide |
| D15 跨段人物和动作连续性编排 | 固定角色/服装、相邻段姿态/支点/镜头方位、前置→动作→惯性→收尾 | 导演规则/真实工作流程；属于编排与模型生成的综合结果，不声称 100% 无漂移 |

## E. 关键帧、动作控制、二采和后处理

| 功能 | 实现或效果 | 状态 |
|---|---|---|
| E01 Guide 关键帧图片 | 提供指定画面锚点，让画面在相应时间点靠近目标 | 部分源码/开关存在；不能与单帧 Clean Rebase 测试混淆 |
| E02 1/2/3 个关键画面 | UI 可选 0–3 个关键帧；未提供图片时有哨兵/错误阻断 | SOURCE_IMPLEMENTED，组合 E2E 各自需验证 |
| E03 多时间点 Guide Timeline | 以时间/帧锚点编译 `MiniMaxH3AddGuide` 控制 | EXPERIMENTAL/BYPASSED |
| E04 Pose / Depth 姿态深度 | Fun ControlNet 相关 Apply、姿态预处理和图像预览 | 公开画布默认旁路，不冒称自动支持所有人物动作 |
| E05 参考视频 V2V/RV2V | 上传原视频后走重绘/融合编排 | PARTIAL/DEFAULT BYPASS |
| E06 坏段检测 | `H3JerkOracle` 寻找高速运动问题区间、导出 hold map 与报告 | 具节点和执行阶段 |
| E07 放大扩时 | `H3TimeSmear` 生成扩时预览或方案，非默认自动修复 | 实验阶段 |
| E08 手动二采 | `H3V2VInit`、`SamplerCustomAdvanced`、`H3ExactRecover` | 默认旁路/条件执行 |
| E09 自动坏段窗口修复 | `H3WindowLoop` 检测后按条件修复 | 明确标注 EXPERIMENTAL |
| E10 采样过程预览 | `ModelPreviewOverrideKJ` 等接口 | 依赖插件，可选，效果需核验 |
| E11 高分辨率 Progressive/SelfLift | 只有规划位置，没有本版实际执行实现 | **PLACEHOLDER / UNAVAILABLE** |

## F. AI 导演、提示词与独立图像工作流

| 功能 | 用途 | 状态 |
|---|---|---|
| F01 不依赖 AI 的六段手写 | 直接输入中文提示词，无须 AI Director | 真实基础功能 |
| F02 可选 AI Director | 调用兼容本地模型生成/编辑剧情提示词，仍需应用到具体段落 | 公开 `H3_V28_Director` / `H3_Prompt_Sidecar` 源码；特定 Provider 以实际部署为准 |
| F03 物理可行性与连续性规则 | 编排人物动作、重心、关键接触、摄影机、衔接 | `V28` 规则与 tests 存在；文本编译不是 GPU 生成质量验收 |
| F04 提示词格式/引用检查 | 参考素材编号、角色/音频指代、模式与禁用输入检查 | SOURCE_IMPLEMENTED |
| F05 首帧/多参考的语义分离 | 防止角色身份与动作/相机参考互相污染 | 导演合同与 `H3VideoPromptRole` |
| F06 Qwen Image 2.1 | 独立的图像生成/编辑实验，不是六段 H3 视频必装项 | 历史有 **GPU 4/4 PASS**，公开候选没全部重测 |
| F07 Lustify/Krea2 First Pass | 独立文生图实验：wf_01、wf_04 | 工作流存在；不等于 H3 视频 |
| F08 Lustify/Krea2 Identity Edit | 独立人物/物体图像编辑：wf_02、wf_03、wf_06 | 工作流存在；具体效果按原环境验证 |
| F09 风格参考实验 | wf_07 / wf_08，单图参考/因果变体 | EXPERIMENTAL |
| F10 其它图片辅助模板 | wf_09～12，图像比对、输出与第三方节点 | 部分精确用途未确认，按 JSON 内 `Note: Usage` 判断 |

工作流逐份索引：[12 份 JSON 选择指南](../workflows/current/README.md)。

## G. 资源管理、稳定性与安全保护

- **TE 模型卸载、Adaptive Host Warm、VAE 前部分显存/内存释放**：8197 历史生产存在真实验收，8207 发布源码内有相应模块；不能声称所有机器或所有路线都稳定提速。
- **资源预算与显存限度**：历史 8197 报告的峰值 22,016 MiB（特定样本），主机内存余量有限；不是保证 24GB 卡上所有功能同时开启。
- **采样超时与保护**：用户生产验收有 300 秒止损原则，超时取消属于本机运行纪律，不等于公开包所有调度路由都逐项实现统一限时。
- **任务身份与错误阻断**：缺少有效参考、错误前序、回执不一致、缓存失效等不能静默当作成功。
- **第三方来源与许可**：外部 MiniMax 官方提示词 Skill、ComfyUI、AudioRefine 等各有独立来源与许可，不随本仓库权利一并转移。
- **历史与正式包隔离**：8197 正式冻结、8207 公开预览、历史实验和用户本地生产配置互不等价。不得把 8207 工作流混装到 8197 冻结生产链。

## H. 已核实的“真实使用”和“测试”为什么不能合并成一个 PASS

| 证据来源 | 可以写什么 | 不应写什么 |
|---|---|---|
| 项目所有者直接陈述（2026-10-14） | **“音色参考已经实际生成使用，稳定使用至少一个月”** | “独立第三方音色保真测试通过” |
| 8197 历史六段验收 | “六段真实 SUCCESS；自动合并 996 帧；单帧 Guide/Clean Rebase 在受测场景通过” | “8207 所有模式已 GPU 自动验收” |
| 8197 Stable8 与 PDD8 旧 A/B 运行 | “两条独立 Ref2VA 8步路线在指定参数下生成通过” | “任意参考组合都同样稳定、同样快” |
| 8207 发布 CPU/JS 报告 | “11 Native + 11 PreBake + 9 发布防护 + 16 JS + 1 桥接 = 48 PASS” | “做过 48 次 GPU 生成” |
| 当前公开 `wf_05` 与源码 | “可以定位功能执行体、UI 与参数范围” | “代码存在 = 任意用户已一键部署可用” |
| SLA / Progressive / SelfLift | “尚无可执行实现” | “已支持一键增强” |

**最终展示原则：先告诉用户产品能力和操作路径，再在具体能力处精确标出证据。不要让 `NOT_TESTED` 字样掩盖已经真实长期使用的功能。**

## 导航

[8207 中文首页](../README.md) · [英文首页](../README_EN.md) · [功能证据台账](CAPABILITIES_AND_EVIDENCE.md) · [发布门禁](../PUBLIC_RELEASE_GATE.md) · [8197 正式版完整能力目录](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/docs/CAPABILITY_CATALOG.md) · [工作流选择指南](../workflows/current/README.md)

**最后边界：** 本文使用公开源码与已有历史资料、作者本人长期使用陈述重建功能目录；尚未直接扫描作者 Windows 上的 D: 等本地目录，也未重新运行 GPU 或浏览器 E2E，因此不冒充“本机逐项源码/回执重新终验”。
