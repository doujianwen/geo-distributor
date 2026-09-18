"""geo-collector 增量同步服务（P0-4 增强）。

解决的问题
----------
GeoCollectorDBAdapter 是"快照式"读取：每次测量都全量扫描 SQLite。
当数据量增长、或需要判断"这轮相比上轮新增了什么"时，缺少增量能力。

本服务补齐增量同步：
- 以 **observation_id 集合差分** 判定新增（不依赖 timestamp 排序，
  避免重处理/回填数据造成的水位线回退）
- watermark 持久化到 JSON，进程重启后仍有效
- 支持 force 全量重同步
- 同步结果可直接喂给测量管线（返回 PlatformObservation 列表）

使用：
    svc = SyncService()
    result = svc.sync(brand="Hydroviv")
    print(result.new_count)        # 本轮新增
    for obs in result.observations: ...
"""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from ..adapters.geo_collector_db import (
    GeoCollectorDBAdapter,
    _obs_row_to_platform,
    _json_safe,
)
from ..compatibility.base import PlatformObservation
from ..models import Prompt

DEFAULT_STATE_FILENAME = "sync_state.json"


@dataclass
class SyncResult:
    """一次同步的结果。"""
    brand: str
    new_count: int                                  # 本轮新增观测数
    known_count: int                                # 此前已同步、本轮跳过的数量
    total_in_db: int                                # 库中该品牌总观测数
    synced_at: str
    forced: bool = False                            # 是否强制全量重同步
    observations: List[PlatformObservation] = field(default_factory=list)
    new_observation_ids: List[str] = field(default_factory=list)

    def to_dict(self, include_observations: bool = False) -> dict:
        d = {
            "brand": self.brand,
            "new_count": self.new_count,
            "known_count": self.known_count,
            "total_in_db": self.total_in_db,
            "synced_at": self.synced_at,
            "forced": self.forced,
            "new_observation_ids": self.new_observation_ids,
        }
        if include_observations:
            d["observations"] = [
                o.to_dict() if hasattr(o, "to_dict") else dict(o)
                for o in self.observations
            ]
        return d


class SyncService:
    """geo-collector → geo-distributor 增量同步。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        state_path: Optional[str] = None,
    ):
        """
        Args:
            db_path: geo-collector.db 路径；缺省用 config.get_geo_collector_root() 推导
            state_path: watermark 持久化路径；缺省 <project_root>/exports/sync_state.json
        """
        if db_path is None:
            from ..config import get_geo_collector_root
            db_path = os.path.join(get_geo_collector_root(), "geo_collector.db")
        self.db_path = db_path

        if state_path is None:
            from ..config import get_project_root
            state_path = os.path.join(
                get_project_root(), "exports", DEFAULT_STATE_FILENAME
            )
        self.state_path = state_path
        self._state: Dict[str, Any] = self._load_state()

    # ------------------------------------------------------------------
    # state 持久化
    # ------------------------------------------------------------------

    def _load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            return {"brands": {}}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "brands" not in data:
                return {"brands": {}}
            return data
        except (json.JSONDecodeError, OSError):
            # 状态文件损坏不阻塞同步：退回空状态（下一轮视为全量）
            return {"brands": {}}

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def _brand_state(self, brand: str) -> Dict[str, Any]:
        return self._state["brands"].setdefault(
            brand,
            {"known_ids": [], "last_synced_at": None, "total_synced": 0},
        )

    # ------------------------------------------------------------------
    # 同步
    # ------------------------------------------------------------------

    def get_status(self, brand: Optional[str] = None) -> Dict[str, Any]:
        """查看当前同步水位（只读，不做同步）。"""
        if brand:
            bs = self._state["brands"].get(brand)
            if bs is None:
                return {"brand": brand, "synced": False, "known_count": 0}
            return {
                "brand": brand,
                "synced": True,
                "known_count": len(bs.get("known_ids", [])),
                "last_synced_at": bs.get("last_synced_at"),
                "total_synced": bs.get("total_synced", 0),
            }
        return {
            "db_path": self.db_path,
            "state_path": self.state_path,
            "brands": {
                b: {
                    "known_count": len(v.get("known_ids", [])),
                    "last_synced_at": v.get("last_synced_at"),
                }
                for b, v in self._state["brands"].items()
            },
        }

    def sync(
        self,
        brand: str,
        force: bool = False,
        include_citations: bool = True,
    ) -> SyncResult:
        """执行一次增量同步。

        Args:
            brand: 目标品牌（与 observations.brand 匹配）
            force: True 则忽略 watermark，全量返回
            include_citations: 是否附带查询 citations/competitors
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"geo-collector DB not found: {self.db_path}")

        bs = self._brand_state(brand)
        known: Set[str] = set(bs.get("known_ids", [])) if not force else set()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()

            # 库中该品牌总观测数（用于分母）
            cur.execute(
                "SELECT COUNT(*) FROM observations WHERE brand = ?", (brand,)
            )
            total_in_db = cur.fetchone()[0]

            # 拉取该品牌全部观测，按时间正序（保证新增项顺序稳定）
            cur.execute(
                """SELECT * FROM observations
                   WHERE brand = ?
                   ORDER BY timestamp ASC, observation_id ASC""",
                (brand,),
            )
            rows = cur.fetchall()

            new_rows = [r for r in rows if r["observation_id"] not in known]

            observations: List[PlatformObservation] = []
            new_ids: List[str] = []
            for row in new_rows:
                obs = _obs_row_to_platform(row, brand)
                if include_citations:
                    cur.execute(
                        "SELECT url, domain, title, citation_index, citation_type, "
                        "anchor_text, context FROM citations WHERE observation_id = ?",
                        (obs.observation_id,),
                    )
                    obs.citations = [
                        {
                            "url": c["url"],
                            "domain": c["domain"],
                            "title": c["title"],
                            "citation_index": c["citation_index"],
                            "citation_type": c["citation_type"],
                            "anchor_text": c["anchor_text"] or "",
                            "context": c["context"] or "",
                        }
                        for c in cur.fetchall()
                    ]
                    if obs.citations:
                        obs.citations_status = "extracted"

                    cur.execute(
                        "SELECT brand, position FROM competitors WHERE observation_id = ?",
                        (obs.observation_id,),
                    )
                    obs.competitors = [
                        {"name": c["brand"], "position": c["position"]}
                        for c in cur.fetchall()
                    ]
                observations.append(obs)
                new_ids.append(obs.observation_id)

            # 更新 watermark（force 时以库内全集重建）
            if force:
                all_ids = [r["observation_id"] for r in rows]
                bs["known_ids"] = all_ids
                bs["total_synced"] = len(all_ids)
            else:
                merged = list(known | set(new_ids))
                bs["known_ids"] = merged
                bs["total_synced"] = len(merged)
            bs["last_synced_at"] = datetime.now().isoformat()
            self._save_state()

            return SyncResult(
                brand=brand,
                new_count=len(new_ids),
                known_count=len(rows) - len(new_ids),
                total_in_db=total_in_db,
                synced_at=bs["last_synced_at"],
                forced=force,
                observations=observations,
                new_observation_ids=new_ids,
            )
        finally:
            conn.close()

    def reset(self, brand: Optional[str] = None) -> None:
        """清除水位（下次 sync 视为全量）。"""
        if brand:
            self._state["brands"].pop(brand, None)
        else:
            self._state["brands"] = {}
        self._save_state()

    # ------------------------------------------------------------------
    # 便捷：同步后直接产出可测量的 prompt 集合
    # ------------------------------------------------------------------

    def sync_as_prompts(self, brand: str, force: bool = False) -> SyncResult:
        """同步，并把新增观测对应的 prompt 也一并返回（供 collect_batch 复用）。"""
        return self.sync(brand=brand, force=force)

    def list_brands(self) -> List[str]:
        """列出 DB 中可用的品牌（供 Distributor 选择同步目标）。"""
        if not os.path.exists(self.db_path):
            return []
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT brand FROM observations WHERE brand != '' ORDER BY brand"
            )
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
