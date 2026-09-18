"""Client 模型（Sprint 2 — P0 补全，Audit 标记为 ABSENT）。

一个 Client 属于一个 Tenant（Distributor），是商业交付的客户实体。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class Client:
    """Client — 商业客户实体。

    一个 Tenant（Distributor）可以服务多个 Client。
    每个 Client 下可以有多个 Project。
    """
    client_id: str
    tenant_id: str
    name: str
    industry: str = ""
    website: str = ""
    contact_email: str = ""
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "client_id": self.client_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "industry": self.industry,
            "website": self.website,
            "contact_email": self.contact_email,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Client":
        """从 to_dict() 输出还原（持久化层用）。"""
        return cls(
            client_id=data["client_id"],
            tenant_id=data["tenant_id"],
            name=data.get("name", ""),
            industry=data.get("industry", ""),
            website=data.get("website", ""),
            contact_email=data.get("contact_email", ""),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at") or datetime.now().isoformat(),
            metadata=data.get("metadata") or {},
        )
