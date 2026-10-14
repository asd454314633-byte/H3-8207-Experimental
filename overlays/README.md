# 宿主补丁

execution-prebake.patch 派生自 ComfyUI（GPL-3.0），修改日期 2026-10-13，修改用途为 8207 H3 PreBake 的 RAM headroom 与 TE 前释放。上游固定版本和应用前后 SHA256 在 config/baseline.lock.json；许可全文见 LICENSE-GPL-3.0.txt。

补丁不对其它宿主版本无条件应用。重建器先检查原文件，git apply --check 后应用，再检查结果哈希。原宿主整文件不分发。源码补丁成功不证明运行、GPU 或性能通过。

## Qwen 2.1 backport

qwen21-backport.patch is a GPL-3.0 ComfyUI feature backport for the pinned 0.36.0 source base. Upstream PR 16400 HEAD is 1b0b848d4e148cb5dae28a636b07af7f8caa5264. Nine of eleven target files match that public feature ref exactly; two files preserve the older source-base context. The explicit target is the existing experiment's ffc9d49e source content, reconstructed through the patch without requiring that local commit to be fetched. All eleven before/after SHA256 values and the patch SHA256 are in config/baseline.lock.json. No whole host repository or model weights are bundled. Exact source equality is not model-runtime acceptance.
