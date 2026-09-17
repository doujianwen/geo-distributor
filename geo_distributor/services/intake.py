"""Intake Service（Sprint 0）。

职责：验证 Service Request 完整性，决定进入 SCOPING 或 CLARIFICATION_REQUIRED。
"""

from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# 最低必填字段
REQUIRED_FIELDS = [
    "client_id",
    "tenant_id",
    "service",
    "business_context",
]

OPTIONAL_BUT_RECOMMENDED = [
    "requested_engines",
    "business_context.target_market",
    "business_context.target_products",
    "business_context.known_competitors",
]


class IntakeService:
    """Intake 服务 — 判断请求是否足够进入技术 Scope。"""

    async def review(
        self,
        request: "ServiceRequest",  # type: ignore
    ) -> Dict[str, Any]:
        """执行 Intake Review，返回结果。

        返回：
        {
            "status": "COMPLETE" | "INCOMPLETE",
            "missing_fields": [...],
            "clarification_request": {...} | None,
            "recommendation": "SCOPING" | "CLARIFICATION_REQUIRED"
        }
        """
        missing = self._check_required_fields(request)
        recommendations = self._check_recommendations(request)

        if missing:
            logger.info("Intake INCOMPLETE: missing=%s", missing)
            return {
                "status": "INCOMPLETE",
                "missing_fields": missing,
                "clarification_request": {
                    "request_id": request.request_id,
                    "missing_fields": missing,
                    "questions": self._format_questions(missing),
                },
                "recommendation": "CLARIFICATION_REQUIRED",
            }

        if recommendations:
            logger.info("Intake COMPLETE with recommendations: %s", recommendations)
            return {
                "status": "COMPLETE",
                "missing_fields": [],
                "recommendations": recommendations,
                "clarification_request": None,
                "recommendation": "SCOPING",
            }

        logger.info("Intake COMPLETE")
        return {
            "status": "COMPLETE",
            "missing_fields": [],
            "clarification_request": None,
            "recommendation": "SCOPING",
        }

    def _check_required_fields(self, request: "ServiceRequest") -> List[str]:  # type: ignore
        """检查必填字段。"""
        missing = []
        for field in REQUIRED_FIELDS:
            if field == "business_context":
                if not hasattr(request, "business_context") or request.business_context is None:  # type: ignore
                    missing.append(field)
            elif not hasattr(request, field) or getattr(request, field) is None:  # type: ignore
                missing.append(field)
        return missing

    def _check_recommendations(self, request: "ServiceRequest") -> List[str]:  # type: ignore
        """检查推荐但非必填的字段。"""
        recs = []
        for field in OPTIONAL_BUT_RECOMMENDED:
            parts = field.split(".")
            obj = request
            for part in parts:
                if not hasattr(obj, part):
                    recs.append(field)
                    break
                obj = getattr(obj, part)
            if recs and recs[-1] == field:
                continue
            if hasattr(obj, "__len__") and len(obj) == 0:
                recs.append(field)
        return recs

    def _format_questions(self, missing: List[str]) -> List[str]:
        """将缺失字段转化为结构化问题。"""
        question_map = {
            "client_id": "Please provide Client ID or create a new Client.",
            "tenant_id": "Please confirm the Distributor Tenant.",
            "service": "Please specify the service type (visibility_audit, measurement, etc.).",
            "business_context": "Please provide business context (target market, products, etc.).",
            "requested_engines": "Which AI engines should be measured? (ChatGPT, Google, etc.)",
            "business_context.target_market": "Which market(s) should be measured? (e.g., US, EU)",
            "business_context.target_products": "Which products/services should be included?",
            "business_context.known_competitors": "Who are the known competitors?",
        }
        return [question_map.get(f, f"Please provide: {f}") for f in missing]
