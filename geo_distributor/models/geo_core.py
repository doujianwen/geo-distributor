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

    在 Observation 和 Measurement 之间，作为前置输入。
    """
    evidence_id: str
    observation_id: str
    source_type: str  # screenshot / url / text_quote / citation
    content: str
    credibility_score: float = 1.0  # 0-1
    level: EvidenceLevel = EvidenceLevel.E1
    verified_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "observation_id": self.observation_id,
            "source_type": self.source_type,
            "content": self.content,
            "credibility_score": self.credibility_score,
            "level": self.level.value,
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
