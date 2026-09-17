"""Elmo → PlatformObservation 映射层（ADR-007 Evidence First）。

将 Elmo REST API 响应转换为 PlatformObservation。
核心原则：
- 保留原始数据在 raw_metadata 中
- 所有计算在 Mapping 层完成，不依赖 Elmo 内部结构
- Citation type 通过域名规则推断
- prompt_id 使用 md5 哈希转 int，原始 UUID 存入 raw_metadata
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Citation type inference rules
# ------------------------------------------------------------------

_CITATION_TYPE_RULES = [
    # (A: Brand-owned) — 匹配品牌域名
    ("A", lambda domain, brand_domains: any(
        domain == bd or domain.endswith("." + bd) for bd in brand_domains
    )),
    # (B: Authority) — .gov / .edu / .org
    ("B", lambda domain, brand_domains: any(domain.endswith(ext) for ext in (".gov", ".edu", ".org"))),
    # (C: Editorial) — 新闻/媒体域名关键词
    ("C", lambda domain, brand_domains: any(kw in domain for kw in (
        "news", "times", "post", "daily", "weekly", "press", "journal", "review", "magazine"
    ))),
    # (D: Community) — forum/social
    ("D", lambda domain, brand_domains: any(kw in domain for kw in (
        "reddit", "forum", "community", "stack", "quip", "discord",
        "twitter", "facebook", "linkedin",
    ))),
    # (E: Commercial) — 其余
    ("E", lambda domain, brand_domains: True),
]


def _infer_citation_type(url: str, domain: str, brand_domains: List[str]) -> str:
    """根据 URL/domain 推断 citation type (A/B/C/D/E)。"""
    for type_label, rule_fn in _CITATION_TYPE_RULES:
        if rule_fn(domain, brand_domains):
            return type_label
    return "E"


# ------------------------------------------------------------------
# Prompt ID: UUID → int
# ------------------------------------------------------------------

def _uuid_to_int(prompt_uuid: str) -> int:
    """将 Elmo prompt UUID 转为 int，原始 UUID 保留在 raw_metadata 中。

    使用 md5 哈希前 8 字节转 int，保证同值同哈希、不同值极大概率不同。
    """
    try:
        return int(hashlib.md5(prompt_uuid.encode()).hexdigest()[:8], 16) % (2 ** 31)
    except Exception:
        # 兜底：使用创建时间 hash
        return int(hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:8], 16) % (2 ** 31)


# ------------------------------------------------------------------
# Answer extraction helpers
# ------------------------------------------------------------------

def _extract_answer_text(run: dict) -> str:
    """从 Elmo run 中提取纯文本回答。

    Elmo answer 可能是嵌套结构（如 {"text": "...", "raw": "..."}），
    这里做安全降级处理。
    """
    answer = run.get("answer") or {}
    # 优先取 text 字段
    text = answer.get("text", "")
    if not text:
        # 尝试 raw_output 中的文本
        raw = run.get("raw_output") or {}
        if isinstance(raw, dict):
            text = raw.get("text", "") or raw.get("content", "")
        elif isinstance(raw, str):
            text = raw
    return text or ""


# ------------------------------------------------------------------
# map_elmo_citation_to_platform
# ------------------------------------------------------------------

def map_elmo_citation_to_platform(
    citation: dict,
    observation_id: str,
    brand_domains: List[str],
) -> Dict[str, Any]:
    """将 Elmo citation dict 映射为 Platform 兼容的 dict。

    Args:
        citation: Elmo API 返回的单条 citation
        observation_id: 对应的 PlatformObservation.observation_id
        brand_domains: 品牌域名列表，用于推断 citation_type

    Returns:
        dict，字段与 PlatformCitation 对齐
    """
    url = citation.get("url", "")
    domain = citation.get("domain", "") or (url.split("//")[-1].split("/")[0] if url else "")

    return {
        "observation_id": observation_id,
        "url": url,
        "domain": domain,
        "title": citation.get("title", ""),
        "citation_index": citation.get("citationIndex", citation.get("index", 0)),
        "citation_type": _infer_citation_type(url, domain, brand_domains),
        "anchor_text": citation.get("anchorText", citation.get("anchor_text", "")),
        "context": citation.get("context", ""),
    }


# ------------------------------------------------------------------
# map_elmo_to_platform
# ------------------------------------------------------------------

def map_elmo_to_platform(
    elmo_run: dict,
    elmo_citations: List[dict],
    brand_name: str,
    brand_domains: List[str],
    prompt_id_uuid: str,
    model_name: str,
    elmo_version: str,
) -> Dict[str, Any]:
    """将 Elmo run + citations 映射为 PlatformObservation dict。

    Args:
        elmo_run: GET /api/v1/prompts/{id}/runs/{runId} 返回的 dict
        elmo_citations: list of citation dicts
        brand_name: 品牌名称（来自 GET /brands/{id}）
        brand_domains: 品牌域名列表
        prompt_id_uuid: Elmo prompt 的 UUID
        model_name: AI 模型名（如 "gpt-4o"）
        elmo_version: 锁定的 Elmo 版本

    Returns:
        PlatformObservation 兼容的 dict
    """
    run_id = str(elmo_run.get("id", ""))
    created_at = elmo_run.get("createdAt", elmo_run.get("created_at", ""))

    # 提取回答文本
    answer_clean = _extract_answer_text(elmo_run)
    answer_raw = elmo_run.get("raw_output", "")
    if isinstance(answer_raw, dict):
        answer_raw = str(answer_raw)

    # 映射 citations
    mapped_citations = [
        map_elmo_citation_to_platform(c, run_id, brand_domains)
        for c in elmo_citations
    ]

    # brand 相关
    brand_mentioned = elmo_run.get("brandMentioned", elmo_run.get("brand_mentioned", False))
    brand_status = "MENTIONED" if brand_mentioned else "NOT_MENTIONED"

    # competitors
    competitors_raw = elmo_run.get("competitorsMentioned", elmo_run.get("competitors_mentioned", []))
    competitors = [{"name": c} if isinstance(c, str) else c for c in competitors_raw]

    # prompt_text: 从 run 中提取或留空（需额外 API 调用获取 prompt value）
    prompt_text = elmo_run.get("prompt", "") or elmo_run.get("prompt_value", "")

    # prompt_id: UUID → int
    prompt_id_int = _uuid_to_int(prompt_id_uuid)

    # citations_status
    citations_status = "extracted" if mapped_citations else "unavailable"

    # status
    status = "success" if answer_clean else "failed"

    # validation_status
    validation_status = "PASS" if answer_clean else "FAIL"

    return {
        "observation_id": run_id,
        "prompt_id": prompt_id_int,
        "engine": model_name,
        "timestamp": created_at,
        "prompt_text": prompt_text,
        "answer_raw": answer_raw,
        "answer_clean": answer_clean,
        "answer_char_count": len(answer_clean),
        "extraction_method": "elmo_api",
        "validation_status": validation_status,
        "brand": brand_name,
        "brand_mentioned": brand_mentioned,
        "brand_status": brand_status,
        "first_mention_position": None,  # Elmo 未提供，由 Measurement 层补充
        "recommendation_level": -1,  # 由 Measurement 层计算
        "recommendation_rank": None,
        "recommendation_evidence": "",
        "competitors": competitors,
        "citations": mapped_citations,
        "citations_status": citations_status,
        "status": status,
        "raw_metadata": {
            "provider": "elmo",
            "version": elmo_version,
            "elmo_version": elmo_version,
            "original_prompt_id": prompt_id_uuid,
            "original_run_id": run_id,
            "web_search_enabled": elmo_run.get("webSearchEnabled", elmo_run.get("web_search_enabled", False)),
            "model": model_name,
        },
    }
