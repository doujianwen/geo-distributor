"""GeoCollectorDBAdapter — 直接读取 geo-collector SQLite 数据库。

与 ElmoAdapter / GeoCollectorAdapter 的区别：
- 不 import geo-collector Python 模块（避免 sys.path 冲突）
- 不发起 HTTP 请求（无网络依赖）
- 直接通过 sqlite3 查询 observations + citations + competitors
- 数据来自已采集的持久化存储（snapshot-based，非实时）

典型使用：
    adapter = GeoCollectorDBAdapter(
        db_path="E:/GEO项目/技术层/geo-collector/geo_collector.db",
        brand="Hydroviv",
    )
    observations = await adapter.collect_batch(prompts)
"""

from __future__ import annotations
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

from ..compatibility.base import PlatformObservation
from ..models import Prompt
from .base import BaseAdapter

logger = logging.getLogger(__name__)


def _normalize_prompt_text(text: str) -> str:
    """归一化 prompt 文本用于比对（忽略大小写/空白/句末标点差异）。"""
    import re

    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = t.rstrip("?.!。？！ ")
    return t


# 字段名映射：DB 列名 → PlatformObservation 字段
_OBS_MAP = {
    "observation_id": "observation_id",
    "prompt_id": "prompt_id",
    "engine": "engine",
    "timestamp": "timestamp",
    "prompt_text": "prompt_text",
    "answer_raw": "answer_raw",
    "answer_clean": "answer_clean",
    "answer_char_count": "answer_char_count",
    "extraction_method": "answer_extraction_method",
    "validation_status": "answer_validation_status",
    "brand": "brand",
    "brand_mentioned": "brand_mentioned",
    "brand_status": "brand_status",
    "first_mention_position": "first_mention_position",
    "recommendation_level": "recommendation_level",
    "recommendation_rank": "recommendation_rank",
    "recommendation_evidence": "recommendation_evidence",
    "citations_status": "citations_status",
    "status": "status",
}


def _json_safe(val: Any) -> Any:
    """安全地将 SQLite TEXT 列转为 Python 对象。"""
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return []
    return val


def _obs_row_to_platform(row: sqlite3.Row, brand: str) -> PlatformObservation:
    """将 DB 行映射为 PlatformObservation。"""
    def col(name: str) -> Any:
        return row[name]

    brand_mentioned = bool(col("brand_mentioned"))
    # 优先用 v2 字段（最新重处理结果），回退到 v1
    rec_level = col("recommendation_level_v2") if col("recommendation_level_v2") is not None else col("recommendation_level")
    rec_rank = col("recommendation_rank_v2") if col("recommendation_rank_v2") is not None else col("recommendation_rank")
    first_pos = col("first_mention_position_v2") if col("first_mention_position_v2") is not None else col("first_mention_position")
    mentioned_v2 = col("brand_mentioned_v2")
    if mentioned_v2 is not None:
        brand_mentioned = bool(mentioned_v2)

    return PlatformObservation(
        observation_id=col("observation_id"),
        prompt_id=col("prompt_id"),
        engine=col("engine") or "",
        timestamp=col("timestamp") or "",
        prompt_text=col("prompt_text") or "",
        answer_raw=col("answer_raw") or "",
        answer_clean=col("answer_clean") or "",
        answer_char_count=col("answer_char_count") or 0,
        extraction_method=col("answer_extraction_method") or "",
        validation_status=col("answer_validation_status") or "",
        brand=brand,
        brand_mentioned=brand_mentioned,
        brand_status=col("brand_status") or "UNKNOWN",
        first_mention_position=first_pos,
        recommendation_level=int(rec_level) if rec_level is not None else -1,
        recommendation_rank=int(rec_rank) if rec_rank is not None else None,
        recommendation_evidence=col("recommendation_evidence") or "",
        competitors=_json_safe(col("competitors")),
        citations=[],  # 通过 JOIN 单独查询
        citations_status=col("citations_status") or "unavailable",
        status=col("status") or "success",
        raw_metadata={
            "parser_version": col("parser_version"),
            "answer_validation_status": col("answer_validation_status"),
            "response_state": col("response_state"),
        },
    )


class GeoCollectorDBAdapter(BaseAdapter):
    """直接读取 geo-collector SQLite 数据库的适配器。

    数据特征：
    - 快照式采集（非实时），适合回溯和基线测量
    - 支持按 brand + prompt_id + engine 精确查询
    - 失败时返回 empty result，不伪造数据
    """

    def __init__(
        self,
        db_path: str,
        brand: str = "Hydroviv",
        min_recommendation_level: int = 0,
        strict_prompt_match: bool = True,
    ):
        """
        Args:
            db_path: geo-collector.db 绝对路径
            brand: 目标品牌名（用于过滤 observations）
            min_recommendation_level: 最低推荐级别（默认 0 = 全部）
            strict_prompt_match: 是否校验 prompt_id 与 prompt_text 一致。
                默认开启——适配器按 prompt_id 查库，若调用方传入的
                prompt_id 与 text 不是同一条（如 prompts 文件用了自建
                编号），会把别的问题的观测当成这条的答案返回，产出
                "采集成功但数字张冠李戴"的假结果。
        """
        self.db_path = db_path
        self.brand = brand
        self.min_rec_level = min_recommendation_level
        self.strict_prompt_match = strict_prompt_match

    # ------------------------------------------------------------------
    # BaseAdapter 契约
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM observations")
            count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT engine) FROM observations")
            engines = cur.fetchone()[0]
            conn.close()
            logger.info("GeoCollectorDB health: %d obs, %d engines", count, engines)
            return count > 0
        except Exception as e:
            logger.error("GeoCollectorDB health check failed: %s", e)
            return False

    async def collect_prompt(self, prompt: Prompt) -> PlatformObservation:
        """按 prompt_id 查询单次观测。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            # 查询主观测
            cur.execute(
                """SELECT * FROM observations
                   WHERE prompt_id = ?
                     AND (brand = ? OR brand = '')
                     AND (recommendation_level >= ? OR ? = 0)
                   ORDER BY timestamp DESC
                   LIMIT 1""",
                (prompt.prompt_id, self.brand, self.min_rec_level, self.min_rec_level),
            )
            row = cur.fetchone()
            if not row:
                return self._empty_obs(prompt)

            # ⚠️ prompt_id 与 prompt_text 一致性校验。
            # 库里 prompt_id=1 是"What water filter should I buy based on
            # my local water quality?"，而某些 prompts 文件里 prompt_id=1
            # 是"best water filter for home"。只按 ID 查会把前者的观测
            # 当成后者的答案——Run 显示 10/10 成功、提及率却衡量的是
            # 另一批问题。这里直接判为 prompt_mismatch，由上层记账。
            if self.strict_prompt_match:
                expected = _normalize_prompt_text(getattr(prompt, "text", "") or "")
                actual = _normalize_prompt_text(row["prompt_text"] or "")
                if expected and actual and expected != actual:
                    return self._mismatch_obs(prompt, row["prompt_text"] or "")

            obs = _obs_row_to_platform(row, self.brand)

            # 查询 citations
            cur.execute(
                "SELECT url, domain, title, citation_index, citation_type, anchor_text, context "
                "FROM citations WHERE observation_id = ?",
                (obs.observation_id,),
            )
            obs.citations = [
                {
                    "url": r["url"],
                    "domain": r["domain"],
                    "title": r["title"],
                    "citation_index": r["citation_index"],
                    "citation_type": r["citation_type"],
                    "anchor_text": r["anchor_text"] or "",
                    "context": r["context"] or "",
                }
                for r in cur.fetchall()
            ]
            if obs.citations:
                obs.citations_status = "extracted"

            # 查询 competitors
            cur.execute(
                "SELECT brand, position FROM competitors WHERE observation_id = ?",
                (obs.observation_id,),
            )
            obs.competitors = [
                {"name": r["brand"], "position": r["position"]}
                for r in cur.fetchall()
            ]

            return obs
        finally:
            conn.close()

    async def collect_batch(
        self,
        prompts: List[Prompt],
        progress_callback=None,
    ) -> List[PlatformObservation]:
        """批量查询所有 prompts 的观测。"""
        results: List[PlatformObservation] = []
        for i, prompt in enumerate(prompts):
            obs = await self.collect_prompt(prompt)
            results.append(obs)
            if progress_callback:
                progress_callback(i + 1, len(prompts))
        return results

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @classmethod
    def get_stats(cls, db_path: str) -> Dict[str, Any]:
        """返回数据库统计摘要（不绑定具体品牌）。"""
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        stats: Dict[str, Any] = {}
        try:
            cur.execute("SELECT COUNT(*) FROM observations")
            stats["total_observations"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM prompts")
            stats["total_prompts"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT engine) FROM observations")
            stats["engines"] = [r[0] for r in cur.execute("SELECT DISTINCT engine FROM observations").fetchall()]
            cur.execute("SELECT COUNT(DISTINCT brand) FROM observations WHERE brand != ''")
            stats["brands"] = [r[0] for r in cur.execute("SELECT DISTINCT brand FROM observations WHERE brand != ''").fetchall()]
            cur.execute("SELECT COUNT(*) FROM observations WHERE status = 'success'")
            stats["successful"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM observations WHERE brand_mentioned = 1")
            stats["brand_mentioned"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM observations WHERE recommendation_level >= 2")
            stats["brand_recommended"] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM citations")
            stats["total_citations"] = cur.fetchone()[0]
        finally:
            conn.close()
        return stats

    def _mismatch_obs(self, prompt: Prompt, db_text: str) -> PlatformObservation:
        """prompt_id 命中但文本对不上时返回透明观测（不返回错配数据）。"""
        obs = self._empty_obs(prompt)
        obs.status = "prompt_mismatch"
        obs.brand_status = "PROMPT_MISMATCH"
        obs.raw_metadata = {
            "note": "prompt_id matched but prompt_text differs; refusing to return mismatched data",
            "expected_text": getattr(prompt, "text", "") or "",
            "db_text": db_text,
        }
        return obs

    def _empty_obs(self, prompt: Prompt) -> PlatformObservation:
        """无匹配数据时返回透明观测（不伪造）。"""
        return PlatformObservation(
            observation_id=f"missing_{prompt.prompt_id}",
            prompt_id=prompt.prompt_id,
            engine="geo-collector-db",
            timestamp="",
            prompt_text=getattr(prompt, "text", "") or "",
            answer_raw="",
            answer_clean="",
            answer_char_count=0,
            extraction_method="db_query",
            validation_status="PASS",
            brand=self.brand,
            brand_mentioned=False,
            brand_status="NOT_COLLECTED",
            first_mention_position=None,
            recommendation_level=-1,
            recommendation_rank=None,
            recommendation_evidence="",
            competitors=[],
            citations=[],
            citations_status="unavailable",
            status="not_collected",
            raw_metadata={"note": "no observation found in geo-collector.db"},
        )
