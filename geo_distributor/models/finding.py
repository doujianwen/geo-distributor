"""Finding 模型（V2 新增）。

Finding 是 Measurement → Opportunity → Action 链条的关键节点。
每个 Finding 追溯到一个或多个 Observation，包含可执行的优化建议。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum, auto


class FindingSeverity(Enum):
    """发现严重程度。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingCategory(Enum):
    """发现类别。"""
    VISIBILITY_GAP = "visibility_gap"           # 品牌提及缺失
    CITATION_QUALITY = "citation_quality"        # 引用来源质量差
    COMPETITIVE_DISADVANTAGE = "competitive"     # 竞品优势
    CONTENT_GAP = "content_gap"                  # 内容缺口
    ENTITY_WEAKNESS = "entity_weakness"          # 实体信息不足
    TECHNICAL_ISSUE = "technical_issue"          # 技术问题（Schema/EEAT）


@dataclass
class Finding:
    """GEO 诊断发现 — 从 Observation/Evidence 推导的可执行洞察。

    字段说明：
    - finding_id: 唯一标识（如 FND-20260918-001）
    - observation_ids: 关联的观测 ID 列表（可追溯到原始数据）
    - category: 发现类别（VISIBILITY_GAP / CITATION_QUALITY 等）
    - severity: 严重程度（CRITICAL / HIGH / MEDIUM / LOW / INFO）
    - statement: 人类可读的发现陈述
    - recommendation: 具体优化建议（可执行）
    - evidence_refs: 引用证据 ID 列表
    - confidence: 置信度（0.0-1.0）
    - priority_score: 优先级分数（impact × confidence / effort）
    - status: 状态（NEW / ANALYZING / RESOLVED / IGNORED）
    """
    finding_id: str
    observation_ids: List[str] = field(default_factory=list)
    category: FindingCategory = FindingCategory.VISIBILITY_GAP
    severity: FindingSeverity = FindingSeverity.MEDIUM
    statement: str = ""
    recommendation: str = ""
    evidence_refs: List[str] = field(default_factory=list)
    confidence: float = 0.5
    priority_score: float = 0.0
    status: str = "new"  # new / analyzing / resolved / ignored
    project_id: Optional[str] = None
    case_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_resolved(self) -> None:
        """标记为已解决。"""
        self.status = "resolved"
        self.updated_at = datetime.now().isoformat()

    def mark_ignored(self) -> None:
        """标记为已忽略。"""
        self.status = "ignored"
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典。"""
        return {
            "finding_id": self.finding_id,
            "observation_ids": self.observation_ids,
            "category": self.category.value,
            "severity": self.severity.value,
            "statement": self.statement,
            "recommendation": self.recommendation,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "priority_score": self.priority_score,
            "status": self.status,
            "project_id": self.project_id,
            "case_id": self.case_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        """从字典反序列化。"""
        return cls(
            finding_id=data["finding_id"],
            observation_ids=data.get("observation_ids", []),
            category=FindingCategory(data.get("category", "visibility_gap")),
            severity=FindingSeverity(data.get("severity", "medium")),
            statement=data.get("statement", ""),
            recommendation=data.get("recommendation", ""),
            evidence_refs=data.get("evidence_refs", []),
            confidence=data.get("confidence", 0.5),
            priority_score=data.get("priority_score", 0.0),
            status=data.get("status", "new"),
            project_id=data.get("project_id"),
            case_id=data.get("case_id"),
            metadata=data.get("metadata", {}),
        )
