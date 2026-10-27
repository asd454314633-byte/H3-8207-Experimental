#!/usr/bin/env bash
# Multi-session concurrency test for CodeGraph MCP pilot.
# Launches TWO concurrent `codex exec` sessions against the SAME index and
# verifies both connect to the codegraph MCP server without persistent lock
# contention, index stalls, or process crashes.
set -u
cd "D:/H3导演台项目目录/_experiments/CODEGRAPH_PILOT_20261027"
export PATH="$HOME/AppData/Local/OpenAI/Codex/bin:$PATH"
REPO="D:/H3导演台项目目录/_experiments/CODEGRAPH_PILOT_20261027/H3-8207-Experimental"
LOG="logs"
mkdir -p "$LOG"
TS=$(date +%H:%M:%S.%N)

echo "[$TS] Launching concurrent session A and B..."

# Session A: explore a recovery-flow symbol
codex exec -C "$REPO" -- "用 codegraph MCP 工具分析 recovery 恢复逻辑，列出涉及的文件路径。只输出工具真实返回。" > "$LOG/multi_A.log" 2>&1 &
PID_A=$!

# Session B: search a director symbol
codex exec -C "$REPO" -- "用 codegraph MCP 工具查找 Director 类的定义位置与调用关系。只输出工具真实返回。" > "$LOG/multi_B.log" 2>&1 &
PID_B=$!

echo "[$(date +%H:%M:%S.%N)] A pid=$PID_A  B pid=$PID_B"

# Wait for both
wait $PID_A; RC_A=$?
wait $PID_B; RC_B=$?

echo "[$(date +%H:%M:%S.%N)] A exit=$RC_A  B exit=$RC_B"

echo "=== SESSION A: mcp connect lines ==="
grep -nE "mcp: codegraph|error|lock|fail|timeout|ECONN|EADDR" "$LOG/multi_A.log" | head -20
echo "=== SESSION B: mcp connect lines ==="
grep -nE "mcp: codegraph|error|lock|fail|timeout|ECONN|EADDR" "$LOG/multi_B.log" | head -20

echo "=== A connected? ==="
grep -qE "mcp: codegraph/codegraph_[a-z]+ (started|completed)" "$LOG/multi_A.log" && echo "A: YES" || echo "A: NO"
echo "=== B connected? ==="
grep -qE "mcp: codegraph/codegraph_[a-z]+ (started|completed)" "$LOG/multi_B.log" && echo "B: YES" || echo "B: NO"
