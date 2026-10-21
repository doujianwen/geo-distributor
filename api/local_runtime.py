"""Local loopback port configuration; never opens a public listener."""
import json
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "config" / "portal_runtime.local.json"


def ports():
    result = {"local_port": 8765, "demo_port": 8767, "customer_acceptance_port": 8768, "growth_sandbox_port": 17669}
    if CONFIG.exists():
        configured = json.loads(CONFIG.read_text(encoding="utf-8"))
        if not isinstance(configured, dict) or any(k not in result for k in configured):
            raise ValueError("Invalid local port configuration")
        result.update(configured)
    if any(type(v) is not int or not 1024 <= v <= 65535 for v in result.values()) or len(set(result.values())) != len(result):
        raise ValueError("Local ports must be distinct integers in 1024..65535")
    return result


def demo_url(customer=False):
    return f"http://127.0.0.1:{ports()['demo_port']}/ui/" + ("customer/" if customer else "")
