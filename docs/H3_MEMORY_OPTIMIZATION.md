# H3 内存优化｜Ref2VA PDD 8步（可选）

> **重要提醒：此功能在公开 8207 工作流中默认关闭。** 在适用环境中，手动开启后，作者本机实测首步采样启动更快，磁盘读取负担明显减轻，并报告运行稳定。这里记录的是**作者本机实际使用反馈**，并非所有硬件的统一加速保证，也没有公开可复核的开关前后量化对照数据。

## 适用范围与默认状态

- 目标工作流：[h3_8207_wf_05.json](../workflows/current/h3_8207_wf_05.json)，MiniMax-H3 六段视频导演台。
- 界面开关：**「H3 内存优化（仅 PDD 8步）」**。
- 两种选择：**「关闭（生产默认）」**、**「开启（高级可选）」**。
- 公开模板中 `H3MemoryOptimizationSelector` 为「关闭」，`h3_memopt_default=OFF`；PDD 分支预留 `H3MemoryOptimization` 节点。
- 此处的开关面向 **Ref2VA 的 PDD 多参考 8 步分支**。不要把收益自动归因于 Stable8、FL2VA F4、Native20 或其他生成模式，也不要将「存在同名节点」理解为所有分支都会执行它。
- **保持默认关闭**，以便不同机器先按保守配置启动。是否开启由用户按硬件、模型和效果自主选择；开启状态会反映在当前工作流设置中，请保存自己需要的配置版本。

## 如何开启

1. 在 ComfyUI 中加载六段视频工作流 `wf_05`，并确认使用的是**多参考 Ref2VA → PDD 多参考 8步**。
2. 打开中文导演台的高级参数区，找到 **「H3 内存优化（仅 PDD 8步）」**。
3. 将 **「关闭（生产默认）」** 切换为 **「开启（高级可选）」**，确认状态提示显示当前已开启。
4. 根据自己的实际资源情况执行生成；以后加载其他工作流或切换模式时，重新核对当前设置，不必永久保持开启。

## 为什么值得尝试

作者在本机实际生成时观察到：**开启后首步采样准备明显加快，磁盘读取/交换压力减轻**，并报告持续使用稳定。可能的解释是不同模型内存策略减少了采样准备阶段反复的数据迁移，但**仅凭这一使用反馈不能判定所有磁盘 I/O 的具体根因或保证磁盘读写归零**。

首段/首步等待、系统内存、显存、磁盘缓存、模型大小、后台程序及冷启动/热启动状态，都会影响加速幅度。有的机器可能无明显收益，甚至遇到内存压力或其他兼容问题。

**推荐原则：先确认当前 PDD8 路线，再手动开启比较；不自动开启、不静默改变用户的选择。**

## 对比与排查建议

- 对比时使用相同模型、相同参考图、分辨率、帧数、步数及相近的系统负载。
- 把「首次模型加载」「第一步开始前等待」「第一步采样耗时」「整段总耗时」分开记录；不要把其中一项变快当成全流程提速。
- 使用系统磁盘活动、RAM占用和GPU显存监控交叉检查，避免仅凭进度条推测实际磁盘读取。
- 若开启后出现内存不足、异常换页或速度下降，可切回「关闭」；这不是所有配置都必须启用的功能。
- 无论是否开启，本选项都**不替代**模型/节点安装、参考图输入检查、Native续接收据或视频合并配置。

## 证据边界与发布说明

- **工作流存在性与默认值：** 已在公开 `wf_05` 的节点与选择器中核对。
- **性能收益：** 项目所有者于 2026-10-14 提供本机实测反馈；本次 GitHub 文档更新未执行新的GPU A/B基准，暂不发布未经复核的加速百分比或磁盘IO减少比例。
- **当前公开预览版本：** 完整同版本六段 GPU 端到端验收与本开关的跨设备性能验证不因这条说明而自动变为 PASS；仓库的 [证据范围说明](CAPABILITIES_AND_EVIDENCE.md) 保持有效。
- 本文是**使用提醒与性能选项说明**，不修改工作流JSON、默认开关、代码、模型或既有 Release 附件。

---

## English quick reference

**H3 Memory Optimization is OFF by default** in the public `wf_05` workflow. The optional UI switch, **“H3 Memory Optimization (PDD 8-step only)”**, is intended for the **Ref2VA PDD 8-step** path, not every H3 backend.

To try it: select Ref2VA PDD 8-step, locate the H3 memory-optimization advanced control, choose **Enable (advanced/optional)**, and confirm that the current setting reads enabled. Keep or save your preferred workflow settings; the repository default remains off.

The maintainer reports stable local use, a faster initial sampling step, and noticeably less disk-reading pressure after enabling the option. **These are owner-reported observations, not a controlled public benchmark or universal performance guarantee.** Results vary by RAM/VRAM, model, loading state and configuration. Monitor memory and I/O, and switch it off if it performs worse on your machine. This documentation change does not modify the published workflow or release artifacts.
