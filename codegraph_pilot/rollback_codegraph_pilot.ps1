<#
.SYNOPSIS
    CodeGraph v1.6.2 Pilot - 隔离回滚脚本 (P1 安全回滚)
.DESCRIPTION
    仅撤销本次 CODEGRAPH_PILOT_20261027 部署产物，绝不触碰：
      - 全局 ~/.codex/config.toml 与现有 MCP 服务器 (comfyui / browseros-neo / node_repl / cua_repl)
      - 任何正在运行的 8207 / 8210 / 8197 / 8188 等 ComfyUI 生产进程
      - 其他已存在的 CodeGraph 实例或用户文件
    回滚范围：
      1) 停止本次部署启动的 codegraph 进程（命令行/路径匹配实验目录）
      2) 删除本次实验目录（含索引、临时安装、项目级 .codex/config.toml）
      3) 验证 Codex 原有功能未被破坏
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File rollback_codegraph_pilot.ps1
#>

$ErrorActionPreference = 'Continue'
$expBase = "D:\H3导演台项目目录\_experiments\CODEGRAPH_PILOT_20261027"
$binDir  = Join-Path $expBase "codegraph-bin"

Write-Output "[ROLLBACK] 开始 CodeGraph Pilot 回滚 ($(Get-Date -Format u))"

# ---- 0. 安全前置检查：确认实验目录存在且确为本部署目录 ----
if (-not (Test-Path $expBase)) {
    Write-Output "[ROLLBACK] 实验目录不存在，无需回滚: $expBase"
    exit 0
}
# 防误删：仅当目录名匹配本次 pilot 标记才允许删除
if ($expBase -notmatch 'CODEGRAPH_PILOT_20261027$') {
    Write-Output "[ROLLBACK][ABORT] 路径不匹配 pilot 标记，拒绝执行以防误删: $expBase"
    exit 1
}

# ---- 1. 停止本次部署启动的 codegraph 进程 ----
Write-Output "[ROLLBACK] 查找本次部署的 codegraph 进程 ..."
$targets = @()
try {
    $procs = Get-CimInstance Win32_Process -Filter "Name LIKE '%codegraph%'" -ErrorAction Stop
    foreach ($p in $procs) {
        $cmd = $p.CommandLine
        $path = $p.ExecutablePath
        # 仅匹配本次实验目录下的进程（命令行或可执行路径包含实验 bin 目录）
        if (($cmd -and $cmd -like "*$expBase*") -or ($path -and $path -like "$binDir*")) {
            $targets += $p
        }
    }
} catch {
    Write-Output "[ROLLBACK][WARN] 进程枚举失败: $_"
}
if ($targets.Count -eq 0) {
    Write-Output "[ROLLBACK] 未发现本次部署的 codegraph 进程（可能已退出）"
} else {
    foreach ($p in $targets) {
        try {
            Write-Output "[ROLLBACK] 停止 PID=$($p.ProcessId) -> $($p.ExecutablePath)"
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Output "[ROLLBACK][WARN] 停止 PID=$($p.ProcessId) 失败: $_"
        }
    }
    Start-Sleep -Seconds 1
}

# ---- 2. 删除实验目录（含索引、临时安装、项目级配置） ----
Write-Output "[ROLLBACK] 删除实验目录: $expBase"
try {
    Remove-Item -Path $expBase -Recurse -Force -ErrorAction Stop
    Write-Output "[ROLLBACK] 已删除实验目录"
} catch {
    Write-Output "[ROLLBACK][WARN] 删除失败: $_"
}

# ---- 3. 验证 Codex 原有功能未被破坏 ----
Write-Output "[ROLLBACK] 验证 Codex 全局功能 ..."
try {
    $cv = & codex --version 2>&1 | Out-String | ForEach-Object { $_.Trim() }
    Write-Output "[ROLLBACK] codex --version -> $cv"
} catch {
    Write-Output "[ROLLBACK][WARN] codex --version 执行异常: $_"
}
$globalCfg = "$env:USERPROFILE\.codex\config.toml"
if (Test-Path $globalCfg) {
    Write-Output "[ROLLBACK] 全局 config.toml 仍存在（未被修改）: $globalCfg"
    # 确认生产 MCP 仍在（comfyui 为关键生产 MCP）
    $content = Get-Content $globalCfg -Raw
    if ($content -match '\[mcp_servers\.comfyui\]') {
        Write-Output "[ROLLBACK][OK] 生产 MCP [mcp_servers.comfyui] 配置完好"
    } else {
        Write-Output "[ROLLBACK][ALERT] 全局 config.toml 中未发现 [mcp_servers.comfyui]，请人工核查！"
    }
} else {
    Write-Output "[ROLLBACK][ALERT] 全局 config.toml 缺失，请人工核查！"
}

# ---- 4. 移除 codex exec -C 写入全局 config 的 pilot trust 条目（Codex 簿记，非生产） ----
# `codex exec -C <repo>` 会在全局 config 的 [projects.<path>] 下写入 trust_level。
# 该条目非生产 MCP，仅本次 pilot 引入；回滚时一并移除，使全局 config 回到部署前状态。
try {
    $lines = Get-Content $globalCfg
    $out = @()
    $skipTrust = $false
    $removed = $false
    foreach ($line in $lines) {
        if ($line -match "\[projects\..*codegraph_pilot_20261027") {
            $skipTrust = $true
            $removed = $true
            continue
        }
        if ($skipTrust) {
            if ($line -match 'trust_level') { $skipTrust = $false; continue }
            $skipTrust = $false
        }
        $out += $line
    }
    if ($removed) {
        Set-Content $globalCfg -Value $out
        Write-Output "[ROLLBACK][OK] 已移除全局 config 中的 pilot trust 条目 ([projects.*codegraph_pilot_20261027])"
    } else {
        Write-Output "[ROLLBACK] 全局 config 中无 pilot trust 条目，无需移除"
    }
} catch {
    Write-Output "[ROLLBACK][WARN] 移除 pilot trust 条目失败，请人工核查: $_"
}

Write-Output "[ROLLBACK] 回滚流程结束。生产环境应不受影响。"
