# Persistent local workspace. No public binding and no credential defaults.
$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$runtimeConfig = Join-Path $portalRoot 'config/portal_runtime.local.json'
$portalPort = 8765
if (Test-Path -LiteralPath $runtimeConfig) { $portalPort = (Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json).local_port }
if (Get-NetTCPConnection -LocalPort $portalPort -State Listen -ErrorAction SilentlyContinue) {
    throw ('Port {0} is already in use. Preserve the current service and review it before restarting.' -f $portalPort)
}
$portalPython = Join-Path $portalRoot '.venv/Scripts/pythonw.exe'
$portalEntry = Join-Path $portalRoot 'scripts/run_portal_local.py'
# A detached pythonw process survives the launching terminal without a console.
$launch = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = ('"{0}" "{1}"' -f $portalPython, $portalEntry)
    CurrentDirectory = $portalRoot
}
if ($launch.ReturnValue -ne 0) { throw 'Unable to start the local workspace.' }
$launch | Select-Object ProcessId, ReturnValue
