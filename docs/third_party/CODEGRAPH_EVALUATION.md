# CodeGraph 引入记录与隔离评估计划

> 仓库：`asd454314633-byte/H3-8207-Experimental`  
> 状态：**仅引入第三方源码引用 / 未安装 / 未启用**  
> 核对日期：2026-10-27

## 1. 来源与固定版本

| 字段 | 值 |
|---|---|
| 上游仓库 | https://github.com/colbymchenry/codegraph |
| 获取方式 | Git submodule，位于 `third_party/codegraph` |
| 固定 Release | `v1.6.2`（2026-10-03 发布） |
| 固定 Commit | `6560052a6f856855d3f71eee838fd66ccfa4285d` |
| 上游主分支 | 未跟随；不会自动滚动到最新提交 |
| 许可证 | MIT（详见子模块内 `LICENSE`） |
| 引入目的 | 预留 Codex / Claude 的代码结构检索、调用链分析和修改影响分析 A/B 测试 |

此操作没有复制第三方代码进入 H3 主工程，没有引用其 Python/JS 依赖，更没有向 Codex、Claude 或 ComfyUI 注册 MCP。仅在 Git 仓库中记录对上游固定 Commit 的引用。正式下载源码需要显式初始化子模块。

## 2. 拉取与验源（Windows PowerShell）

```powershell
git clone https://github.com/asd454314633-byte/H3-8207-Experimental.git
cd H3-8207-Experimental
git submodule update --init third_party/codegraph

$expected = "6560052a6f856855d3f71eee838fd66ccfa4285d"
$actual = (git -C third_party/codegraph rev-parse HEAD).Trim()
if ($actual -ne $expected) { throw "CodeGraph 版本校验失败: $actual" }
git -C third_party/codegraph describe --tags --exact-match
```

子模块自身的 `LICENSE`、`README.md` 和源码继续由上游 Git 历史提供。更新时须先审查新 Release/Issues/Windows 兼容性，然后**单独提交 Gitlink 更新**，不得自动跟随 `main`。

## 3. 与生产环境隔离

- 不修改 8207 的 ComfyUI 工作流、Python 服务、模型、启动器、环境变量、Agent 配置或端口。
- 不运行上游 `install.ps1`、`codegraph install`、`codegraph init`，不自动创建索引。
- 不触碰 8197 的 `H3-Chinese-Director`，不改任何历史 Release、tag 或资产包。
- 任何后续测试均在独立、可删除的本地副本中执行，测试前备份并记录现有 Codex/Claude MCP 配置；不得让安装器修改生产级或全局 Agent 配置。
- CodeGraph 运行时索引目录 `.codegraph/` 已列入本仓库 `.gitignore`，测试产物和遥测不应提交。

## 4. 待做 A/B 实测（此阶段**未执行**）

选三种匿名化、可复现的真实问题：①跨文件函数调用链；②改一个模块后的影响范围；③旧故障定位。对同一固定代码快照、模型、推理档位和提示词，分别运行未启用 CodeGraph 与启用 CodeGraph 的独立会话。

采集：实际 wall time、工具调用量、输入/输出 Token、上下文峰值、正确率、错误调用链接比例、Windows MCP 稳定性、安装/卸载副作用。无客户端可信计量时对应项标记“不可测”，禁止从厂商宣传外推。

**验收门槛**：能清楚复现代码定位结果，索引过程不损坏源码，不干扰在运服务，卸载后原配置可恢复；达到这些条件才讨论正式接入。

## 5. 来源与局限

- 上游 GitHub：https://github.com/colbymchenry/codegraph
- 对应 Release：https://github.com/colbymchenry/codegraph/releases/tag/v1.6.2
- 上游使用文档：https://colbymchenry.github.io/codegraph/getting-started/quickstart/
- 对外宣称的节省 Token/调用次数属于其特定基准，不代表在 H3 项目或 Codex 订阅额度中的真实收益；未完成本地测试前统一标记**未验证**。

机器可读来源清单：[CODEGRAPH_SOURCE.json](./CODEGRAPH_SOURCE.json)。
