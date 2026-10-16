# 2026-10-17 六段关键帧能力更新

本次更新把关键帧图片送入当前段最终BasicGuider conditioning，并为六张提示词卡片增加独立、默认关闭的设置。官方 `MiniMaxH3AddGuide` 在CPU图编译中使用实际图片与帧号；965旧时间线保持旁路，避免执行环路。Clean Rebase的自动frame0接续Guide与用户中段Guide共存。

## 公开验收

| 项目 | 结果 | 范围 |
|---|---|---|
| GUIDE_ROUTING | PASS | 56项CPU检查、11项PreBake回归；243/362完整Managed图通过服务端validate_prompt；队列未提交 |
| 六段默认关闭 | PASS | 12个旧缓存/Fallback编译图与修复前逐图一致 |
| 帧位换算 | PASS | 倒数88帧：243→155、362→274；Native可见24→模型63；Clean Rebase不加39 |
| 前端隔离和恢复 | PASS | 实际页面上传、工作流保存/刷新/载入、失败快照恢复夹具均未串段 |
| GUIDE_VISUAL_GPU | HOLD | GPU提交0；需用户亲自生成录屏并确认视觉关键帧效果 |

这是8207本机源码与前端CPU证据，不代表公开发行包GPU验收，也不代替长歌曲、跨组或其他功能的原有验收。