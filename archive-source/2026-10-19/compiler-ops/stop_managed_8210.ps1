$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root 'data\server.pid'
$StopMarker = Join-Path $Root 'data\managed-8210.stop'

if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host '8210 PID 文件不存在；没有发出停止信号。'
    exit 0
}
$ServerPid = [int](Get-Content -LiteralPath $PidFile | Select-Object -First 1)
$Listener = Get-NetTCPConnection -LocalPort 8210 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $Listener -or $Listener.OwningProcess -ne $ServerPid) {
    throw "8210 PID/listener 不一致；拒绝停止。pidfile=$ServerPid listener=$(if($Listener){$Listener.OwningProcess}else{'none'})"
}
if (Test-Path -LiteralPath $StopMarker) {
    throw '停止标记已存在；请先检查受管服务状态。'
}
[IO.File]::WriteAllText($StopMarker, [guid]::NewGuid().ToString(), [Text.Encoding]::ASCII)
$Deadline = (Get-Date).AddSeconds(10)
do {
    Start-Sleep -Milliseconds 200
    $Listener = Get-NetTCPConnection -LocalPort 8210 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $Listener -and -not (Test-Path -LiteralPath $PidFile)) {
        Write-Host "8210 已正常停止（原 PID=$ServerPid）。"
        exit 0
    }
} while ((Get-Date) -lt $Deadline)
throw "8210 未在 10 秒内完成优雅停止（原 PID=$ServerPid）。"
