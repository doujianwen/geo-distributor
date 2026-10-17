#!/usr/bin/env python3
"""RA-06 V2 access matrix test. Run:
    .venv/Scripts/python.exe scripts/ra06_v2_access_matrix.py
Never prints API keys. Saves JSON evidence.
"""
import json
import socket
import urllib.request
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVID = Path(r"E:\一人公司\FDE\渠道商演示环境就绪度核验\2026-10-17\REMAINING_BLOCKERS_CLOSURE_20261017_V2\evidence")
NONLOOPBACK = ["192.168.31.160", "172.25.192.1", "172.28.0.1", "172.19.0.1", "169.254.218.55"]
results = []


def record(cid, desc, expect, actual, extra=""):
    ok = actual == expect
    results.append({"id": cid, "desc": desc, "expect": expect,
                    "actual": actual, "pass": ok, "extra": extra})
    print(f"{'PASS' if ok else 'FAIL'} {cid}: {desc} -> {actual} (expect {expect}) {extra}")


def tcp_probe(ip, port, timeout=3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        return "OPEN"
    except Exception:
        return "REFUSED"
    finally:
        s.close()


def http(method, url, key=None, host=None, body=None, timeout=8):
    req = urllib.request.Request(url, method=method)
    if key:
        req.add_header("X-API-Key", key)
    if host:
        req.add_header("Host", host)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as r:
            return r.status, r.read(200).decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(200).decode(errors="replace")
    except Exception as e:
        return type(e).__name__, str(e)[:120]


def keys():
    reg = json.loads((REPO / "config" / "api_keys.json").read_text(encoding="utf-8"))
    out = {}
    for e in reg["keys"]:
        out[e["role"] + "|" + e["tenant_id"]] = e["api_key"]
    return out


K = keys()
HQ = K["HQ_TECHNICAL|T-E2E-SMOKE"]
DA = K["DISTRIBUTOR_ADMIN|T-E2E-SMOKE"]
DB = K["DISTRIBUTOR_ADMIN|T-DEMO-B"]
CV = K["CLIENT_VIEWER|T-E2E-SMOKE"]

# --- A. Non-loopback exposure (RA-06 core) ---
for ip in NONLOOPBACK:
    record(f"NL-80-{ip}", f"non-loopback {ip}:80 TCP", "REFUSED", tcp_probe(ip, 80))
for ip in NONLOOPBACK:
    record(f"NL-443-{ip}", f"non-loopback {ip}:443 TCP", "REFUSED", tcp_probe(ip, 443))
for ip in NONLOOPBACK:
    record(f"NL-8765-{ip}", f"non-loopback {ip}:8765 TCP", "REFUSED", tcp_probe(ip, 8765))
for ip in NONLOOPBACK:
    record(f"NL-8080-{ip}", f"non-loopback {ip}:8080 TCP", "REFUSED", tcp_probe(ip, 8080))

# --- B. Legal local entries ---
record("LB-01", "geo-growth.local/portal/ (loopback)", 200, http("GET", "http://geo-growth.local/portal/")[0])
record("LB-02", "geo-growth.local/ui/ (loopback)", 200, http("GET", "http://geo-growth.local/ui/")[0])
record("LB-03", "geo-growth.local/ui/app.js", 200, http("GET", "http://geo-growth.local/ui/app.js")[0])
record("LB-04", "geo-growth.local/ (commercial site)", 200, http("GET", "http://geo-growth.local/")[0])
record("LB-05", "localhost/ (WordPress)", 200, http("GET", "http://localhost/")[0])
record("LB-06", "127.0.0.1/geo-api/health", 200, http("GET", "http://127.0.0.1/geo-api/health")[0])
record("LB-07", "127.0.0.1:8765/health (app direct, loopback)", 200, http("GET", "http://127.0.0.1:8765/health")[0])

# --- C. Unauthenticated / auth failures ---
record("AU-01", "API no key via Apache /geo-api/clients", 401, http("GET", "http://127.0.0.1/geo-api/clients")[0])
record("AU-02", "API wrong key", 401, http("GET", "http://127.0.0.1/geo-api/clients", key="sk-wrong-key")[0])
record("AU-03", "API no key direct 8765", 401, http("GET", "http://127.0.0.1:8765/clients")[0])

# --- D. Role boundaries ---
s, b = http("POST", "http://127.0.0.1/geo-api/clients", key=CV,
            body={"name": "RA06-V2-VIEWER-PROBE", "industry": "demo"})
record("RB-01", "CLIENT_VIEWER POST /clients", 403, s)
s, b = http("POST", "http://127.0.0.1/geo-api/projects/PRJ-BA5C0FC8/deliver", key=DA)
record("RB-02", "DISTRIBUTOR_ADMIN deliver", 403, s)

# --- E. Cross-tenant isolation ---
s, b = http("GET", "http://127.0.0.1/geo-api/projects/PRJ-BA5C0FC8", key=DB)
record("XT-01", "T-DEMO-B admin reads T-E2E-SMOKE project", 404, s)
s, b = http("GET", "http://127.0.0.1/geo-api/clients", key=DB)
if s == 200:
    req = urllib.request.Request("http://127.0.0.1/geo-api/clients")
    req.add_header("X-API-Key", DB)
    with urllib.request.urlopen(req, timeout=8) as r:
        payload = json.loads(r.read().decode())
    tids = {c.get("tenant_id") for c in payload}
    leak = "T-E2E-SMOKE" in tids
    record("XT-02", "T-DEMO-B admin sees zero T-E2E-SMOKE clients",
           "NO-LEAK", "LEAK" if leak else "NO-LEAK", f"tenants={tids}")
else:
    record("XT-02", "T-DEMO-B admin client list", 200, s)

# --- F. Path traversal & nonexistent ---
record("PT-01", "/geo-api/clients/../../etc/passwd", 404, http("GET", "http://127.0.0.1/geo-api/clients/../../etc/passwd", key=HQ)[0])
record("PT-02", "/geo-api/..%5C..%5Cwindows%5Cwin.ini", 404, http("GET", "http://127.0.0.1/geo-api/..%5C..%5Cwindows%5Cwin.ini", key=HQ)[0])
record("PT-03", "/geo-api/../geo_distributor/persistence/sqlite_repository.py", 404, http("GET", "http://127.0.0.1/geo-api/../geo_distributor/persistence/sqlite_repository.py", key=HQ)[0])
record("NE-01", "/geo-api/api/nonexistent", 404, http("GET", "http://127.0.0.1/geo-api/api/nonexistent", key=HQ)[0])
# docs endpoints: app-layer 404 confirmed (direct 8765 also 404). Apache-level
# `Require all denied` in LocationMatch does NOT fire (request reaches app) —
# recorded as P2 observation; security outcome (not accessible) holds.
s1 = http("GET", "http://127.0.0.1/geo-api/docs")[0]
record("NE-02", "/geo-api/docs not accessible (403 or 404)", "IN(403,404)",
       "IN(403,404)" if s1 in (403, 404) else str(s1), f"actual={s1}")
s2 = http("GET", "http://127.0.0.1/geo-api/openapi.json")[0]
record("NE-03", "/geo-api/openapi.json not accessible (403 or 404)", "IN(403,404)",
       "IN(403,404)" if s2 in (403, 404) else str(s2), f"actual={s2}")

# --- G. php:8080 (protected service, state record only) ---
record("RA09-01", "php:8080 loopback (unchanged, no action)", 200, http("GET", "http://127.0.0.1:8080/")[0])

(EVID / "ra06_v2_access_matrix.json").write_text(
    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
passed = sum(1 for r in results if r["pass"])
print(f"\nSUMMARY: {passed}/{len(results)} passed")
