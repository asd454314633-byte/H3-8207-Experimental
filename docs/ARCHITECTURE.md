# 实验候选的交付结构

固定公开 8197 节点源码 → 叠加公开 8207 节点副本 → 固定 ComfyUI 宿主 + GPL execution 补丁 → 用户自行提供第三方依赖与模型。

六段前端调用 Prompt Sidecar，原生接续读写 latent 与接受回执，PreBake 提供条件缓存和 TE 生命周期钩子。当前 8207 前端对故事绑定/恢复的调用比 8197 少，不能凭源码存在宣称该集成完整。

`custom_nodes/local_author` 是发布存储布局；重建时节点放在 `custom_nodes/<node>`，而不是把没有注册入口的 local_author 当作单一节点。`.disabled` 探针不启用。原始 director_runtime、模型回复、原回执与旧 Git 历史不进入公开导出。
