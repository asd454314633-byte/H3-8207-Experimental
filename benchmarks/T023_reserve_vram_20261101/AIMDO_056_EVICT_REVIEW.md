# comfy-aimdo 0.5.6 预算驱逐调用点只读审查（对照 Issue #128）

审查对象：本机 8207 部署 comfy_aimdo **0.5.6**（dist-info + `__commit_id__ = g08b37eec3`）。
审查基线：上游源码 commit `08b37eec3`（已克隆至 `AIMDO_SRC_REVIEW_20261101/upstream`，检出该 commit 逐行核对）。
约束：只读研究；未编译、未替换 DLL、未注入生产进程、未升级。

## 一、部署版本与上游 commit 的对应关系

- `venv_0421/Lib/site-packages/comfy_aimdo/_version.py`：`__version__='0.5.6'`、`__commit_id__='g08b37eec3'`
- 上游 git 中 `08b37ee` = "Merge pull request #121 (null-guard-phys-free)" —— **与 Issue #128 报告者的验证版本（v0.5.6, commit 08b37eec3）完全相同**，其复现结论可直接参照本机。

## 二、五处预算驱逐调用点（0.5.6 实测 grep + 源码核对）

| # | 文件:行 | 函数 | 调用形态 | 路径性质 |
|---|---|---|---|---|
| 1 | `src/model-vbar.c:363` | `vbar_fault()` | `vbars_free(budget_deficit(0))` | **每次 VBAR 页 fault 的 stopgap**——采样期权重按需分页的主要入口 |
| 2 | `src/malloc-graph.c:426` | `create_page()` | `vbars_free(budget_deficit(MG_PAGE))` | 图录制页分配 |
| 3 | `src/vrambuf.c:112` | `vrambuf_grow()` | `vbars_free(budget_deficit(grow_to-allocated))` | VRAM 缓冲增长（HostBuffer/暂存区扩容） |
| 4 | `src/pyt-cu-plug-alloc-async.c:167` | `aimdo_cuda_malloc()` | `vbars_free(budget_deficit(size+CUDA_MALLOC_HEADROOM))` | PyTorch 每次同步分配的热路径 |
| 5 | `src/pyt-cu-plug-alloc-async.c:230` | `aimdo_cuda_malloc_async()` | `vbars_free(budget_deficit(MIN(size,malloc_async_clamp)))` | PyTorch 异步分配热路径 |

另有 OOM 兜底路径（非 #128 对象，#128 方案亦不触碰）：`malloc-graph.c:429`、`model-vbar.c:381/403`、`pyt-cu-plug-alloc-async.c:175/237`、`vrambuf.c:124` —— 均为分配失败后的有界重试，无节流亦无重复放大问题。

## 三、赤字计算与节流实证（0.5.6 源码）

1. **`budget_deficit(size)`**（`src/plat.h:149`）：
   `deficit = MAX(deficit_simple, deficit_delta) + extra_vram_headroom`
   - `deficit_simple = total_vram_usage + size + simple_vram_headroom − vram_capacity`
   - **`simple_vram_headroom` 即 `--reserve-vram` 的接线点**：本机 runtime `main.py:87` `simple_vram_headroom = int(args.reserve_vram * 1024**3)` → **预留越大，deficit_simple 越大，驱逐压力越大**（与"3GB 慢基线慢段更多、1.5GB 有改善"的观察方向一致）。
2. **`poll_budget_deficit()`**（`src-win/shmem-detect.c:109-145`）：
   - 第 118 行实证：`if (now - wddm_timestamp_last_check < 2000) return;` —— **WDDM 预算视图 2000ms 才刷新一次**。
   - `deficit_sync = total_vram_usage + WDDM_BUDGET_HEADROOM − DXGI(info.Budget)`（WDDM budget 常量定义未在本次 grep 中定位到，标注 UNVERIFIED）。
3. **机制链（#128 所述与本机代码一致）**：2000ms 窗口内，`budget_deficit()` 返回值不变；五处调用点无去抖 → 热路径（尤其 #1 `vbar_fault`，采样期每步 50 次 reblock 计划触发大量页 fault）在窗口内**每次都按同一陈旧赤字全量执行 `vbars_free`** → 驱逐→重取→再 fault→再驱逐的循环。

## 四、与本机遥测的形态对照（不作因果断言，仅形态吻合度）

| #128 报告签名 | 本机实测 | 吻合 |
|---|---|---|
| ~100% 利用率 + 远低于额定功耗 | SM 92–99% + 300–351W（快段 516–559W） | ✓ |
| VRAM 顶满 | fb 两段均 ~23.4GB | ✓ |
| 持续高访存 | 慢步 PCIe 520–703GB/步（快步 45–89GB） | ✓ |
| Windows + WDDM + 超订 | Win11 + RTX 5090 D v2 + fb 顶满 + 共享 GPU 内存 22.97GB | ✓ |
| 多 GB 级 evict-and-reload 循环 | 每步 ~550GB ≈ 百次级多 GB 循环量级 | 量级相符 |

S5 段内衰减形态（步2 峰值 777.6GB → 步4 起 81–119GB、功耗恢复 536W）与"驱逐循环清偿赤字后自愈"的机制预期一致；S1/S3 全程慢则是赤字持续未清偿的形态。段间差异（哪段慢）的触发条件**未锁定**——涉及 WDDM Budget 波动、pinned 主机缓冲计入、段间 `GPU_COLD_HOST_RETAINED` 后的重装载序列，均属候选变量，无直接读数。

## 五、验证缺口清单

1. **运行中驱逐次数/字节数**：DLL 运行期日志静默（当前 log level），VBAR 驻留 API 为进程内 → UNAVAILABLE。若未来取得 DEBUG 级日志（`src-win/shmem-detect.c` 的 `log(DEBUG, ... budget=%zu usage=%zu ...)` 行），可直接读出赤字数值与刷新频率。
2. **`WDDM_BUDGET_HEADROOM` 数值**：定义位置未定位（可能由构建注入），UNVERIFIED。
3. **本机是否处于"赤字常态为正"**：取决于 WDDM Budget（DXGI）与 pinned 计入方式，无外部只读读数。
4. **#128 修复的 5090/48GB 适配性**：报告者仅在 RTX 4070 Super 12GB 验证，未覆盖本项目硬件。

## 六、v0.6.0 现状复核（上游 main 68088de / v0.6.0 标签）

五处调用点在 v0.6.0/main 中仍为 `vbars_free(budget_deficit(...))` 原始形态（仅新增返回值检查 `if (!vbars_free(...))`，来自 PR #126 writeback 系列），**无 `stopgap_vbars_free` 限频函数** → 与用户核查一致：升级 0.6.0 不能解决 #128。**结论：暂不升级，等上游明确修复提交。**

## 七、裁定状态

- 首要根因候选：**comfy-aimdo #128 重复驱逐机制**（形态五项全吻合 + 版本精确匹配 + 代码路径实证存在）
- 判定边界：高 PCIe + 低功耗已证明"数据搬运型性能异常"，**尚不能确认具体是哪个函数在本机重复驱逐**（缺运行中驱逐计数）。
- 行动：8207 保持 `--reserve-vram 1.5`，不重启、不改工作流、不调显存参数碰运气、暂不升级 aimdo；等上游修复提交或取得更直接驱逐证据。
