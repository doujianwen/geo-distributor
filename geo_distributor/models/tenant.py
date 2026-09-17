"""租户与身份模型（Sprint 0 — P0）。

实现原则：
- 每个 Distributor 是独立 Tenant
- 技术真相（HQ）与商业视图（Portal）分离
- 数据隔离从 ID 层开始，不依赖权限绕过
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum, auto


class TenantStatus(Enum):
    ACTIVE = "active"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


@dataclass
class Tenant:
    """Distributor 租户实体。

    一个 Distributor = 一个 Tenant。
    Tenant 是数据隔离的最小单位。
    """
    tenant_id: str          # 如 "DST-001"
    name: str               # Distributor 名称
    contact_email: str
    status: TenantStatus = TenantStatus.ACTIVE
    plan: str = "standard"  # standard / enterprise / pilot
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status in (TenantStatus.ACTIVE, TenantStatus.TRIAL)


class UserRole(Enum):
    DISTRIBUTOR_ADMIN = "distributor_admin"
    DISTRIBUTOR_USER = "distributor_user"
    HQ_TECHNICAL = "hq_technical"
    HQ_MANAGEMENT = "hq_management"
    CLIENT_VIEWER = "client_viewer"


@dataclass
class User:
    """系统用户（Distributor 或 HQ 成员）。

    用户属于 Tenant，但不能跨 Tenant 访问数据。
    """
    user_id: str            # 如 "USR-001"
    tenant_id: str
    email: str
    role: UserRole
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AuditEntry:
    """审计日志条目（P0 必须）。

    记录所有关键操作，支持事后追溯。
    """
    audit_id: str
    tenant_id: str
    user_id: str
    action: str             # CREATE / UPDATE / DELETE / TRANSITION / VIEW
    resource_type: str      # REQUEST / PROJECT / SCOPE / REPORT
    resource_id: str
    old_value: Optional[dict] = None
    new_value: Optional[dict] = None
    ip_address: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "audit_id": self.audit_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }
