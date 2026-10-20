# H3 V29｜本机性能、显存生命周期、缓存与历史裁决总索引

> 更新/汇总：2026-10-20。**这是一份历史证据索引，不是新的 GPU 实验报告，也不是 8207 当前版本的性能承诺。**  
> 适用：8197 冻结生产 V29（历史），以及 8207 V29 实验线（独立事实）。接收方公开构建 GPU 验收不由历史本机 PASS 自动推导。  
> 目的：以后研究 H3 性能时先查本页，避免把已修复问题重新排查、把旧 HOLD 误读为最终状态，或重复已明确否决的试验。

## 0. 先看最终结论（避免重复研发）

- **已开发且历史真实验收**：Conditioning PreBake/Load、Qwen3-VL-32B 文本/视觉编码后选择性卸载（N1057）、H3 DiT 采样后在视频/音频 VAE 前部分释放（N1058）、Adaptive Host Warm、Pinned Memory ON + DynamicVRAM + Async Offload 两流、Ref2VA PDD8、Stable8/PDD8 共享 N1058 生命周期。
- **曾经确实找到并修复的 I/O 根因**：Adaptive 对 H3 完整卸载，可导致同一 H3 主 checkpoint 重新发生约 20.874GB 的逻辑读取；有条件 Host Retention V2 将受测读取量降至约 17.015GB（-18.4842%），但仍有部分读取和 RAM 余量问题。
- **经实测不推荐重复尝试**：关闭 Pinned Memory；把 pinned cap 限制到 16GiB；把 H3 **主扩散模型**由 INT8 ConvRot 换成 NVFP4（该次后段脸部损坏）；只凭单次对照升级 ComfyUI 0.39.2 或切 fast_disk 就宣称提速。
- **尚未证实的性能收益**：最新 8207 v0.4.0 的分阶段 P50/P95；8207 INT8 视频 VAE 对 FP16 视频 VAE 的严格同条件解码 A/B；默认旁路的 BlockSparse/稀疏注意力在本机无损提速；可在 Windows 原生正式链直接复用的全新 H3 DiT 融合内核。
- **不要混淆量化对象**：被画质测试拒绝的是 **H3 DiT 主 checkpoint NVFP4**，**不是**工作流 N128 的 Qwen3-VL-32B NVFP4 AWQ 文本/视觉编码器。

## 1. 如何理解本页数字

| 证据标签 | 含义 |
|---|---|
| HISTORICAL_GPU_PASS | 作者本机当时的真实 GPU 运行及报告结论；**原始私有 History/视频未在公开仓库完整发布** |
| HISTORICAL_MEASURED | 历史记录有具体读数；可来自同一进程、资源采样、节点事件或人工观察，**不保证统一 A/B 口径** |
| HISTORICAL_REJECTED | 试验执行过，但因画质、内存安全或无可靠收益而拒绝晋升 |
| SOURCE_PRESENT | 工作流或源码中找到节点、接口、选择器，不能直接宣称当前在线/默认执行 |
| LATEST_LOCAL_PASS | 2026-10-20 的本机 8207 v0.4.0 特定条件 GPU 验收 |
| NOT_ESTABLISHED | 当前没有充分同条件实测，不能做速度/画质承诺 |

**事实源**：作者本机按时间追加的《H3 V29 维修记录.txt》（特别是第 2–9、20、23–27 节、2026-10-09 晚间两份专项）、《00_当前状态.md》，以及仓库内的 GPU/发布报告。上述旧私有文档存于作者历史归档，不作为本仓库公开附件；下文仅摘录必要的非敏感测试指标、裁决与追溯名称。**本页为归档文本转录和交叉索引，不等于本次从原始 GPU 遥测重新计算**。

## 2. 8197｜已做过的内存/缓存/GPU 优化（2026-10-05 至 10-09）

| 日期 / 主题 | 已记录的实际结果 | 最终裁决 / 限制 |
|---|---|---|
| 10-05 Pinned Memory ON/OFF | OFF：204.33s、后段 D 盘约 1220MB/s；ON：126.43s、后段约 38.8MB/s | **保持 ON**；单次历史对照，非当前8207承诺 |
| 10-05 pinned cap=16GiB | 约 126.33s，RAM 峰59.08GiB，Commit99.73%，最低可用 RAM2.56GiB | **REJECTED**；恢复默认约24.66GiB cap |
| 10-05 Qwen TE 选择性卸载 | TE约14.610GiB、pinned约14.601GiB；准确卸载约14.601GiB，全局 pinned约15.272→0.672GiB | **GPU 测量 PASS**；最后 TE consumer 为 N136，PDD 不使用 TE |
| 10-05 VAE 前完整释放 H3 | H3/Video VAE 共驻留时 RAM 峰约55GiB；精确卸载后 VAE 阶段约33.916–34.348GiB | **历史路径 PASS**；后续全量 reload 导致 I/O 成本，已演进为部分释放 |
| 10-05 N1058 部分释放 | H3 GPU residency约9.3–9.6→0.970GiB，同时 HostBuffer/host cache可留约19.525GiB | **GPU 测量 PASS**；Host 缓存并非无条件保留 |
| 10-05 Adaptive Host Warm V2 | RUN1建热 Host 约19.525GiB；RUN2新提示词先释放 Host，RAM峰55.059GiB/最低可用6.582GiB；RUN3缓存命中首步10.057s、Commit峰90.215%，视频通过 | **三条真实路径 PASS**；避免 TE 约14.61GiB 与整份 H3 Host 重叠耗尽64GB内存 |
| 10-06 N1058 current-residency 维修 | 冷视频139.189s、热视频86.404s；均192帧/8步，两路VAE及输出通过，释放后GPU loaded约0.970GiB | **PRODUCTION_PASS**；两次系统 RAM 低水位约2.489/1.746GiB，MEMORY_MARGIN=LIMITED；不能把冷热差全归为同一优化收益 |
| 10-06 Stable8/PDD8 N1058 兼容 | Stable8 111.186s、PDD8 110.052s，均608×1056/192帧/8步；前者 turbo patches208，后者 PDD patches308；两路VAE/视频通过 | **兼容修复 PASS**；首次中止任务不算完成视频；不能按约1秒差推断稳定速度优势 |
| 10-06 INT8 H3 主模型 vs NVFP4 主模型 | 同seed/提示词/4参考图/192帧/8步：INT8 152.490s、逻辑读取20.874GB、VRAM19.941GiB；NVFP4 131.622s、读取11.240GB、VRAM20.603GiB | **NVFP4_COMPAT_FIX=PASS；生产替换 REJECTED**：179–191帧面部重影/结构破碎、服装纹理变弱；约10%整体画质损失是单 seed 人工评估，非统计保证 |
| 10-06 PreBake 早期无损核心验证 | N136完整 CONDITIONING+嵌套 AV latent：8张量/76,601,552 bytes，无损差异0；对照192解码帧完全相同 | **固定输入范围 PASS**，不是只有 text embedding；首次 Bake7.492s使用了遗留 warm TE，不能称冷端到端提速 |
| 10-06 PreBake 两段动态续接 | 两段86.687s / 91.696s，同 PID，H3 checkpoint读取均0 / full reload0；SEG2承接SEG1真实 AV latent，Prefix误差按阶段界定 | **两段真实 GPU PASS**；静态 conditioning 可提前 Bake，动态末帧/前序 latent 不能盲目提前缓存 |
| 10-06 六段 PreBake 生产晋升 | 六段静态条件 Bake；SEG1真实生成，SEG2真实前序 AV latent，SEG3–6 SUCCESS；自动合并39.875s（**成片时长**，非耗时） | **8197 PRODUCTION_PROMOTION PASS**；74项只读复核为检查项，不是74次GPU生成 |
| 10-09 8197 最终六段冻结验收 | 各段132.926 / 92.423 / 90.368 / 87.255 / 91.070 / 90.277秒；合并996帧/24fps，合并操作耗时41.5s；GPU峰22,016MiB、最低可用RAM5.94GiB、Commit峰95.05GiB | **冻结指定故事/配置生产 PASS**；Clean Rebase+单帧Guide接缝通过，不代表任意故事无漂移 |

**原件追溯**：私有维修归档（2026-10-05 至 10-09）；8197 公开指标入口：[benchmarks/SUMMARY.md](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/benchmarks/SUMMARY.md)、[benchmarks/runs.csv](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/benchmarks/runs.csv)、[docs/CAPABILITY_CATALOG.md](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/docs/CAPABILITY_CATALOG.md)。

### 2.1 重复读取根因：注意旧 HOLD 已被后续结论覆盖

- **10-06 第一轮 HOLD（第23节）**：当时只有冷启动首次读约20.874GB、内存闸门中止，不足以声称“反复整读”，ROOT_CAUSE=UNCONFIRMED。**这是旧时点，不是最终答案**。
- **10-06 第25节重新做同进程因果实验**：同一个 H3 LoadedModel/patcher、预热后19.525GiB Host backing、N136 pre-TE full unload→0、再次加载同主模型逻辑读取20,873,793,024bytes，约为主文件20,970,379,616bytes的99.54%；随后完整8步/VAE/视频通过。正式裁决：ROOT_CAUSE=ADAPTIVE_FULL_UNLOAD_CAUSES_H3_CHECKPOINT_REREAD、CAUSAL_SEQUENCE_PROVEN=YES。
- **同日 V2 RAM-aware 有条件保留修复**：按可用 RAM、Commit 与 TE 14.75GiB+工作区3GiB预算，部分释放并保留约3.631GiB H3 Host；主 checkpoint 逻辑读取降至17,015,437,824bytes，**减少18.4842%**；完整视频107.886s通过，最低可用RAM5.0003GiB、Commit峰88.2324%。不足则仍允许安全全卸载。
- **严谨边界**：统计的是进程内按 H3 文件识别的成功逻辑读取请求，**不是** ETW 物理 NVMe 吞吐；减少18.4842%也不是整段视频提速18.4842%；该修复并未证明整机 I/O/换页问题全面解决。

对应私有报告标识：H3_PDD8_DISK_THRASH_ROOTFIX_20261006、H3_PDD8_IO_CAUSAL_CLOSURE_AND_ROOTFIX_20261006、H3_NVFP4_COMPAT_AND_QUALITY_AB_20261006、H3_CONDITIONING_PREBAKE_20261006、H3_PREBAKE_PRODUCTION_INTEGRATION_20261006。

## 3. 8207｜单卡专项与最新版证据不可混用

| 日期 / 版本 | 实际观察 | 证据结论 |
|---|---|---|
| 10-09 8207 PreBake RAM headroom/TE释放候选 | 一轮 PreBake14.441s + 视频104.113s，端到端119.808s；另一轮36.329s +137.636s，端到端175.222s；物理Drive3读取35.5601GB→34.9557GB（-1.70%） | 缓存身份/回执/内存安全PASS；**端到端性能 NOT_PASSED、生产晋升NO**；两轮负载和干扰不同，不能因果断言补丁拖慢了55s |
| 10-09 0.36.0/0.39.2 单卡性能专项报告v2 | 受测同类8步/192帧PDD8：N125进入→首个progress **30.7–36.2s**（权重加载+首步准备）；progress 1→8 **58.4–59.7s**（7个进度间隔，约8.39–8.58s/间隔） | 最大已观察等待来自采样前的加载窗口；去噪内核差约1.4–2.0%，并未验证稳定总提速 |
| 10-09 正式对照样本 | 0.36.0带候选补丁两轮104.35/137.87s；0.36.0生产干净树一轮115.63s；0.39.2两轮89.18/107.22s | **分布、样本数、代码基线不相等，不得宣传0.39.2提升X%**；无头违规轮 VOID、不计统计 |
| 10-09 fast_disk 专项 | 新版fast_disk确实启用过；切换差异18.04s，单侧n=1，落在约20%波动内 | FAST_DISK_BENEFIT=NO_RELIABLE_EVIDENCE；冻结生产基线 fast_disk OFF |
| 10-09 SSD线索 | 旧H3模型文件读取实测约1.79–2.28GB/s；同盘新文件写可达5.89GB/s；H3文件6盘区、TE文件3盘区 | **不是同一种读取/写入基准，不能认定SSD故障或碎片化** |
| 10-14 8207六段视频 | 243帧各段执行221.264 / 158.350 / 158.218 / 156.967 / 160.882 / 160.197s；保存1302帧，54.25s成片 | **指定本机 GPU PASS**；该次资源峰值 NOT_RECORDED，不能拿8197的峰值硬套 |
| **10-20 8207 v0.4.0** | 真实六个新键 Bake→持久化→Load→GPU；受控无缓存对照全部video/audio latent及153解码帧相同；真实两组六段最终1875帧/24fps、音视频均78.125s | **LATEST_LOCAL_PASS（功能/无损与连续性）**；不是“最新VAE/内核已测速”，没有提供同配置完整分阶段加速比 |

上表 8207 本仓库证据入口：[2026-10-20 验收](CLOSEOUT_ACCEPTANCE_20261020.md)、[2026-10-14 六段验收](8207_SIX_SEGMENT_GPU_ACCEPTANCE_20261014.md)、[内存优化开关的证据边界](H3_MEMORY_OPTIMIZATION.md)、[本机与公开构建区别](CAPABILITIES_AND_EVIDENCE.md)。

**10-09 性能报告v2必须优先于其v1**：v1错误混入 VOID 样本、写反缓存释放阈值语义；v2已纠正。FINAL：END_TO_END_PERFORMANCE_GAIN=NOT_ESTABLISHED；DENOISE_KERNEL_EQUIVALENT=CONFIRMED（仅受测配置）；PRODUCTION_PROMOTION=NO；NEAR_PERFORMANCE_CEILING=NOT_ASSERTED。不得重新使用旧“已经接近性能上限”表述。私有报告标识：H3_V29_SINGLE_GPU_PERF_20261009 / H3_V29_SINGLE_GPU_PERF_FINAL_REPORT.md（v2）；有统一的 analyze_perf.py、CORRECTED_STATS.json 与分阶段 events/resources 数据。

## 4. 工作流已有的节点与当前缺口

8207 主图 **[workflows/current/h3_8207_wf_05.json](../workflows/current/h3_8207_wf_05.json)** 的源码核对：

| 技术点 | 目前已具备什么 | 不能宣称什么 |
|---|---|---|
| N128 Qwen3-VL-32B | 工作流 CLIPLoader 指向 Qwen3-VL-32B NVFP4 AWQ 文本/视觉编码器 | 不要把此编码器与被拒绝的 **H3 DiT NVFP4** 混为一谈 |
| N1057 H3SelectiveTEUnload | 已连到最终 BasicGuider 的 conditioning 依赖链，有精确目标/残留验证源码 | 仅存在连线不等于每一次缓存命中都需要卸载TE；缓存命中允许合法SAFE_NOOP |
| N1058 H3PartialDiffusionEvictBeforeVAE | 已接在 SamplerCustomAdvanced latent → Video/Audio VAE 两路之前；代码可对当前H3 loaded模型部分卸载 | 不能把“释放 GPU 9GB”误记为“减少9GB系统RAM”或“直接快9倍” |
| Adaptive Host Warm | 有对官方 N136 class 的 in-place hook、预留内存预算和观测代码；8197有历史三路GPU验收 | 不得无条件常驻整个Host权重；8207最新实现需按真实激活状态/日志判定 |
| N1006 PDD Acc | PDD Ref2VA 8步实跑、模型分支与PDD patches证据 | 不能推导任意FastH3/FL2VA路线等价 |
| N950 INT8 Attention | 内置注意力后端的可选路由存在 | 缺最新8207相同条件/同资源负载的严谨速度A/B |
| N998 H3MemoryOptimization | PDD8高级开关存在，公开模板默认关闭；作者报告首步更快、磁盘压力下降 | **没有量化开/关严格A/B**，不把反馈写成百分比 |
| N862/119 + N872 视频 VAE | INT8 ConvRot视频VAE与FP16视频VAE两个loader及切换器存在 | **未找到最新8207同seed/同模型/同潜变量仅切VAE的解码速度和画质严格对照** |
| N966/980 BlockSparseAttention | 工作流存在实验节点；当前主路线并非默认有效启用 | 稀疏注意力改变模型计算，不能直接认定“无损”或正式生产提速 |

本索引与上述源码节点编号均对应已公开的 **8207 wf_05**；8197 历史相似编号不代表每个时点节点完全相同。

## 5. 以后查询顺序 / 不重复实验规则

1. **先判断版本线**：8197 历史生产 / 8207 历史实验 / **8207 v0.4.0 当前功能验收**。先读本页，再读[最新版验收](CLOSEOUT_ACCEPTANCE_20261020.md)及[8197性能表](https://github.com/asd454314633-byte/H3-Chinese-Director/blob/main/benchmarks/SUMMARY.md)。
2. **同一事项读最后裁决**：10-06 磁盘根因“第23节 HOLD”→“第25节 CAUSAL_SEQUENCE_PROVEN=YES”；Stable8 兼容从HOLD→第24节PASS；PreBake从早期独立候选→正式8197晋升→8207 v0.4.0新键GPU消费PASS；报告v1更正以v2为准。
3. **不要重启/改正式线重复已拒绝项目**：Pinned OFF、16GiB cap、H3主模型NVFP4取代INT8、仅依赖fast_disk或新版ComfyUI、未经画质A/B的稀疏采样。
4. **目前可以仅做只读核验的两项**：最新8207 v0.4.0在真实成功History中各阶段时间、重复模型加载；现有INT8/FP16视频VAE究竟哪个分支在执行。缺少严格同条件样本时标NOT_ESTABLISHED，不为了补表主动改变生产基线。
5. **严格区分“已实现”“运行时生效”“功能GPU通过”“显存内存实测”“稳定端到端加速”**。除非新增可复核A/B记录，否则不将任一阶段局部收益升级为完整视频提速。
6. **不把历史私人证据放到公开包**：原始场景/参考图/长歌/History/任务身份/本机账户绝对路径均只保留在作者私有档案。此页只保留非敏感统计、报告标识及公开仓库交叉链接。

> 更新原则：后续新结果请追加“日期｜环境指纹｜同条件输入｜样本数｜执行阶段｜资源峰值｜画质比较｜最新PASS/HOLD/REJECTED｜原始证据位置”，**不要静默覆盖旧裁决或把旧数据改写成新GPU重跑**。
