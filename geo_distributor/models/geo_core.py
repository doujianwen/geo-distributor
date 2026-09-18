"""GEO Core 链路模型（Evidence/Measurement/Diagnosis/Report）。

基于 ADR-007 Evidence First 和 08-统一状态机。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum, auto


class EvidenceLevel(Enum):
    E0 = "e0_idea"
    E1 = "e1_single_observation"
    E2 = "e2_repeated_observation"
    E3 = "e3_observed_effect"
    E4 = "e4_controlled"


class ReportType(Enum):
    TECHNICAL = "technical_report"
    CLIENT = "client_report"


@dataclass
class Evidence:
    """Evidence — 可验证证据链（ADR-007 核心）。

    **权威定义**（P1-1 统一）：原先 models/evidence.py 与 models/geo_core.py
    各有一份 Evidence 定义，字段不一致导致调用方需二选一。现合并于此：
    - 保留 geo_core 的 EvidenceLevel 分级（E0–E4，ADR-007 证据强度）
    - 吸收 evidence.py 的 url / metadata 字段
    - models/evidence.py 退化为 re-export 兼容层，不再重复定义

    在 Observation 和 Measurement 之间，作为前置输入。
    """
    evidence_id: str
    observation_id: str
    source_type: str = ""   # screenshot / url / text_quote / citation / raw_output_excerpt / competitor_mention
    content: str = ""
    url: str = ""
    credibility_score: float = 0.0  # 0-1，由 Measurement 层计算；未提供时为 0 而非 1（不可默认采信）
    level: EvidenceLevel = EvidenceLevel.E1
    verified_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 兼容从 dict/JSON 反序列化时 level 为字符串（如 mock.py 生成的 "E2"）
        if isinstance(self.level, str):
            try:
                self.level = EvidenceLevel(self.level)
            except ValueError:
                # 允许 "E2" 这类简写
                by_code = {e.name: e for e in EvidenceLevel}
                self.level = by_code.get(self.level.upper(), EvidenceLevel.E1)

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        """从 dict 构造（容忍缺失字段与字符串 level）。"""
        known = {
            "evidence_id", "observation_id", "source_type", "content", "url",
            "credibility_score", "level", "verified_at", "created_at", "metadata",
        }
        payload = {k: v for k, v in data.items() if k in known}
        return cls(**payload)

    def to_dict(self) -> dict:
        """序列化。注意：metadata 为内部字段，不出现在对外输出中。"""
        return {
            "evidence_id": self.evidence_id,
            "observation_id": self.observation_id,
            "source_type": self.source_type,
            "content": self.content,
            "url": self.url,
            "credibility_score": self.credibility_score,
            "level": self.level.value if isinstance(self.level, EvidenceLevel) else str(self.level),
            "verified_at": self.verified_at,
            "created_at": self.created_at,
        }


@dataclass
class ReportVersion:
    """报告版本（P0 必须，支持追溯）。"""
    version: int
    report_id: str
    content: dict
    generated_at: str
    is_client_safe: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "is_client_safe": self.is_client_safe,
            "notes": self.notes,
        }


@dataclass
class Report:
    """报告 — 双报告模型。

    Technical Report: 完整技术记录，仅供 HQ 内部。
    Client Report: Client-safe 投影，供 Distributor/Client 消费。
    """
    report_id: str
    project_id: str
    tenant_id: str
    type: ReportType
    title: str = ""
    versions: List[ReportVersion] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_version(self, content: dict, is_client_safe: bool = True, notes: str = ""):
        """添加新版本（版本递增，旧版本保留）。

        Client-safe报告会自动过滤敏感字段。
        """
        if not self.versions:
            version_num = 1
        else:
            version_num = max(v.version for v in self.versions) + 1

        # Client-safe过滤：移除技术内部字段
        filtered_content = content.copy()
        if is_client_safe:
            # 移除不应暴露给客户端的字段
            sensitive_keys = {"raw_response", "parser_output", "provider_internals",
                             "browser_logs", "query_internals", "validity_internals",
                             "evidence_grading", "technical_notes"}
            for key in sensitive_keys:
                filtered_content.pop(key, None)
        else:
            filtered_content = content

        self.versions.append(ReportVersion(
            version=version_num,
            report_id=self.report_id,
            content=filtered_content,
            generated_at=datetime.now().isoformat(),
            is_client_safe=is_client_safe,
            notes=notes,
        ))
        self.updated_at = datetime.now().isoformat()

    def get_latest_version(self) -> Optional[ReportVersion]:
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "project_id": self.project_id,
            "tenant_id": self.tenant_id,
            "type": self.type.value,
            "title": self.title,
            "latest_version": self.get_latest_version().to_dict() if self.get_latest_version() else None,
            "total_versions": len(self.versions),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
