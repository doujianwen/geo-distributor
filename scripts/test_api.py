"""Quick API exploration script."""
import json, os, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8')
# 密钥从环境变量读取，不再硬编码（避免明文泄漏到仓库）
key = os.getenv("ELMO_API_KEY", "")
if not key:
    sys.exit("[ERROR] ELMO_API_KEY 未设置，请先 export ELMO_API_KEY=...")
pid = '7e64e741-b090-467f-a2e4-8106b186634e'

# Test runs endpoint with proper params
for path in [f'/api/v1/prompts/{pid}/runs?page=1&limit=1', f'/api/v1/prompts/{pid}/runs?page=1&limit=1&start=2026-01-01&end=2026-12-31']:
    req = urllib.request.Request(f'http://localhost:1515{path}', headers={'Authorization': f'Bearer {key}'})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        ct = resp.headers.get('Content-Type', '')
        body = resp.read().decode()
        print(f'GET {path} -> {resp.status} ({ct})')
        print(body[:300])
    except urllib.error.HTTPError as e:
        ct = e.headers.get('Content-Type', '')
        is_json = 'json' in ct
        body = e.read().decode()[:200]
        label = 'json' if is_json else 'html'
        print(f'GET {path} -> {e.code} ({label})')
        if is_json:
            print(body)
    print()
