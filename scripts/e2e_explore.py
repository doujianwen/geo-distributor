"""A1.7.1 — 实时 Elmo API 探索脚本。

在真实 Elmo 实例上验证 API schema、endpoint 可用性和数据格式。
不修改 geo-distributor 代码，只读取和打印原始响应。
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

API_KEY = "5vGAUQo58wjhLiXp43bV3lvgIhF/AnIk6WxtREjevn4="
BASE = "http://localhost:1515"
PID = "7e64e741-b090-467f-a2e4-8106b186634e"
BRAND_ID = "test-brand"

def api_get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {API_KEY}"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        ct = resp.headers.get("Content-Type", "")
        body = resp.read().decode()
        return resp.status, ct, body
    except urllib.error.HTTPError as e:
        ct = e.headers.get("Content-Type", "")
        body = e.read().decode()[:500]
        return e.code, ct, body

def api_post(path, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=data,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        ct = resp.headers.get("Content-Type", "")
        result = resp.read().decode()
        return resp.status, ct, result
    except urllib.error.HTTPError as e:
        ct = e.headers.get("Content-Type", "")
        result = e.read().decode()[:500]
        return e.code, ct, result


print("=" * 60)
print("A1.7.1 — Real Elmo API Exploration")
print(f"Base: {BASE}")
print(f"Timestamp: {datetime.now().isoformat()}")
print("=" * 60)

# T1: Health / Me
print("\n[T1] GET /api/v1/me")
status, ct, body = api_get("/api/v1/me")
print(f"  Status: {status}, Content-Type: {ct}")
if "json" in ct:
    print(f"  Response: {body[:300]}")
else:
    print(f"  Response: {body[:200]}")

# T2: Models
print("\n[T2] GET /api/v1/models")
status, ct, body = api_get("/api/v1/models")
print(f"  Status: {status}, Content-Type: {ct}")
if "json" in ct:
    data = json.loads(body)
    print(f"  Models count: {len(data.get('models', data.get('data', [])))}")
    for m in (data.get('models', data.get('data', [])))[:5]:
        print(f"    - {m}")
else:
    print(f"  Response: {body[:200]}")

# T3: Brands
print("\n[T3] GET /api/v1/brands")
status, ct, body = api_get("/api/v1/brands")
print(f"  Status: {status}")
if status == 200 and "json" in ct:
    data = json.loads(body)
    print(f"  Total brands: {data.get('pagination',{}).get('total', '?')}")
    for b in data.get("brands", data.get("data", [])):
        print(f"    Brand: {b.get('id')} name={b.get('name')} domains={b.get('domains')}")
        # Get brand detail
        bid = b.get("id")
        s2, ct2, b2 = api_get(f"/api/v1/brands/{bid}")
        if s2 == 200 and "json" in ct2:
            bd = json.loads(b2)
            print(f"      Full: enabled={bd.get('enabled')} onboarded={bd.get('onboarded')}")
            print(f"      Keys: {list(bd.keys())}")

# T4: Prompts
print("\n[T4] GET /api/v1/prompts")
status, ct, body = api_get("/api/v1/prompts")
print(f"  Status: {status}")
if status == 200 and "json" in ct:
    data = json.loads(body)
    prompts = data.get("prompts", data.get("data", []))
    print(f"  Total prompts: {len(prompts)}")
    for p in prompts:
        print(f"    Prompt: {p.get('id')} value={p.get('value')[:60]}...")
        # Get prompt detail
        pid = p.get("id")
        s2, ct2, b2 = api_get(f"/api/v1/prompts/{pid}")
        if s2 == 200 and "json" in ct2:
            pd = json.loads(b2)
            print(f"      Keys: {list(pd.keys())}")

# T5: Runs — list
print("\n[T5] GET /api/v1/prompts/{id}/runs")
status, ct, body = api_get(f"/api/v1/prompts/{PID}/runs?page=1&limit=10")
print(f"  Status: {status}, Content-Type: {ct}")
if status == 200 and "json" in ct:
    data = json.loads(body)
    runs = data.get("data", [])
    print(f"  Total runs: {data.get('pagination',{}).get('total','?')}")
    for r in runs[:3]:
        print(f"    Run: {r.get('id')} model={r.get('model')} provider={r.get('provider')} brandMentioned={r.get('brandMentioned')} createdAt={r.get('createdAt')}")
        print(f"    Keys: {list(r.keys())}")
else:
    print(f"  Body: {body[:300]}")

# T6: Runs — single
print("\n[T6] GET /api/v1/prompts/{id}/runs/{runId}")
# First get a run ID
status, ct, body = api_get(f"/api/v1/prompts/{PID}/runs?page=1&limit=1")
if status == 200 and "json" in ct:
    data = json.loads(body)
    runs = data.get("data", [])
    if runs:
        rid = runs[0].get("id")
        s2, ct2, b2 = api_get(f"/api/v1/prompts/{PID}/runs/{rid}")
        print(f"  Status: {s2}, Content-Type: {ct2}")
        if s2 == 200 and "json" in ct2:
            run_data = json.loads(b2)
            print(f"  Run keys: {list(run_data.keys())}")
            print(f"  Answer keys: {list(run_data.get('answer',{}).keys())}")
            print(f"  Citations count: {len(run_data.get('citations',[]))}")
            if run_data.get("citations"):
                print(f"  Citation keys: {list(run_data['citations'][0].keys())}")
                print(f"  Sample citation: {json.dumps(run_data['citations'][0], ensure_ascii=False)[:200]}")
            print(f"  Answer text (first 200): {str(run_data.get('answer',{}).get('text',''))[:200]}")
        else:
            print(f"  Body: {b2[:300]}")
    else:
        print("  No runs found yet (worker may not have executed)")

# T7: Trigger a run
print("\n[T7] POST /api/v1/prompts/{id}/runs (trigger manual run)")
status, ct, body = api_post(f"/api/v1/prompts/{PID}/runs")
print(f"  Status: {status}, Content-Type: {ct}")
if "json" in ct:
    print(f"  Response: {body[:300]}")
else:
    print(f"  Response: {body[:200]}")

# Summary
print("\n" + "=" * 60)
print("API Exploration Complete")
print("=" * 60)
