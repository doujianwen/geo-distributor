$ErrorActionPreference = 'Stop'
$portalRoot = Split-Path -Parent $PSScriptRoot
$runtimeConfig = Join-Path $portalRoot 'config/portal_runtime.local.json'
$portalPort = 8767
if (Test-Path -LiteralPath $runtimeConfig) { $portalPort = (Get-Content -LiteralPath $runtimeConfig -Raw | ConvertFrom-Json).demo_port }
if (Get-NetTCPConnection -LocalPort $portalPort -State Listen -ErrorAction SilentlyContinue) {
    throw ('Port {0} is occupied. Check the existing service before restarting.' -f $portalPort)
}
$portalPython = Join-Path $portalRoot '.venv/Scripts/pythonw.exe'
$portalEntry = Join-Path $portalRoot 'scripts/run_portal_demo.py'
$launch = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = ('"{0}" "{1}"' -f $portalPython, $portalEntry)
    CurrentDirectory = $portalRoot
}
if ($launch.ReturnValue -ne 0) { throw 'Unable to start the demo workspace.' }
$launch | Select-Object ProcessId, ReturnValue
