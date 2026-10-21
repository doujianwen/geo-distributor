$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$portalPort = 17669
$runtimeConfig = Join-Path $portalRoot 'config/portal_runtime.local.json'
if (Test-Path -LiteralPath $runtimeConfig) {
    $configured = Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json
    if ($null -ne $configured.growth_sandbox_port) { $portalPort = [int]$configured.growth_sandbox_port }
}
$existing = Get-NetTCPConnection -LocalPort $portalPort -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $owner = Get-CimInstance Win32_Process -Filter ('ProcessId={0}' -f $existing[0].OwningProcess)
    if ($owner.CommandLine -notmatch 'run_growth_sandbox\.py') { throw 'The lab port belongs to another service.' }
    Write-Output ('Interactive lab is running: http://127.0.0.1:{0}/ui/lab/' -f $portalPort)
    return
}
$portalPython = Join-Path $portalRoot '.venv/Scripts/pythonw.exe'
Start-Process -FilePath $portalPython -ArgumentList (Join-Path $portalRoot 'scripts/run_growth_sandbox.py') -WorkingDirectory $portalRoot -WindowStyle Hidden
Write-Output ('Interactive lab starting: http://127.0.0.1:{0}/ui/lab/' -f $portalPort)
