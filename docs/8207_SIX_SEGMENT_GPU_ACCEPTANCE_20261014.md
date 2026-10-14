# 8207六段真实GPU验收 / Local six-segment GPU acceptance

日期：2026-10-14；来源：8207实验环境，不是8197生产验收。用户确认此次六段连续成功；另只读核实了6份独立SUCCESS收据、6份原prompt_id的实时History、提交快照、Native文件头/SHA、逐段视频、自动合并任务及真实浏览器回填。此次发布整理**没有运行任何GPU任务**。

The owner confirmed this completed local run. The publication pass independently checked six exact successful histories/receipts/snapshots, Native headers/hashes, media metadata, the automatic merge history and current browser player bindings. It did not generate new media.

## 证据级别 / Evidence levels

|标识 / Identifier|状态 / Status|范围 / Scope|
|---|---|---|
|LOCAL_8207_GPU_E2E_PASS|PASS|指定本机PDD Ref2VA 8步、同分辨率六段与自动合并 / this specific local run|
|PUBLIC_SOURCE_MATCH|PASS, SIX_FILES_ONLY|自适应6文件与已晋升源码逐字节一致 / six recovery files only|
|PUBLIC_BUILD_GPU_E2E|NOT_TESTED|脱敏公开环境没有同版本GPU重跑 / sanitized public build not GPU rerun|
|FULL_RUNTIME_EQUIVALENCE|HOLD|不保证其他硬件、依赖或任意工作流 / no universal environment guarantee|

Story脱敏标识：`sha256:f4b193d2254e92a2`；Execution脱敏标识：`sha256:d5c6e1932ee0539e`。ComfyUI 0.36.0，前端 1.52.7。各段提交工作流的规范化JSON SHA256、任务脱敏标识、视频/Native/History/快照SHA索引见[机器摘要](../benchmarks/8207_six_segment_20261014.json)，不附私人图、剧情或账本。

## 六段参数与耗时 / Per-segment measurements

|段 / Segment|状态|分辨率|生成帧|保存帧|FPS|步数|实际执行秒 / execution seconds|接续|
|---|---|---|---:|---:|---:|---:|---:|---|
|01|SUCCESS|1056×608|243|243|24|8|221.264|independent|
|02|SUCCESS|1056×608|243|204|24|8|158.350|Native 39|
|03|SUCCESS|1056×608|243|204|24|8|158.218|Native 39|
|04|SUCCESS|1056×608|243|243|24|8|156.967|Clean Rebase|
|05|SUCCESS|1056×608|243|204|24|8|160.882|Native 39|
|06|SUCCESS|1056×608|243|204|24|8|160.197|Native 39|

执行计时来自各段收据的execution_start/end及单调时钟runtime_seconds，排队等待不计入；六段总执行时间 **1015.879秒**，不能当作统一硬件性能承诺。原始时间戳也在机器摘要内。

All six generated 243 frames, not the earlier planned 277-frame continuation setting. Segments 2/3/5/6 saved 204 frames after one 39-frame overlap removal. Segment 4 executed Clean Rebase with no predecessor latent input and retained 243 frames. The measured output is **54.25 seconds, not the earlier theoretical approximately 60 seconds**.

Native Provider为CORE_NATIVE_MASKED_AV；2/3/5/6的实际Prepare图有prev_latent输入，4段无此前序输入且Clean Rebase启用；各段Native文件头prompt身份、243帧及SHA与收据一致。index的trim_events含重复审计行，**不是重复裁剪证据**；本报告依据实际保存帧与合并源SHA核对，不能再盲裁39帧。

## 合并与播放器 / Merge and players

自动合并任务History及账本均SUCCESS，输入SHA与这6个已接受片段一致。合并MP4：**1056×608、24fps、1302帧、54.25秒**，视频与音频流时长均54.25秒。六段播放器均有相应视频源且readyState=4，合并播放器也已加载54.25秒文件。未重新播放六段来制作新证据；本轮只读检查了现有浏览器状态。

This is technical stream-duration alignment, **not a new perceptual A/V sync, identity, core uniqueness or seam-quality review**. Those quality verdicts are NOT_REVIEWED in this publication pass. Mixed-resolution merge remains HOLD.

## 性能与内存 / Performance and memory

- GPU显存观测峰值 / observed peak VRAM: **NOT_RECORDED**。
- GPU利用率、系统RAM峰值、CPU利用率峰值：**NOT_RECORDED**。
- 找到的hardware.csv仅覆盖先前失败单段，不能混入本次成功六段。Hardware capacity/current usage is not an execution-window peak.
- 实际PDD8模型祖先图含H3MemoryOptimization；作者既有反馈是首步准备更快、磁盘压力减轻。没有同窗口开关A/B，**不发布加速百分比**。公开工作流默认仍关闭，[原内存说明](H3_MEMORY_OPTIMIZATION.md)保留。

## 自适应恢复与限制 / Recovery and limits

此前49项离线与8227浏览器证据不重跑。8207晋升后真实History恢复、原播放器回填、10.125秒完整播放、24/24.0语义等价已PASS，旧Native收据不改写；后续本次6段各有独立快照。公开6文件来源SHA与本机一致，不附8227浮层、CPU禁用器或测试History注入。

Not tested here: fresh GPU execution of this sanitized repository, arbitrary custom-node graphs, all modes, concurrent-edit stress, cross-resolution visual equivalence, mixed-resolution auto merge, perceptual seam/character/audio quality, controlled acceleration benchmarks. This update records a local success without converting it into universal production certification.

## 公开内容 / Published data

仅发布本报告、[CSV](../benchmarks/8207_six_segment_20261014.csv)、白名单字段JSON与SHA索引。原视频、参考图、完整录屏、History、Latent、绝对路径和私人剧情留在作者本机。v0.1.0-preview标签、Release附件及8197仓库不变。
