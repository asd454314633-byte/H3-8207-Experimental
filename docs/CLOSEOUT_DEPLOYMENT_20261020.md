# 2026-10-20 部署、恢复与验收边界

本轮针对隔离的 H3 8207 V29。正式8197/8193工作流、既有模型、素材及历史发布保持独立。部署接收方仍须在自己的隔离环境验收，不能直接使用本机运行结论替代。

主工作流是 `workflows/current/h3_8207_wf_05.json`，其它11份是独立图像工具。主工作流保留实际验收画布的181节点、218链接及子图接口，清除了本机任务绑定、角色素材、歌曲路径、缓存身份和历史视频；完整歌曲、跨组开关及六个关键帧默认关闭。先选择自己的合法参考和模型，在独立8210中登记真实角色，再输入六段提示词。

将 `custom_nodes/local_author` 下实际需要的节点包部署到隔离 ComfyUI 的 `custom_nodes`。按原模型与第三方版本锁准备依赖，保持上游许可证。需要修改宿主时先备份，使用 `runtime_patches` 中明示的版本门；不向生产实例传播实验补丁。独立可见控制台必须显示端口及实时日志。

公开的 `h3_conditioning_prebake/model_registry.json` 是无私有路径、无信任哈希的配置模板，不能直接当作已经冻结的本机模型注册表。服务停止时用 `scripts/setup/freeze_model_registry.py --registry <部署节点包的model_registry.json> --model h3=<H3权重绝对路径> --model te=<编码器绝对路径> --model video_vae=<视频VAE绝对路径> --model audio_vae=<音频VAE绝对路径>` 生成自己的四角色注册表。选择的文件名须与工作流实际加载器一致；工具不会猜测替代模型，逐文件完整计算 SHA256、核对文件在读取期间未变化，并备份旧注册表。不要把接收方生成的注册表或模型再提交到公共仓库。

`services/h3_compiler8210` 提供冻结编译器必要源码及依赖版本记录，不包含角色工程、翻译模型和历史留档。按其 README 部署。8207 进程应设置 `H3_8210_PID_FILE` 为该独立服务的 `data/server.pid`。已有受管任务 `H3-8210-Managed` 时，应核对其动作是可见启动入口、交互用户身份及目标目录；不要沿用历史隐藏任务。可先手动运行 `Start-Visible.ps1` 并检查健康/PID一致后使用桥接，不要求必须创建计划任务。

PDD 节点中的以下四项上游数值资源不随新包分发：`adaln_basis/basis_fl2va.safetensors`、`adaln_basis/basis_ref2va.safetensors`、`partition_fingerprints/video_out_fl2va.safetensors`、`partition_fingerprints/video_out_ref2va.safetensors`。它们是必要外部依赖，不能把移除这些资源后的源码目录直接当作依赖已装齐。来源为 Jalen-Brunson/ComfyUI-MiniMax-H3-PDD-Acc，固定 commit `993566bd49a4776e3b15f617a0b207d75dccaed7`，原许可证 Apache-2.0；文件哈希见完整包 `05_来源许可及校验/20261020外部数值资源.json`。按该固定版本的上游目录获取并校验后再运行。主模型、VAE、文本编码器及加速权重同样独立获取。

恢复前先检查真实队列、History、PID/argv、GPU及会话。在途真实任务等待完成，不用重复生成证明播放器恢复。保存完整前端工作流 JSON 与任务账本，不能用 API prompt 图替代画布。跨组前驱必须来自实际 S6 的视频、latent、SHA和歌曲时间轴；不要仅按最近文件名猜测。缓存和原输出应保留，失效身份应明确拒绝。

回滚时仅恢复本轮变更清单所列源码和配置：先备份当前修复版、确认队列空闲，再恢复修复前备份并受管启动；保留生成视频、原曲、人物素材、模型、缓存、日志及历史 Release。公开包不带本机私有备份，接收方部署前必须建立自己的源码备份。

完整包离线校验使用 `python -B 07_公开源码及回归/scripts/verify/verify_closeout_package.py <完整包目录>`。在 `07_公开源码及回归` 运行相应 CPU 回归。校验通过只证明文件及来源一致；真实GPU、浏览器播放和音视频连续性仍按报告中的范围分别验收。


`tools/instance_manager.py` 是本轮实际使用的可见实例管理器。使用 `--registry <独立注册目录> create <实例ID> --source <隔离ComfyUI目录> --python <解释器> --port <实验端口> --data <数据根目录>` 注册，随后同一 `--registry` 执行 `status/start/stop`。端口被未知进程占用时不能替换；停止必须等待真实队列空闲。它会保存原始 Queue/History 快照，管理器的日志文件不是可见控制台的替代。

`tools/startup_compatibility/startup_node_preflight.py --module-root tools/startup_compatibility --route-manifest <自己的路由JSON> --endpoint <本实例URL> --report <报告路径>` 从路由JSON的 `candidate_api_graph` 读取本实例实际 API 图，对实时 object_info 做全部输出祖先兼容检查。该 API 图只作类型/连线检查，历史任务图不能直接重投。此工具不生成、不研究动作迁移。当前本机启动预检已经本地化，不再依赖另一个实验工作目录。

本机完整交付另含私有源码备份、完整 History、输入引用和本机启动入口；公开包仅含可分发源码与净化的完整画布。恢复 History 时只能恢复相同实例的真实快照，核对 prompt_id/提交图/输出和账本，不能伪造新的 SUCCESS。重建未知机器的角色、素材、模型和本机环境后，应按报告验收。
