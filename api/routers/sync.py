"""同步路由 — geo-collector 增量同步（P0-4 增强）。

端点：
    GET  /sync/status          — 查看同步水位（全部品牌或指定品牌）
    GET  /sync/brands          — 列出 DB 中可同步的品牌
    POST /sync                 — 触发一次增量同步
    POST /sync/reset           — 清除水位（下次同步视为全量）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import state

router = APIRouter(prefix="/sync", tags=["sync"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class SyncRequest(BaseModel):
    brand: str = Field(..., description="目标品牌名（与 observations.brand 匹配）")
    force: bool = Field(False, description="忽略水位，全量重同步")
    include_observations: bool = Field(
        False, description="响应中是否包含完整观测体（大，默认关闭）"
    )


class SyncResponse(BaseModel):
    brand: str
    new_count: int
    known_count: int
    total_in_db: int
    synced_at: str
    forced: bool
    new_observation_ids: list[str] = Field(default_factory=list)


class ResetRequest(BaseModel):
    brand: Optional[str] = Field(None, description="不传则清空全部品牌水位")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_sync_service():
    """懒构造 SyncService（首次调用时初始化）。"""
    from .. import state as _state
    if getattr(_state, "sync_service", None) is None:
        from geo_distributor.services.sync_service import SyncService
        try:
            _state.sync_service = SyncService()
        except Exception as e:  # pragma: no cover - 环境相关
            raise HTTPException(
                status_code=503,
                detail=f"SyncService unavailable: {e}",
            )
    return _state.sync_service


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/status")
async def sync_status(brand: Optional[str] = None):
    """查看同步水位。不带 brand 则返回全局概览。"""
    svc = _get_sync_service()
    return svc.get_status(brand)


@router.get("/brands")
async def list_brands():
    """列出 geo-collector DB 中可同步的品牌。"""
    svc = _get_sync_service()
    brands = svc.list_brands()
    return {
        "brands": [
            {
                "brand": b,
                **{k: v for k, v in svc.get_status(b).items() if k != "brand"},
            }
            for b in brands
        ],
        "count": len(brands),
    }


@router.post("", response_model=SyncResponse)
async def run_sync(body: SyncRequest):
    """触发一次增量同步。

    以 observation_id 集合差分判定新增，水位持久化到 exports/sync_state.json。
    """
    svc = _get_sync_service()
    if not body.brand.strip():
        raise HTTPException(status_code=400, detail="brand is required")
    try:
        result = svc.sync(brand=body.brand.strip(), force=body.force)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Sync failed: {e}")

    return SyncResponse(
        brand=result.brand,
        new_count=result.new_count,
        known_count=result.known_count,
        total_in_db=result.total_in_db,
        synced_at=result.synced_at,
        forced=result.forced,
        new_observation_ids=result.new_observation_ids,
    )


@router.post("/reset")
async def reset_sync(body: ResetRequest):
    """清除同步水位（下次同步视为全量）。"""
    svc = _get_sync_service()
    svc.reset(body.brand)
    return {
        "reset": True,
        "brand": body.brand or "*",
        "message": "下次 sync 将执行全量同步",
    }
