# Adaptive V1: workflow discovery and task-owned recovery

## 使用与已发布范围 / Usage and published scope

自适应V1已在作者8207实验实例晋升并验收，main包含与本机逐字节一致的6份恢复相关源码。冻结的v0.1.0-preview标签/附件不变；使用新功能需取main源码，旧ZIP不含本次更新。源码重建脚本会复制对应本地作者节点目录，无新增外部依赖。

Adaptive V1 is promoted and verified on the author's local 8207 experimental instance. The six listed recovery source files on main are byte-identical. The frozen v0.1.0-preview tag and assets are unchanged; use main for this update. The existing source reconstruction copies this node package; no new external dependency is introduced.

1. 在自己的独立ComfyUI环境更新这6份节点源码，按原可见启动方式重启并刷新浏览器；先检查活动队列，勿中断生成。Configure your own models/assets and preserve active jobs before updating.
2. 正常使用六段导演台，提交时保存独立TaskSnapshot；读取同一Story/Execution的恢复入口时回填原播放器。No test overlay, CPU generation firewall or synthetic History injection is installed.
3. 本机存储位于配置的output下的`h3_adaptive_v1/tasks`、`versions`、`events`；私人运行数据不应提交Git。Task snapshots are private runtime state, not public sample fixtures.

## 原理 / Design

- 根据节点元数据、输入/输出类型与实际连线发现能力；图语义签名不以节点编号、画布位置、JSON排序为身份。Metadata/types/topology drive discovery; graph identity is independent of node IDs and layout.
- INT/FLOAT/STRING/BOOLEAN与连接分别规范化，声明为FLOAT时24与24.0等价；真实参数改变形成不同语义版本。SHA256保留为文件完整性、审计和追踪证据，不能单独替代任务归属。Type-aware normalization distinguishes valid equivalence from actual changes.
- 每次提交保存独立图、声明、任务及收据快照；当前草稿更改不替换旧快照。History、prompt身份、原输出SHA及Native头/收据共同证明结果归属。Immutable snapshots isolate submitted work from later canvas edits.
- 恢复通过原`/h3/prebake/story`接口附加`adaptive_recovery`结果；前端校验Story绑定、prompt_id及段号后调用原`setSegmentVideo`。旧Native收据不被伪造或抹除。
- 不具备接续能力时保留已完成视频并返回缺失能力；播放器恢复与真实GPU成功证据分别保留。Loss of continuation does not erase a completed output.

## 开放性与限制 / Freedom and limits

核心不把九张图、六段私人剧情、24FPS或固定节点编号写成通用有效性条件。支持可声明能力的参考图数量变化、合法参数与节点调整；未知节点保留输入和连线，适配器可扩展，输出歧义需要明确映射。The generic core is not hardcoded to this acceptance movie's reference count, story or node IDs.

**不等于任意修改都能生成。** 原六段UI/PreBake规划与Native收据仍有宿主H3约束；本次没有重写所有旧规划函数或支持任意损坏图。类型、输出与接续能力仍需真实存在。任意新自定义节点组合、全部节点重编号后的完整GPU生成、FL2VA全组合、跨尺寸合并和并发编辑压力测试未获本轮GPU验收。

**Not arbitrary-workflow GPU certification.** Legacy six-panel/PreBake planning and Native receipt validation still have host-specific H3 contracts. This update does not rewrite every old planner. Missing capabilities are reported rather than disabling all validation.

无快照的历史任务不会凭“最新文件”构造新身份。旧SUCCESS收据继续走原兼容回填；历史失败任务只有经核实的原快照及真实History证据才能迁入自适应恢复。归档History需要相应SHA文件；当前桥接不自动导入其他人的私人账本，也不保证所有未留存History的旧失败任务可恢复。No fabricated legacy snapshots or automatic cross-task directory fallback.

## 已有证据 / Evidence

复用49项本机离线检查（44 Python+5 JS）、8227真实浏览器回填/播放及任务隔离验收、8207晋升后原第1段完整播放。随后六段PDD8任务有独立快照、SUCCESS收据和真实视频；见[实测报告](8207_SIX_SEGMENT_GPU_ACCEPTANCE_20261014.md)。这些原始私人样本不公开。

Public regression: `python -B tests/test_adaptive_v1_public.py` uses seven synthetic CPU-only checks, **not a replay of the private 49-test suite and not GPU testing**. Public-source SHA mapping is in [the manifest](../manifests/adaptive_v1_source_match.json). Full sanitized public-build GPU E2E remains NOT_TESTED.

## 回滚 / Rollback

先保存自己当前节点文件与工作流版本；活动队列清空并正常停止自己的可见实例后，恢复对应文件并按原入口启动/刷新。不要删除自己的输出、Native、任务快照。Private machine-specific Windows rollback scripts are not distributed.
