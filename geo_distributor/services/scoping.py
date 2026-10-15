"""Scoping Service（Sprint 0）。

职责：将业务请求转换为 Technical Scope，生成 Scope 对象。
"""

from typing import Optional, Dict, Any
import logging
import uuid

logger = logging.getLogger(__name__)


class ScopingService:
    """Scoping 服务 — 商业需求 → Technical Scope。"""

    async def create_scope(
        self,
        request_id: str,
        tenant_id: str,
        business_context: Dict[str, Any],
        service: str,
        requested_engines: Optional[list] = None,
    ) -> Dict[str, Any]:
        """生成 Technical Scope。

        Scope 策略：
        - query_policy 默认为 HQ_DEFINED
        - measurement_rounds 默认为 1
        - 根据 service 类型决定包含哪些阶段
        """
        scope_id = f"SCOPE-{uuid.uuid4().hex[:8].upper()}"

        # 默认引擎
        engines = requested_engines or ["ChatGPT"]

        # 根据服务类型设置阶段
        stages = self._determine_stages(service)

        scope = {
            "scope_id": scope_id,
            "request_id": request_id,
            "tenant_id": tenant_id,
            "markets": business_context.get("target_market", []),
            "engines": engines,
            "query_policy": "HQ_DEFINED",
            "query_set_id": None,
            "measurement_rounds": 1,
            "sampling_protocol": "HQ-GEO-SP-001",
            "measurement": stages["measurement"],
            "diagnosis": stages["diagnosis"],
            "intervention": stages["intervention"],
            "remeasurement": stages["remeasurement"],
            "deliverables": ["client_report"],
            "assumptions": [],
            "exclusions": [],
            "approved_by": None,
            "approved_at": None,
            "version": 1,
        }

        logger.info("Scope created: %s for request %s", scope_id, request_id)
        return scope

    def _determine_stages(self, service: str) -> Dict[str, bool]:
        """根据服务类型确定包含的阶段。"""
        stage_map = {
            "visibility_audit": {"measurement": True, "diagnosis": False, "intervention": False, "remeasurement": False},
            "measurement": {"measurement": True, "diagnosis": False, "intervention": False, "remeasurement": False},
            "diagnosis": {"measurement": True, "diagnosis": True, "intervention": False, "remeasurement": False},
            "competitor_analysis": {"measurement": True, "diagnosis": True, "intervention": False, "remeasurement": False},
            "intervention": {"measurement": True, "diagnosis": True, "intervention": True, "remeasurement": False},
            "remeasurement": {"measurement": True, "diagnosis": False, "intervention": False, "remeasurement": True},
            "full_geo_project": {"measurement": True, "diagnosis": True, "intervention": True, "remeasurement": True},
        }
        return stage_map.get(service, stage_map["visibility_audit"])
