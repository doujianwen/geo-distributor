"""为官网（WordPress）账号写入工作区成员权限 —— 幂等，可重复执行。

用途：生产部署时，把「官网账号」与「工作区角色」绑定起来。
      身份真源仍是 api/personal_identity.py 的身份库，本脚本只是按其
      subject 规则写入记录，不引入第二套认证。

用法（需先注入 GEO_IDENTITY_DB / GEO_IDENTITY_SECRET / GEO_IDENTITY_ISSUER）：
    .venv/bin/python scripts/seed_identity_memberships.py \
        5:DEMO-GEO:DISTRIBUTOR_ADMIN: \
        6:DEMO-GEO:END_CUSTOMER:DEMO-CLI-1

每个参数格式： <WordPress用户ID>:<租户>:<角色>:<绑定客户ID或空>
"""
import hashlib
import json
import sys
import time
from pathlib import Path

# 允许直接以 `python scripts/xxx.py` 方式运行（不依赖调用方设置 PYTHONPATH）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.personal_identity import connect, configured


def subject_for(issuer: str, user_id: str) -> str:
    return "wp:" + hashlib.sha256(issuer.encode()).hexdigest()[:20] + ":" + user_id


def parse(spec: str):
    parts = spec.split(":")
    if len(parts) != 4:
        raise SystemExit(f"参数格式错误：{spec}（应为 id:tenant:role:client）")
    user_id, tenant, role, client = (p.strip() for p in parts)
    return user_id, tenant, role, (client or None)


def main(argv):
    if not configured():
        raise SystemExit("身份桥接未配置：请先注入 GEO_IDENTITY_DB / GEO_IDENTITY_SECRET / GEO_IDENTITY_ISSUER")
    import os

    issuer = os.environ["GEO_IDENTITY_ISSUER"].rstrip("/")
    now = int(time.time())
    conn = connect()
    try:
        for spec in argv:
            user_id, tenant, role, client = parse(spec)
            subject = subject_for(issuer, user_id)
            conn.execute(
                "INSERT OR IGNORE INTO identity_people VALUES(?,?,?,?)",
                (subject, issuer, user_id, now),
            )
            conn.execute(
                "INSERT INTO identity_memberships VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(subject) DO UPDATE SET tenant=excluded.tenant, role=excluded.role, "
                "client=excluded.client, enabled=excluded.enabled, "
                "revision=identity_memberships.revision+1",
                (subject, tenant, role, client, 1, 1),
            )
            conn.execute(
                "INSERT INTO identity_requests VALUES(?,'approved',?) "
                "ON CONFLICT(subject) DO UPDATE SET status='approved'",
                (subject, now),
            )
            detail = json.dumps(
                {"tenant": tenant, "role": role, "client": client, "enabled": True},
                ensure_ascii=False,
            )
            conn.execute(
                "INSERT INTO identity_events(subject,actor,operation,detail,created_at) "
                "VALUES(?,?,?,?,?)",
                (subject, "deploy/seed-memberships", "membership", detail, now),
            )
            # 权限变更后旧会话必须失效。
            conn.execute("DELETE FROM identity_sessions WHERE subject=?", (subject,))
            print(f"[OK] wp-user {user_id} -> {tenant}/{role}/client={client}  subject={subject}")
        conn.commit()
        print("\n-- 当前成员权限 --")
        for row in conn.execute(
            "SELECT m.subject, m.tenant, m.role, m.client, m.enabled, r.status "
            "FROM identity_memberships m LEFT JOIN identity_requests r ON r.subject=m.subject"
        ):
            print(dict(row))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv[1:])
