"""Evidence 层模型（ADR-007 Evidence First Architecture）。

Evidence 是对 Observation 的可验证支撑：
- 引用原文摘录
- URL 来源
- 可信度评分
- 可追溯性（从 Provider -> Prompt -> Observation -> Evidence）

位置：Observation → Evidence → Measurement → Diagnosis
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Evidence:
    """GEO 证据记录。

    每条 Evidence 追溯到一个具体的来源（Citation / Raw Output / Competitor Mention），
    使 Measurement 和 Diagnosis 的结论可被验证。
    """
    evidence_id: str
    observation_id: str
    source_type: str = ""  # "citation" | "raw_output_excerpt" | "competitor_mention"
    content: str = ""      # 引用的实际文本
    url: str = ""
    credibility_score: float = 0.0  # 0.0-1.0，由 Measurement 层计算
    verified_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "observation_id": self.observation_id,
            "source_type": self.source_type,
            "content": self.content,
            "url": self.url,
            "credibility_score": self.credibility_score,
            "verified_at": self.verified_at,
        }
