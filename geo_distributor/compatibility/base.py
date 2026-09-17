"""Compatibility Layer — Platform Observation 统一契约。

A1.6 核心战场。

设计原则：
- 所有 Adapter（GeoCollectorAdapter / ElmoAdapter）最终输出同一个 PlatformObservation
- geo-collector 的数据通过映射函数转换，不直接暴露给上层
- Elmo 的数据通过另一个映射函数转换，共享同一契约
- 上游系统变更后，只改 mapping 函数，不动上层业务代码
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class PlatformObservation:
    """所有 Adapter 输出的统一格式。

    无论数据来自 geo-collector 还是未来的 Elmo，
    上层业务只看到 PlatformObservation。

    字段命名对齐 geo-collector 的 Observation dataclass，
    保证映射时不会丢失语义。
    """
    # --- 标识 ---
    observation_id: str
    prompt_id: int
    engine: str
    timestamp: str

    # --- 输入 ---
    prompt_text: str

    # --- 回答 ---
    answer_raw: str            # 原始 HTML 提取文本
    answer_clean: str          # 清洗后的纯文本
    answer_char_count: int
    extraction_method: str     # 如 "dom_traversal", "engine_specific_css"
    validation_status: str     # PASS / SUSPICIOUS / FAIL / CHANNEL_BLOCKED

    # --- 品牌 ---
    brand: str
    brand_mentioned: bool
    brand_status: str          # UNKNOWN / MENTIONED / NOT_MENTIONED
    first_mention_position: Optional[int]
    recommendation_level: int  # -1=UNKNOWN, 0=Not Mentioned, 1=Mentioned, 2=Considered, 3=Recommended, 4=Strongly Recommended
    recommendation_rank: Optional[int]
    recommendation_evidence: str

    # --- 竞品 ---
    competitors: List[Dict[str, Any]]

    # --- 引用 ---
    citations: List[Dict[str, Any]]
    citations_status: str      # unavailable / partial / extracted

    # --- 状态 ---
    status: str                # success / failed / channel_blocked

    # --- 原始元数据（保留，用于调试和未来扩展）---
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """序列化为 dict，供 JSON 导出或 API 响应使用。"""
        return {
            "observation_id": self.observation_id,
            "prompt_id": self.prompt_id,
            "engine": self.engine,
            "timestamp": self.timestamp,
            "prompt_text": self.prompt_text,
            "answer_raw": self.answer_raw,
            "answer_clean": self.answer_clean,
            "answer_char_count": self.answer_char_count,
            "extraction_method": self.extraction_method,
            "validation_status": self.validation_status,
            "brand": self.brand,
            "brand_mentioned": self.brand_mentioned,
            "brand_status": self.brand_status,
            "first_mention_position": self.first_mention_position,
            "recommendation_level": self.recommendation_level,
            "recommendation_rank": self.recommendation_rank,
            "recommendation_evidence": self.recommendation_evidence,
            "competitors": self.competitors,
            "citations": self.citations,
            "citations_status": self.citations_status,
            "status": self.status,
        }


@dataclass
class PlatformCitation:
    """统一 Citation 格式。"""
    observation_id: str
    url: str
    domain: str
    title: str
    citation_index: int
    citation_type: str       # A=Brand-owned, B=Authority, C=Editorial, D=Community, E=Commercial
    anchor_text: str
    context: str

    def to_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "citation_index": self.citation_index,
            "citation_type": self.citation_type,
            "anchor_text": self.anchor_text,
            "context": self.context,
        }


# ------------------------------------------------------------------
# 映射函数占位（V0.2 先实现 geo-collector → Platform，Elmo 待 V0.3）
# ------------------------------------------------------------------

def map_geo_collector_observation(obs: Any) -> PlatformObservation:
    """将 geo-collector 的 Observation 映射为 PlatformObservation。

    兼容两种格式：
    - geo-collector storage.models.Observation（字段名为 prompt, answer_extraction_method 等）
    - 本层 models.Observation（字段名为 prompt_text, extraction_method 等）

    Args:
        obs: 任意 Observation 对象，自动识别字段名

    Returns:
        PlatformObservation
    """
    def _get(attr, fallback=None):
        return getattr(obs, attr, fallback)

    return PlatformObservation(
        observation_id=_get("observation_id"),
        prompt_id=_get("prompt_id"),
        engine=_get("engine"),
        timestamp=_get("timestamp"),
        prompt_text=_get("prompt_text") or _get("prompt", ""),
        answer_raw=_get("answer_raw"),
        answer_clean=_get("answer_clean"),
        answer_char_count=_get("answer_char_count", 0),
        extraction_method=_get("extraction_method") or _get("answer_extraction_method", ""),
        validation_status=_get("validation_status") or _get("answer_validation_status", ""),
        brand=_get("brand"),
        brand_mentioned=_get("brand_mentioned", False),
        brand_status=_get("brand_status", "UNKNOWN"),
        first_mention_position=_get("first_mention_position"),
        recommendation_level=_get("recommendation_level", -1),
        recommendation_rank=_get("recommendation_rank"),
        recommendation_evidence=_get("recommendation_evidence", ""),
        competitors=_get("competitors", []),
        citations=_get("citations", []),
        citations_status=_get("citations_status", "unavailable"),
        status=_get("status", "success"),
    )


def map_geo_collector_citations(obs_citations: list) -> List[PlatformCitation]:
    """将 geo-collector 的 citation 列表映射为 PlatformCitation。"""
    result = []
    for i, c in enumerate(obs_citations, 1):
        result.append(PlatformCitation(
            observation_id="",  # 由调用方填充
            url=c.get("url", ""),
            domain=c.get("domain", ""),
            title=c.get("title", ""),
            citation_index=c.get("citation_index", i),
            citation_type=c.get("citation_type", ""),
            anchor_text=c.get("anchor_text", ""),
            context=c.get("context", ""),
        ))
    return result
