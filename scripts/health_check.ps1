# ============================================================
# RA-11 可观测性 · 本地健康检查（Windows 原生 / PowerShell 版）
# ------------------------------------------------------------
# 用途: 对 geo-distributor 本地演示环境做一轮完整健康探测。
#       任一判据失败即退出码 1（可被 Windows 计划任务捕获后触发
#       外部告警，如飞书 Webhook——参照 bookconv FEISHU_WEBHOOK_URL 模式）。
#
# 判据（与 scripts/health_check.sh 完全一致）:
#   C1  /health HTTP 200 且 body 为 {"status":"ok"}
#   C2  持久化: data/geo_distributor.db 存在且 reports_projection 可读
#   C3  数据完整性: PRAGMA quick_check == ok
#   C4  幂等约束: ux_reports_projection_ptv 唯一索引存在
#   C5  审计日志: data/audit_log.db 存在且 audit_log 行数 > 0
#   C6  (可选, -WithApache) 经 Apache 反代 /geo-api/health 可达
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts\health_check.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\health_check.ps1 -WithApache
#   powershell -ExecutionPolicy Bypass -File scripts\health_check.ps1 -BaseUrl http://127.0.0.1:8765
#
# Python 查找顺序: <repo>\.venv\Scripts\python.exe → 系统 PATH python
# 兼容性: Windows PowerShell 5.1+ / PowerShell 7+；不依赖 Git Bash / MSYS。
# 计划任务示例:
#   schtasks /Create /TN "GEO-HealthCheck" /SC HOURLY /TR ^
#     "powershell -ExecutionPolicy Bypass -File E:\GEO项目\技术层\geo-distributor\scripts\health_check.ps1"
# ============================================================
param(
    [switch]$WithApache,
    [string]$BaseUrl = "http://127.0.0.1:8765",
    [string]$ApacheUrl = "http://geo-growth.local/geo-api/health"
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
# 中文路径/中文 Windows 控制台编码统一：子进程 python 输出 UTF-8，宿主按 UTF-8 解码
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'

$repoRoot = Split-Path -Parent $PSScriptRoot
$failures = 0

function Write-Pass([string]$msg) { Write-Output "[PASS] $msg" }
function Write-Fail([string]$msg) {
    Write-Output "[FAIL] $msg"
    $script:failures++
}

# ---- Python 解析：优先 .venv，回退系统 Python ----
$venvPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (Test-Path $venvPy) {
    $python = $venvPy
} else {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Write-Fail "C0 python not found (no .venv and no system python)"
        Write-Output "----------------------------------------"
        Write-Output "HEALTH_CHECK: FAIL (1 failure(s))"
        exit 1
    }
    $python = $cmd.Source
}

# ---- C1 /health（Invoke-WebRequest，.NET 原生） ----
try {
    $resp = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 10
    $body = $resp.Content.Trim()
    if ($resp.StatusCode -eq 200 -and $body -eq '{"status":"ok"}') {
        Write-Pass "C1 /health 200 + status ok"
    } else {
        Write-Fail "C1 /health -> HTTP=$($resp.StatusCode) body=$body"
    }
} catch {
    Write-Fail "C1 /health unreachable: $($_.Exception.Message)"
}

# ---- C2/C3/C4/C5 数据库检查（python 脚本文件方式，规避 Win32 传参引号剥离） ----
$dbPath = Join-Path $repoRoot 'data\geo_distributor.db'
$auditPath = Join-Path $repoRoot 'data\audit_log.db'

$pyCode = @'
import sqlite3, sys
db, audit = sys.argv[1], sys.argv[2]
import os
# 输出用相对路径，避免非 ASCII 绝对路径跨控制台代码页乱码
db_rel = os.path.relpath(db, os.path.dirname(os.path.dirname(db)))
audit_rel = os.path.relpath(audit, os.path.dirname(os.path.dirname(audit)))
if not os.path.isfile(db):
    print("[FAIL] C2 db file missing: %s" % db_rel); sys.exit(1)
print("[PASS] C2 db file exists: %s" % db_rel)
try:
    c = sqlite3.connect(db)
    n = c.execute("SELECT COUNT(*) FROM reports_projection").fetchone()[0]
    print("[PASS] C2 reports_projection readable, rows=%d" % n)
except Exception as e:
    print("[FAIL] C2 reports_projection unreadable: %r" % e); sys.exit(1)
qc = c.execute("PRAGMA quick_check").fetchone()[0]
print("[%s] C3 quick_check = %s" % ("PASS" if qc == "ok" else "FAIL", qc))
if qc != "ok": sys.exit(1)
idx = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='ux_reports_projection_ptv'").fetchone()[0]
print("[%s] C4 unique index ux_reports_projection_ptv present = %s" % ("PASS" if idx else "FAIL", bool(idx)))
if not idx: sys.exit(1)
c.close()
if not os.path.isfile(audit):
    print("[FAIL] C5 audit_log.db missing: %s" % audit_rel); sys.exit(1)
try:
    a = sqlite3.connect(audit)
    rows = a.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    a.close()
    if rows > 0:
        print("[PASS] C5 audit_log.db rows=%d" % rows)
    else:
        print("[FAIL] C5 audit_log.db empty rows=0"); sys.exit(1)
except Exception as e:
    print("[FAIL] C5 audit_log unreadable: %r" % e); sys.exit(1)
sys.exit(0)
'@

$tmpPy = Join-Path $env:TEMP ("geo_dist_health_" + [guid]::NewGuid().ToString("N") + ".py")
try {
    [IO.File]::WriteAllText($tmpPy, $pyCode, [Text.UTF8Encoding]::new($false))
    & $python $tmpPy $dbPath $auditPath 2>&1 | ForEach-Object {
        $line = "$_"
        if ($line -match '^\[FAIL\]') { Write-Fail $line } else { Write-Output $line }
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "C2-C5 db checks exited with code $LASTEXITCODE"
    }
} finally {
    Remove-Item $tmpPy -ErrorAction SilentlyContinue
}

# ---- C6 可选 Apache 反代探针 ----
if ($WithApache) {
    try {
        $resp6 = Invoke-WebRequest -Uri $ApacheUrl -UseBasicParsing -TimeoutSec 10
        if ($resp6.StatusCode -eq 200) {
            Write-Pass "C6 apache /geo-api/health 200"
        } else {
            Write-Fail "C6 apache /geo-api/health -> $($resp6.StatusCode)"
        }
    } catch {
        Write-Fail "C6 apache unreachable: $($_.Exception.Message)"
    }
}

Write-Output "----------------------------------------"
if ($failures -gt 0) {
    Write-Output "HEALTH_CHECK: FAIL ($failures failure(s))"
    exit 1
}
Write-Output "HEALTH_CHECK: PASS (all criteria green)"
exit 0
