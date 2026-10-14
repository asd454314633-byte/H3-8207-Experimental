param([string]$Model='', [switch]$CloudRouting, [switch]$Console)
$ErrorActionPreference='Stop'
$base='http://127.0.0.1:8197/api/h3-director'
Write-Host 'DIRECTOR_URL = http://127.0.0.1:8197/h3-director/six'
$reply=& curl.exe --silent --show-error --fail --noproxy '*' --max-time 5 "$base/status"
if ($LASTEXITCODE -ne 0) { throw '8197 Director unavailable; inspect visible ComfyUI console. No alternate server started.' }
$reply | Out-Host
if ($Model) {
    if ($Model -notin @('dark_roast','gemma4')) { throw 'Unknown local model' }
    $body=@{model_key=$Model} | ConvertTo-Json -Compress
    $tempFile=Join-Path $env:TEMP ([guid]::NewGuid().ToString()+'.json')
    try {
        [IO.File]::WriteAllText($tempFile,$body,[Text.UTF8Encoding]::new($false))
        & curl.exe --silent --show-error --fail --noproxy '*' --max-time 130 -H 'Content-Type: application/json' --data-binary "@$tempFile" "$base/model/warm"
        if ($LASTEXITCODE -ne 0) { throw 'Model warmup failed; existing busy model protected' }
    } finally { Remove-Item -LiteralPath $tempFile -ErrorAction SilentlyContinue }
}
