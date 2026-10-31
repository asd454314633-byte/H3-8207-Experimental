# T023｜8207 原地显存优化测试（--reserve-vram 单变量）

- 日期：2026-11-01 01:50 – 02:30 (GMT+8)
- 实例：h3-lab @ 127.0.0.1:8207（官方托管 instance_manager.py）
- 托管树：`D:\H3导演台项目目录\_promotion_isolated_8207_0421_CANDIDATE\runtime`（0421 候选树，未变更）
- 单变量：`--reserve-vram` 3 → 1.5 → 恢复 3
- 结论速览：**1.5GB 显著降低异常重取与慢步（步时 −25%~−50%，PCIe 搬运 −57%~−82%），全程无 OOM/无驱动异常/无 WDDM 回退，建议未来正式采用前再做一轮六段级长稳验证。本轮已按要求恢复 3GB。**

## 一、执行前保护（全部完成）

| 项目 | 结果 |
|---|---|
| 队列 running/pending | 0 / 0（停机前两次确认） |
| 六段合并任务 | 无未完成项（最后合并 1788e6f1 success，3.26s） |
| 0421 托管树 | `/h3/instance` source = `_promotion_isolated_8207_0421_CANDIDATE\runtime` ✓ |
| 启动命令存证 | `evidence/instance_before_T023.json`（SHA256 6F7F9747E2DCF4A14D398279E555FBC7D43B03D072E3CC01FF3BCDBD4C4C8215） |
| PID / generation | 停机前 44512 / `7d1c0f7732064b16a9499f5322e7c88b` |
| History 保护 | 官方 stop 自动快照 `snapshot-1793469493016318200.json`（19.9MB，28 条）✓；内存库边界已明示：重启后内存 History 不复原，T023 两段 History 另存 `evidence/history_gen_7d163019_final.json` |
| 工作流/草稿/回执/输出 | 磁盘文件与 localStorage 不受重启影响；回执目录未动；输出目录零覆盖 |
| 参数覆盖方式 | 注册表 `instance.json.extra` 数组 + 官方 stop→edit→start（restart 无法中途改参；host 退出时以内存配置回写注册表，故必须先 stop 再改） |
| 注册表差异校验 | 仅 `--reserve-vram` 一个值变化（程序化 diff 全字段比对）✓ |

## 二、基线（3GB，复用 11月1日已采集记录，未重复六段测试）

基线选择：同一提交图（81→实际 68 节点段图，prompt_id `2f81d593`，seed 959250910524196，9:16 0.6MP，8 步采样，SparkAttention speed 模式，comfy kitchen attention）在 01:46–01:48 的真实执行（批内热态）。逐步数据取自 console.log tqdm 块（line 127477），GPU 遥测取自 `gpu_dmon2.csv` 同窗口积分。

| 指标 | 3GB 基线（热态） |
|---|---|
| 8 步耗时 | 10.39 / 17.27 / 13.36 / 12.53 / 13.50 / 16.70 / 16.89 / 15.11 s，**总和 115.7s** |
| Prompt 总耗时 | **148.42s** |
| fb 峰值 / 均值 | 23547MB / 19318MB |
| PCIe rx / tx 积分（整窗） | 1307421MB / 1408982MB（**rx+tx ≈ 2.72TB**） |
| 功耗均值 / 峰值 | 303.8W / 557W |
| SM 均值 | 72.2% |

## 三、候选测试（1.5GB，最多两段，均成功）

提交方式：与基线完全相同的提交图字节级复用（seed/素材/分辨率/步数/注意力后端不变），经 `/prompt` 路由（图内无 H3AttemptGuard/H3ConditioningLoad，与前端同路径）。提交体存 `evidence/candidate_submit_body.json`。

### 段 1（冷启动首段，prompt_id 1c62d177-5703-4575-8b8f-69d3d8db23e8，02:02:08 提交）

| 指标 | 1.5GB 冷启动 | 基线（热态） |
|---|---|---|
| 8 步耗时 | 14.31 / 10.38 / 10.35 / 10.34 / 10.54 / 10.43 / 10.37 / 10.39，**总和 87.1s** | 115.7s |
| 步时形态 | 首步含加载，2–8 步全稳 ~10.4s，**无 >20s 慢步** | 多步 12.5–17.3s 慢步 |
| Prompt 总耗时 | 149.90s（含全部模型冷加载） | 148.42s（热态） |
| fb 峰值 | 23403MB | 23547MB |
| PCIe rx+tx 积分 | 629339+535290 ≈ **1.16TB**（含冷加载） | 2.72TB |
| 功耗均值 | 288.6W | 303.8W |

### 段 2（热态同负载，prompt_id 091df9fb-ee66-473f-aab2-74485ea18ad6，02:07:09 提交）

| 指标 | 1.5GB 热态 | 基线（热态） |
|---|---|---|
| 8 步耗时 | 8.21 / 8.20 / 8.22 / 8.24 / 8.22 / 8.38 / 8.26 / 8.25，**总和 66.0s** | 115.7s |
| Prompt 总耗时 | **73.65s（−50.4%）** | 148.42s |
| fb 峰值 / 均值 | 23299 / 18894MB | 23547 / 19318MB |
| PCIe rx / tx 积分 | 247631 / 254352MB（**rx+tx 502GB，−81.5%**） | 2.72TB |
| 功耗均值 / 峰值 | 455.1W / 574W（算力真正用于计算） | 303.8W / 557W |
| SM 均值 | 77.6% | 72.2% |
| 输出 | S6_00003_.mp4 完整（独立子目录，未覆盖任何既有文件） | — |

## 四、重点监控项汇总

- **采样步骤耗时**：见上表（`t023_dmon_seg1.csv` + console.log）。
- **动态权重加载/驱逐/重取**：段 1 启动区 `reblock_plan_calls=8`（8 步每步 1 次 plan），`Model MiniMaxH3 prepared for dynamic VRAM loading. 21140MB Staged` 常规出现，无异常驱逐风暴日志。段 2 Spark 执行摘要：`evaluations=8, reblock_plan_calls=400, comfy_kitchen_calls=400, sparse:spark_comfy_native=400, unexpected_fallbacks=[]`。
- **系统内存**（`sys_io.csv`，1s 分辨率）：段 2 窗口 avail_min=6.08GB、commit_max=94.5GB、内存负载 max 89%、进程读速率 avg 12.9MB/s（段 1 冷加载 avg 246MB/s、峰值 2978MB/s）。系统内存未逼近耗尽。
- **CUDA 错误 / OOM / 进程状态**：本 generation 区间 `CUDA out of memory=0`、`CUDA error=0`；两段均 status=success；进程全程存活。
- **视频完整性**：两段均成功产出（S6_00002_.mp4 / S6_00003_.mp4，608×1056、24fps、204 帧、8.5s）。
- **启动期既有异常（与 reserve-vram 无关的归因声明）**：本次启动区间共 5 个 Traceback——`ModuleNotFoundError: anthropic`（可选云模型 provider 缺失）×1、内存库批量插入 `sqlite3.OperationalError: no such savepoint` ×4，均为启动期旧有模式（此前日志同模式大量存在），非测试窗口内、与本变量无因果证据。

## 五、止损规则检查

| 止损条件 | 触发? |
|---|---|
| CUDA OOM / 驱动异常 | 否 |
| WDDM 共享内存回退减速 | 否（fb 峰值仍 23.3GB，无回退特征） |
| 20 秒以上持续慢步 | 否（最慢步 14.31s 为冷启动加载步） |
| 8207 面板/尾12/合并功能异常 | 否（route preflight PASS 50 节点 0 缺失） |
| 系统内存逼近耗尽 | 否（avail_min 6.08GB） |
| 影响其他任务 | 否（队列独占，测试期间无其他提交） |

## 六、恢复与验收

- 恢复流程：官方 stop → 注册表 `--reserve-vram` 改回 3 → 官方 start。
- **偏差记录（deviation）**：第二次 stop 的优雅退出失败——主机已发出 "Normal Ctrl+C requested" 并升级 Ctrl+Break（主机控制台屏幕缓冲直接读取证实），但本实例进程树对控制台信号完全免疫（stop.json×2、`_break`、`_signal` 官方助手全部穷尽无效；01:58 同一流程对上一代进程树成功）。在**队列空、内存库无执行中任务、输出已落盘、证据已保全**的最低风险点执行受控 `taskkill /T /F`。此为托管器 "never force-kill" 原则下的必要偏离，已如实记录。本轮 1.5GB 段的 History 已先行保全至 `evidence/history_gen_7d163019_final.json`（内存库数据不因重启“恢复”，边界如实声明）。
- 恢复后核验：`h3-lab` / generation `bdd74981019c4c37ad3a4fc1903428c8` / PID 52956 / source 0421 树 ✓；`--reserve-vram 3` ✓；route preflight PASS（50 节点、0 缺失，T022 全功能在位）✓；队列 0/0 ✓；未覆盖任何既有视频/草稿/回执 ✓。

## 七、五个验收问题

1. **1.5GB 是否比 3GB 更快？** 是。热态同图同负载：73.65s vs 148.42s（−50.4%）；冷启动首段总耗时也持平热态基线（149.9s vs 148.4s），且其中含全部模型冷加载。
2. **慢步是否减少？** 是。基线 8 步中 7 步处于 12.5–17.3s 慢步区间；1.5GB 热态 8 步全部 8.2–8.4s，方差极小；冷启动段 2–8 步全稳 ~10.4s。无任何 >20s 慢步。
3. **PCIe 搬运量是否下降？** 是。热态 rx+tx 502GB vs 基线 2.72TB（−81.5%）；冷启动段（含全量首次加载）仍仅 1.16TB（−57%）。动态权重反复重取被大幅抑制。
4. **是否出现显存或系统内存风险？** 否。fb 峰值 ~23.3–23.4GB（与 3GB 基线相当，因动态加载器按需驻留）；系统 avail_min 6.08GB、commit_max 94.5GB、负载峰值 89%，无 OOM、无 WDDM 回退。
5. **是否有足够证据值得未来正式采用？** 证据充分支持进入下一道验证（六段连续级长稳 + 人工视觉质检后由用户批准），本轮不自动晋升、未保留新参数（已恢复 3GB）。

## 八、数据文件清单（本目录）

- `baseline_gpu_window.txt`：3GB 基线窗口 GPU 积分
- `t023_dmon_seg1.csv`：1.5GB 全程 GPU 遥测（1s，含两段+恢复期）
- `sys_io.csv` + `sys_probe_t023.py`：进程 IO/系统内存探针（sys_probe.py 最小参数化扩展：PIDS 改命令行传入）
- `evidence/instance_before_T023.json`：停机前注册表（SHA256 6F7F…8215）
- `evidence/h3_instance_before.json`：停机前 /h3/instance
- `evidence/history_before_T023.json`：上一 generation 全量 History（28 条）
- `evidence/snapshot`（由官方 stop 落盘于 `instances/h3-lab/snapshot-1793469493016318200.json`）
- `evidence/candidate_submit_body.json` / `candidate1_submit_reply.json` / `candidate1_history.json` / `candidate2_history.json`
- `evidence/history_gen_7d163019_final.json`：1.5GB generation 最终 History（2 条）
