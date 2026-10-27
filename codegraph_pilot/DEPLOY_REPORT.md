# CodeGraph v1.6.2 本机部署与验收报告

- 任务级别：P1
- 执行环境：Windows 10.0.26300.0 / AMD64 / PowerShell 7.6.6 / Codex CLI 0.160.0
- 实验目录：`D:\H3导演台项目目录\_experiments\CODEGRAPH_PILOT_20261027`
- 日期：2026-10-27
- 上游固定版本：v1.6.2 / commit `6560052a6f856855d3f71eee838fd66ccfa4285d`（colbymchenry/codegraph）
- 官方二进制 SHA256：`7455E817EE8032666867A1BADEB799B8A884C5F4FEA9B444E088A02069B6DEEA`（已校验通过）

## 判定总览

| 判定 | 状态 | 说明 |
|---|---|---|
| DEPLOY    | **PASS** | 安装+版本(1.6.2)+索引(194文件/4720节点/12535边)+MCP 真实调用(8 工具全部实测返回真实数据) |
| SAFETY    | **PASS** | 全局 `~/.codex/config.toml` 未写入 codegraph MCP；生产 ComfyUI / 生产 MCP(comfyui/browseros-neo/node_repl) 全程未改动、未重启 |
| ROLLBACK  | **PASS** | `rollback_codegraph_pilot.ps1` 路径隔离、仅停 pilot 进程、删实验目录、移除 pilot trust 条目、校验全局/生产完好（已破坏性执行验证） |
| BENCHMARK | **INCONCLUSIVE** | 功能正确、多会话稳定；但本 194 文件小规模仓库下，启用 CodeGraph 未显现 token/耗时净收益，反而增加 token（详见阶段 E） |

---

## 一、阶段 A：环境审计与隔离

- OS/架构：Windows 10.0.26300.0 / AMD64（匹配 win32-x64 包）✓
- PowerShell：7.6.6 Core ✓；Codex CLI `codex-cli 0.160.0`，支持 `mcp` 子命令 ✓
- codegraph：PATH 无；文件系统无残留（干净基线）✓
- 网络：github.com 与发行包 URL 均 HTTP 200 ✓
- 远程仓库：`asd454314633-byte/H3-8207-Experimental` → `main` = `917c89bed74f1ec335fe542112696f07c01d096d` 可达；`.gitmodules` 指向 `colbymchenry/codegraph.git`
- 隔离克隆：已建；子模块 `third_party/codegraph` HEAD = `6560052a6f856855d3f71eee838fd66ccfa4285d`（与固定 commit 一致）✓
- 生产进程基线（全程未触碰）：claude / codex / 多个 ComfyUI 实例（含 H3_V26_Lab venv、H3_中文提示词编译器 8210 等）、comfyui-router / comfyui-mcp 生产 MCP 进程。

## 二、阶段 B：安装与版本校验

- 下载包：`downloads/codegraph-win32-x64.zip` = 54,260,850 字节
- SHA256：`7455E817EE8032666867A1BADEB799B8A884C5F4FEA9B444E088A02069B6DEEA` == 官方值 ✓
- 解压至：`codegraph-bin/codegraph-win32-x64/`（根 `node.exe` 92MB + `lib/dist/bin/codegraph.js`）
- CLI 入口：`bin/codegraph.cmd`（包装 `node.exe --liftoff-only --disable-warning=ExperimentalWarning lib/dist/bin/codegraph.js`）
- 版本检查（绝对路径）：`codegraph.cmd --version` → `1.6.2` ✓
- 未修改系统 PATH；未执行 upgrade（自动升级已禁用：`CODEGRAPH_NO_UPDATE_CHECK=1`）
- 遥测：`codegraph telemetry off` → disabled；`DO_NOT_TRACK=1` 生效

## 三、阶段 C：代码索引（仅独立副本）

- `codegraph.json` 排除：`third_party/**`、二进制资产、模型/缓存/输出/日志等。
- `codegraph init -y`：索引 **194 文件 / 4,720 节点 / 12,535 边**，耗时 1.1s（总 4.9s）。
- SQLite：`.codegraph/codegraph.db` ≈ 20.3 MB（node:sqlite / WAL / state=complete / Journal mode: wal，并发读安全）。
- 节点类型：function 1441 / import 1087 / method 893 / variable 680 / file 192 / class 246 / constant 181；语言 javascript 38 / python 154 / yaml 2。
- 真实查询演示（CLI）：
  - `query Director` → `Director` 类位于 `custom_nodes/local_author/H3_Prompt_Sidecar/director_engine.py:74`。
  - `explore receipt recovery resume` → 跨 5 文件定位 98 符号（RecoveryEngine / recovery / resume_unstarted / resumen / receipt）。
  - `impact authorize_recovery` / `callers recovery` → 返回真实跨文件影响与调用关系。
- 增量同步：修改 1 文件 → `sync` 报告 "Modified: 1 → 16 nodes in 471ms"（4720→4721）；`git checkout` 还原后 `sync` → "Modified: 1 → 15 nodes in 469ms"（精确回到 4720）✓

## 四、阶段 D：接入 Codex MCP（真实调用）

### 4.1 配置（项目级，不碰全局）
- `H3-8207-Experimental/.codex/config.toml`：`mcp_servers.codegraph` 用已验收 CLI 绝对路径 `node.exe ...\codegraph.js serve --mcp` + `DO_NOT_TRACK=1` / `CODEGRAPH_NO_UPDATE_CHECK=1`。
- **关键修正**：CodeGraph v1.6.2 源码 `lib/dist/mcp/tools.js:1574` 定义 `DEFAULT_MCP_TOOLS = new Set(['explore'])`——即 MCP 默认**仅暴露 `codegraph_explore`**，`search/callers/callees/impact/node/status/files` 被默认隐藏。必须通过环境变量 `CODEGRAPH_MCP_TOOLS=search,callers,callees,impact,node,explore,status,files`（该 allowlist 会**替换**默认集合，故必须含 explore）重新启用全部 8 个工具。本部署已写入该 env。
- 全局 `~/.codex/config.toml` 未写入任何 codegraph MCP 配置；仅有 `codex exec -C` 自动写入的良性 `[projects.'...codegraph_pilot_20261027...'] trust_level` 簿记条目（回滚时移除）。
- 生产 MCP（comfyui / browseros-neo / node_repl）在全局 config 中完好未改 ✓

### 4.2 真实 MCP 调用验证（确定性 stdio 探针，非模型依赖）
- 脚本 `mcp_probe_client.js` 直接 spawn `serve --mcp`，完成 JSON-RPC 握手，`tools/list` 返回 **8 个工具**，并实际调用：
  - `codegraph_search("authorize_recovery")` → `tools/startup_compatibility/h3_action_director/execution_graph.py:264` ✓
  - `codegraph_callers("recovery")` → 调用者 `story`（`custom_nodes/local_author/h3_conditioning_prebake/production.py:120`）✓ 真实跨文件调用关系
  - `codegraph_impact("authorize_recovery")` → 影响 1 个符号（execution_graph.py:264）✓ 真实影响分析
  - `codegraph_status` → 194 文件 / 4720 节点 / 12535 边 / 19.36 MB / WAL / node:sqlite ✓
  - `codegraph_files` → 194 文件树 ✓
  - 探针总耗时 3934ms（含 server 启动 + 5 次工具调用）。
- `codex exec -C $repo` 真实会话亦验证：`codegraph_explore` / `codegraph_search` / `codegraph_node` / `codegraph_callers` / `codegraph_callees` 均被模型成功调用并返真实数据（logs/codex_exec_*.log）。

### 4.3 稳定性验证（阶段 D 要求 5、6）
- **重开会话仍连接**：新建 `codex exec` 会话（全新进程）成功连接 codegraph MCP 并返回正确符号路径（execution_graph.py:264 / adaptive_bridge.py:65，与 CLI 一致）✓
- **多会话无锁争用**：并发启动 2 个 `codex exec` 会话（logs/multi_A.log / multi_B.log），两者均 exit 0、均连接、B 实际调用 explore+search+callers+callees（started→completed），**无 lock 错误、无索引停滞、无进程异常** ✓（符合 status 报告 "Journal mode: wal (concurrent reads safe)"）。

> 阶段 D 全部 6 项要求（查询关键函数 / 跨文件调用关系 / 修改影响范围 / 改副本后索引同步 / 重开会话连接 / 多会话无锁）均验证通过。

## 五、阶段 E：A/B 效益测试

### 5.1 方法
相同代码快照 / 模型(gpt-6.1-sol) / 推理档位(low) / 问题，三类任务：
1. 跨文件调用链定位（`recovery` 的 callers/callees）
2. 续接/回执/恢复逻辑排查
3. 改动 `authorize_recovery` 的影响范围

- 变体 A（OFF）：隔离副本 `repo_nocg`（无 `.codex`，`codex exec --skip-git-repo-check`，无 codegraph MCP，agent 用 Grep/Read/ripgrep）。
- 变体 B（ON）：原仓库（项目级 `.codex` 含 codegraph MCP，prompt 指示优先使用 codegraph 工具）。
- 指标：耗时(s) / tokens / codegraph 工具事件 / rg·Read 事件 / 准确性。

### 5.2 结果

| 任务 | 变体 | 耗时 | tokens | codegraph事件 | rg/Read事件 | 准确性 |
|---|---|---|---|---|---|---|
| 1 调用链 | A(off) | 49s | 23,002 | 0 | 5 | 正确（caller=story@production.py:120；callees=snapshot_path/root/TaskSnapshot.load/file_sha/verify_native/RecoveryEngine/…） |
| 1 调用链 | B(on)  | 38s | 41,778 | 4 | 2 | 正确（同 A，经 codegraph_callers/callees/explore） |
| 2 恢复逻辑 | A(off) | 99s | 58,495 | 0 | 9 | 正确（全面覆盖 NativeContinuation/PreBake/six_resume/attempt_lifecycle/adaptive_v1/H3_LongSong/V28 等） |
| 2 恢复逻辑 | B(on)  | 103s| 85,619 | 19| 1 | 正确（同 A，经 codegraph 工具） |
| 3 影响范围 | A(off) | 52s | 10,652 | 0 | 8 | 正确（结论：无调用方/消费者，影响限于函数自身契约+抛出的 GraphCompatibilityError） |
| 3 影响范围 | B(on)  | 57s | 28,784 | 5 | 3 | 正确（同 A，经 codegraph_impact depth=5 仅返回函数自身+文本补查） |

### 5.3 结论
- **正确性**：两种变体在三类任务上均得出正确结论；CodeGraph 未提升正确性（小库下 rg+Read 已足够准确）。
- **效率**：启用 CodeGraph 后 token 消耗更高（1.8× / 1.5× / 2.7×），耗时未稳定下降（任务1 略快 38 vs 49s；任务2/3 略慢）。原因：codegraph 工具返回"逐字源码"体量大于定向 rg+Read，对小库不划算。
- **判定 BENCHMARK=INCONCLUSIVE**：功能正确、多会话稳定均通过；但本 194 文件仓库未显现 token/耗时净收益。这与 CodeGraph 自身设计说明一致（收益随仓库规模上升；小库 rg 已高效）。更大仓库可能显现收益，需另行 A/B。

## 六、回滚（ROLLBACK=PASS，已破坏性执行验证）

- 脚本：`rollback_codegraph_pilot.ps1`（路径隔离：仅当路径匹配 `CODEGRAPH_PILOT_20261027$` 才允许删除）。
- 范围：① 仅停命令行/路径匹配实验目录的 codegraph 进程；② 删实验目录（索引+临时安装+项目级 `.codex`）；③ 移除全局 config 中 pilot trust 条目；④ 校验 `codex --version` 与全局 `[mcp_servers.comfyui]` 完好。
- 执行结果：实验目录已删除；全局 config 的 pilot trust 条目已移除；生产 MCP 配置与 Codex 原有功能不受影响。**所有部署可回滚，且已实测通过。**
- 注：回滚后如需恢复部署，从 GitHub 提交（见第八节链接）重新克隆实验目录并重跑阶段 B/C/D 即可。

## 七、遗留问题与限制

1. **MCP 默认仅暴露 explore**：CodeGraph v1.6.2 默认 `DEFAULT_MCP_TOOLS=['explore']`，须显式设 `CODEGRAPH_MCP_TOOLS` 才能用全 8 工具。已写入项目级配置。
2. **小规模仓库收益不显**：194 文件下 A/B 未显现 token/耗时收益。建议在大仓库复测。
3. **中文路径直连 MCP 探针不可行**：`.NET Process.Start()` 无法设置含中文的 WorkingDirectory，故 stdio 自写探针失败；改用 `codex exec -C`（内部 `-C` 切目录规避）与 Node 直连子进程探针（mcp_probe_client.js）验证。
4. **索引排除 third_party**：第三方源码被排除（否则数千文件），索引聚焦本仓库业务代码。仓库内无模型权重文件（已扫描 safetensors/gguf/ckpt/pt/onnx 均无）。

## 八、必须输出项

1. **安装位置与版本**：`D:\H3导演台项目目录\_experiments\CODEGRAPH_PILOT_20261027\codegraph-bin\codegraph-win32-x64\`（node.exe + lib/dist/bin/codegraph.js），版本 **1.6.2**（SHA256 校验通过）。
2. **Codex MCP 是否真正可用**：**是**。经 `codex exec` 真实调用 + 确定性 stdio 探针双重验证；工具集含 `codegraph_search/callers/callees/impact/node/explore/status/files` 共 8 个，均返回真实跨文件数据。
3. **实际索引规模与构建耗时**：194 文件 / 4720 节点 / 12535 边，构建 1.1s；增量同步 471ms / 469ms。
4. **多会话稳定性**：通过。2 并发会话均连接、无锁争用、无索引停滞、无进程异常（WAL 并发读安全）。
5. **A/B 数据与收益判断**：见第五节。正确性两者均正确；启用 CodeGraph 未降 token/耗时，BENCHMARK=INCONCLUSIVE。
6. **遗留问题与限制**：见第七节。
7. **一键回滚**：`rollback_codegraph_pilot.ps1`（已实测 PASS）。
8. **GitHub 提交链接**：见下方「提交与链接」。

## 提交与链接

- 仓库：`asd454314633-byte/H3-8207-Experimental`
- 本次提交：将 pilot 产物（`codegraph_pilot/` 目录：DEPLOY_REPORT.md、codegraph.json、codex 配置样例、mcp_probe_client.js、ab_test.sh、multi_session_test.sh、rollback_codegraph_pilot.ps1、README）纳入版本控制并推送。
- 提交链接：`<GitHub commit URL — 由 git push 输出填入>`
