#!/usr/bin/env bash
# A/B benefit test (v2): same 3 tasks, CodeGraph OFF (baseline, rg/Read) vs ON.
# Variant A (OFF): codex exec --skip-git-repo-check in repo_nocg (no codegraph MCP).
# Variant B (ON) : codex exec in H3-8207-Experimental (project config has codegraph),
#                  prompt instructs the agent to PRIORITIZE codegraph MCP tools.
# Captures: wall time (integer s), tokens used, codegraph tool events, rg/read events.
set -u
cd "D:/H3导演台项目目录/_experiments/CODEGRAPH_PILOT_20261027"
export PATH="$HOME/AppData/Local/OpenAI/Codex/bin:$PATH"
REPO_ON="D:/H3导演台项目目录/_experiments/CODEGRAPH_PILOT_20261027/H3-8207-Experimental"
REPO_OFF="D:/H3导演台项目目录/_experiments/CODEGRAPH_PILOT_20261027/repo_nocg"
LOG="logs"
mkdir -p "$LOG"

CG_ON="你已接入 codegraph MCP（含 codegraph_search / codegraph_callers / codegraph_callees / codegraph_impact / codegraph_explore / codegraph_status 等），导航与影响分析时优先使用这些工具。"
CG_OFF="你未接入 codegraph，只能使用 Grep / Read / ripgrep 等基础工具导航代码。"

P1B="在这个代码库里定位函数 recovery（定义于 custom_nodes/local_author/h3_conditioning_prebake/adaptive_bridge.py）。找出：1) 谁调用了它（callers，跨文件）；2) 它调用了哪些函数（callees）。只基于真实代码，列出文件路径与函数名，禁止编造。$CG_ON"
P1A="在这个代码库里定位函数 recovery（定义于 custom_nodes/local_author/h3_conditioning_prebake/adaptive_bridge.py）。找出：1) 谁调用了它（callers，跨文件）；2) 它调用了哪些函数（callees）。只基于真实代码，列出文件路径与函数名，禁止编造。$CG_OFF"

P2B="调查这个项目的『恢复/续接(resume)/回执(receipt)』逻辑：哪些类与函数实现它？涉及哪些文件？请列出关键符号与文件路径，禁止编造。$CG_ON"
P2A="调查这个项目的『恢复/续接(resume)/回执(receipt)』逻辑：哪些类与函数实现它？涉及哪些文件？请列出关键符号与文件路径，禁止编造。$CG_OFF"

P3B="如果我要修改 tools/startup_compatibility/h3_action_director/execution_graph.py 里的函数 authorize_recovery，哪些其他代码会受影响（影响范围/impact）？列出会受影响的符号与文件，禁止编造。$CG_ON"
P3A="如果我要修改 tools/startup_compatibility/h3_action_director/execution_graph.py 里的函数 authorize_recovery，哪些其他代码会受影响（影响范围/impact）？列出会受影响的符号与文件，禁止编造。$CG_OFF"

run_one () {
  local tag="$1" repo="$2" prompt="$3"
  local logf="$LOG/ab_${tag}.log"
  local t0=$(date +%s)
  if [ "$tag" = "${tag%_OFF}" ]; then
    : # ON variant
  fi
  if [[ "$tag" == *A* ]]; then
    codex exec --skip-git-repo-check -C "$repo" -- "$prompt" > "$logf" 2>&1
  else
    codex exec -C "$repo" -- "$prompt" > "$logf" 2>&1
  fi
  local rc=$?
  local t1=$(date +%s)
  local dur=$((t1 - t0))
  local tok=$(awk '/tokens used/{getline; print; exit}' "$logf")
  local cg=$(grep -cE "mcp: codegraph/codegraph_[a-z]+ (started|completed)" "$logf")
  local rg=$(grep -cE "ripgrep|\brg -|Read tool|mcp: (comfyui|files)" "$logf")
  echo "[$tag] rc=$rc  dur=${dur}s  tokens=$tok  codegraph_events=$cg  rgread_events=$rg"
}

echo "========== TASK 1: cross-file call chain =========="
run_one "A1" "$REPO_OFF" "$P1A"
run_one "B1" "$REPO_ON"  "$P1B"
echo "========== TASK 2: resume/receipt/recovery logic =========="
run_one "A2" "$REPO_OFF" "$P2A"
run_one "B2" "$REPO_ON"  "$P2B"
echo "========== TASK 3: impact of changing authorize_recovery =========="
run_one "A3" "$REPO_OFF" "$P3A"
run_one "B3" "$REPO_ON"  "$P3B"
echo "========== DONE =========="
