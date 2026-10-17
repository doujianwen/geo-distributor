#!/usr/bin/env python3
# ra04_v2_recovery_drill.py — RA-04 真实备份/恢复/回滚演练（GGS V2）
#
# 流程：一致性备份实时库 → 隔离恢复 → 完整性校验 → 启动恢复副本(独立端口/独立DB)
#       → 读/写/权限测试 → 证明写入只落到恢复副本、原库零污染 → 关闭副本 → 原库SHA不变
#
# 不变量：绝不写回 / 删除 / 覆盖实时 data/geo_distributor.db。

import os, sys, json, time, shutil, sqlite3, hashlib, subprocess, urllib.request, urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_DB = os.path.join(REPO, "data", "geo_distributor.db")
API_KEYS = os.path.join(REPO, "config", "api_keys.json")
ISO_ROOT = "C:/Users/29537/AppData/Local/Temp/ggs-ra04-restore"
RESTORE_DB = os.path.join(ISO_ROOT, "geo_distributor_restored.db")
BACKUP_DB = os.path.join(ISO_ROOT, "geo_distributor_backup.db")
PORT = 18765

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def load_key(role="HQ_TECHNICAL", tenant=None):
    reg = json.load(open(API_KEYS, encoding="utf-8"))
    for e in reg["keys"]:
        if e["role"] == role and (tenant is None or e["tenant_id"] == tenant):
            return e["api_key"]
    return reg["keys"][0]["api_key"]

def api_call(method, path, key, body=None):
    url = f"http://127.0.0.1:{PORT}{path}"
    req = urllib.request.Request(url, method=method)
    req.add_header("X-API-Key", key)
    data = None
    if body is not None:
        data = json.dumps(body).encode(); req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

def db_counts(p):
    c = sqlite3.connect(p)
    out = {}
    for t in ["clients", "projects", "requests", "reports_projection", "measurements_projection"]:
        try:
            out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except Exception:
            out[t] = "MISSING"
    c.close()
    return out

def wait_health(timeout=25):
    for _ in range(timeout):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False

def main():
    os.makedirs(ISO_ROOT, exist_ok=True)
    print("=== RA-04 备份/恢复/回滚演练 ===")

    # 1) 一致性备份实时库
    live_sha_before = sha(LIVE_DB)
    shutil.copy(LIVE_DB, BACKUP_DB)
    backup_sha = sha(BACKUP_DB)
    assert backup_sha == live_sha_before, "backup sha mismatch"
    print(f"[1] live SHA(before) = {live_sha_before[:16]}")
    print(f"[1] backup SHA       = {backup_sha[:16]}  (== live)")

    # 2) 隔离恢复
    shutil.copy(BACKUP_DB, RESTORE_DB)
    restore_sha = sha(RESTORE_DB)
    assert restore_sha == backup_sha, "restore sha mismatch"
    print(f"[2] restore SHA      = {restore_sha[:16]}  (== backup)")

    # 3) 结构/计数/样本校验
    live_counts = db_counts(LIVE_DB)
    restore_counts = db_counts(RESTORE_DB)
    print(f"[3] live counts   = {live_counts}")
    print(f"[3] restore counts= {restore_counts}")
    assert live_counts == restore_counts, "count mismatch"
    c = sqlite3.connect(RESTORE_DB)
    sample = c.execute("SELECT id FROM reports_projection ORDER BY rowid DESC LIMIT 1").fetchone()
    c.close()
    print(f"[3] restore sample report = {sample[0] if sample else None}")

    # 4) 启动恢复副本（独立端口 + 独立 DB）
    env = dict(os.environ, GEO_DISTRIBUTOR_DB=RESTORE_DB, GEO_DISTRIBUTOR_ENV="demo")
    proc = subprocess.Popen(
        [os.path.join(REPO, ".venv", "Scripts", "python.exe"), "-m", "uvicorn",
         "api.app:app", "--host", "127.0.0.1", "--port", str(PORT), "--no-server-header"],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_health(), "restore replica did not become healthy"
        print(f"[4] restore replica healthy on :{PORT} (pid {proc.pid})")

        # 5) 读测试：已知报告可读
        hq = load_key("HQ_TECHNICAL")
        st, rep = api_call("GET", f"/reports/{sample[0]}", hq)
        assert st == 200 and rep.get("report_id") == sample[0], f"readback failed {st}"
        print(f"[5] read RPT {sample[0]}: HTTP {st}, tenant={rep.get('tenant_id')}")

        # 5) 写测试：在恢复副本创建新 client
        st, cli = api_call("POST", "/clients", hq, {
            "name": "RA04-RECOVERY-REPLICA-WRITE", "industry": "demo",
            "website": "http://ra04.test", "contact_email": "ra04@test.local"})
        assert st in (200, 201), f"client create failed {st}"
        new_cid = cli["client_id"]
        st, rb = api_call("GET", f"/clients/{new_cid}", hq)
        assert st == 200, "client readback failed"
        print(f"[5] replica write+read: client {new_cid} HTTP {st}")

        # 5) 权限测试：错误 key 被拒
        bad = "invalid-key-0000"
        try:
            api_call("GET", "/clients", bad)
            print("[5] WARN: bad key not rejected")
        except urllib.error.HTTPError as e:
            assert e.code == 401, f"expected 401 got {e.code}"
            print(f"[5] permission: bad key -> HTTP {e.code} (rejected OK)")

        # 6) 证明写入只落到恢复副本，原库零污染
        restore_after = db_counts(RESTORE_DB)
        live_after = db_counts(LIVE_DB)
        assert restore_after["clients"] == live_counts["clients"] + 1, "replica client not persisted"
        assert live_after["clients"] == live_counts["clients"], "ORIGINAL DB WAS MODIFIED!"
        live_sha_after = sha(LIVE_DB)
        assert live_sha_after == live_sha_before, "ORIGINAL DB SHA CHANGED!"
        print(f"[6] replica clients now = {restore_after['clients']} (orig was {live_counts['clients']})")
        print(f"[6] ORIGINAL clients   = {live_after['clients']} (unchanged)")
        print(f"[6] ORIGINAL SHA after = {live_sha_after[:16]} (== before: {live_sha_after==live_sha_before})")

        # 7) 回滚可行性：用备份即可重建恢复副本（已验证 restore sha == backup sha）
        print("[7] rollback path: backup -> restore verified (sha stable)")
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except Exception: proc.kill()

    print("=== RA-04 DRILL: PASS ===")
    print(json.dumps({
        "live_sha_before": live_sha_before, "backup_sha": backup_sha,
        "restore_sha": restore_sha, "live_sha_after": sha(LIVE_DB),
        "live_counts": live_counts, "restore_counts": restore_counts,
        "original_untouched": sha(LIVE_DB) == live_sha_before,
        "replica_write_persisted": db_counts(RESTORE_DB)["clients"] == live_counts["clients"] + 1,
    }, indent=2))

if __name__ == "__main__":
    main()
