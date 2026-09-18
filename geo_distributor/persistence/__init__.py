"""持久化层（P0-5）。

背景
----
Sprint 0 起所有仓储都是 `InMemoryRepository`——进程重启即失。对 API 服务而言
这意味着"重启后客户、项目、四阶段进度全部归零"，无法进入真实使用。

方案
----
基于 Python 内置 `sqlite3` 实现仓储（**零新增依赖**），与 InMemory 仓储
保持完全相同的 async 接口，可通过开关切换：

- 环境变量 `GEO_DISTRIBUTOR_DB` 指向 .db 文件路径 → 启用 SQLite
- 未设置 → 保持 InMemory（默认，行为与之前完全一致）

存储格式
--------
统一表结构 `(id, tenant_id, payload_json, updated_at)`：
- `id` / `tenant_id` 提出来建索引，支撑租户隔离查询
- 实体整体以 JSON 存 `payload`（schema 演进友好，不需要迁移列）
- 枚举/嵌套对象通过各模型的 `from_dict()` / `to_dict()` 还原

已知限制（MVP 可接受）
----------------------
- 非分布式：单进程/单机适用；多副本部署需换 Postgres
- 每次操作新建连接（简单可靠，非高频场景足够）
"""

from .sqlite_repository import (
    SQLiteRepository,
    SQLiteClientRepository,
    SQLiteProjectRepository,
    SQLiteRequestRepository,
    get_default_db_path,
    is_persistence_enabled,
    resolve_db_path,
)

__all__ = [
    "SQLiteRepository",
    "SQLiteClientRepository",
    "SQLiteProjectRepository",
    "SQLiteRequestRepository",
    "get_default_db_path",
    "is_persistence_enabled",
    "resolve_db_path",
]
