# CodeGraph v1.6.2 本机部署与验收（Pilot）

本目录归档 2026-10-27 在 `D:\H3导演台项目目录\_experiments\CODEGRAPH_PILOT_20261027` 完成的
CodeGraph v1.6.2 隔离部署与验收产物。验收判定：**DEPLOY=PASS / SAFETY=PASS / ROLLBACK=PASS / BENCHMARK=INCONCLUSIVE**。

## 内容

- `DEPLOY_REPORT.md` — 完整验收报告（阶段 A–E、回滚、复核整改、8 项必需输出、4 项判定）。
- `codegraph.json` — 索引排除配置（排除 third_party / 二进制 / 模型 / 缓存 / 输出 / 日志）。
- `config.codegraph.sample.toml` — **参考样例（不自动生效）**：原项目级 Codex MCP 配置的样例化版本。2026-10-27 复核后，已从仓库根自动加载路径 `.codex/config.toml` 移出，转为本参考文件，使正式仓库不再自动启动 CodeGraph（见报告第九节）。实验目录保留未删。
- `mcp_probe_client.js` — 确定性 stdio 探针：直连 `serve --mcp`，验证 8 工具真实返回。
- `ab_test.sh` — A/B 效益测试（CodeGraph 关/开 各 3 类任务）。
- `multi_session_test.sh` — 多会话并发稳定性测试。
- `rollback_codegraph_pilot.ps1` — 一键回滚脚本（路径隔离，已破坏性执行验证）。

## 关键坑位

1. **MCP 默认仅暴露 `codegraph_explore`**：源码 `lib/dist/mcp/tools.js:1574` 定义
   `DEFAULT_MCP_TOOLS = new Set(['explore'])`。须设环境变量
   `CODEGRAPH_MCP_TOOLS=search,callers,callees,impact,node,explore,status,files`
   （该 allowlist 会**替换**默认集合，故必须含 `explore`）才能启用全部 8 工具。
2. **中文路径直连 MCP 探针不可行**：`.NET Process.Start()` 无法设置含中文的
   `WorkingDirectory`。验证改用 `codex exec -C`（内部切目录）或 Node 直连子进程（`mcp_probe_client.js`）。
3. **小规模仓库收益不显**：194 文件下 A/B 显示启用 CodeGraph 未降 token/耗时，反而增 token。
   收益随仓库规模上升，建议大仓库复测。

## 重新部署

> ⚠️ 安全提醒：仓库根**不再保留**自动加载的 `.codex/config.toml`。本目录的
> `config.codegraph.sample.toml` 仅是参考样例，需手动复制到目标仓库才会生效。

```powershell
# 1. 下载并校验官方 win32-x64 包（SHA256=7455E817EE8032666867A1BADEB799B8A884C5F4FEA9B444E088A02069B6DEEA）
# 2. 解压到 codegraph-bin/codegraph-win32-x64/
# 3. 在目标仓库根执行：codegraph init -y   （生成 .codegraph/ 索引）
# 4. 将 codegraph_pilot/config.codegraph.sample.toml 复制为目标仓库的 .codex/config.toml
#    （并改其中的绝对路径为你本机/安装目录）
# 5. codex exec -C <目标仓库> 即可使用 codegraph_* MCP 工具
```

## 回滚

```powershell
powershell -ExecutionPolicy Bypass -File rollback_codegraph_pilot.ps1
```

仅删除 `CODEGRAPH_PILOT_20261027` 实验目录、停 pilot codegraph 进程、移除全局 config 中的
pilot trust 条目；不触碰生产 ComfyUI / 生产 MCP。
