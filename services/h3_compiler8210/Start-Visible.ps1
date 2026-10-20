param([string]$Python = (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'), [int]$Port = 8210, [switch]$ConsoleWorker)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python not found: $Python. Create this service's venv and install the documented translation dependency first." }
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) { throw "Port $Port already listens (PID $($existing.OwningProcess -join ',')). Verify the existing service; this launcher never stops it." }
if (-not $ConsoleWorker) {
    $taskArgs = @('-NoExit', '-NoProfile', '-File', ('"' + $PSCommandPath + '"'), '-ConsoleWorker', '-Python', ('"' + $Python + '"'), '-Port', "$Port")
    Start-Process -FilePath 'powershell.exe' -ArgumentList $taskArgs -WorkingDirectory $PSScriptRoot -WindowStyle Normal
    return
}
$Host.UI.RawUI.WindowTitle = "H3 Compiler $Port - http://127.0.0.1:$Port"
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONUTF8 = '1'
Set-Location -LiteralPath $PSScriptRoot
Write-Host "H3 compiler: http://127.0.0.1:$Port; Python: $Python"
try { & $Python -u -m app $Port; Write-Host "Service exited: $LASTEXITCODE" } catch { Write-Error $_ }
Read-Host 'Press Enter to close this console'
