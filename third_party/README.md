# Third-party source dependencies

This directory contains external projects tracked separately from H3-8207 source.

## CodeGraph

- Path: `third_party/codegraph`
- Mode: Git submodule (NOT vendored / copied source)
- Upstream: https://github.com/colbymchenry/codegraph
- Pinned release: `v1.6.2` / `6560052a6f856855d3f71eee838fd66ccfa4285d`
- License: MIT (upstream `LICENSE` retained in the submodule)
- Status: Source reference only. Not installed, indexed, executed, or connected to any agent.

After cloning this repository, explicitly fetch the source:

```powershell
git submodule update --init third_party/codegraph
git -C third_party/codegraph rev-parse HEAD
```

The final command must equal `6560052a6f856855d3f71eee838fd66ccfa4285d`.

For provenance, safety boundaries, and the proposed A/B test, read
[docs/third_party/CODEGRAPH_EVALUATION.md](../docs/third_party/CODEGRAPH_EVALUATION.md).
