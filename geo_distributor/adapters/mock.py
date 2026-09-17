"""Mock Measurement Adapter（Sprint 2 — P0 必须）。

返回真实结构的 Mock 数据，用于验证 GEO Core 链路。
不依赖 open-geo，证明 Canonical Core 独立运行。
"""

from typing import List, Optional, Dict, Any
import asyncio
import uuid
import random
from dataclasses import dataclass, field
from datetime import datetime

from .base import BaseAdapter
from ..compatibility.base import PlatformObservation


@dataclass
class MockQuerySet:
    """模拟 Query Set。"""
    queries: List[str] = field(default_factory=list)
    market: str = "US"
    engine: str = "mock"


@dataclass
class MockRawResponse:
    """模拟原始响应。"""
    query: str
    answer_text: str
    sources: List[str] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    brand_in_answer: bool = False
    target_source_rank: Optional[int] = None
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())


class MockMeasurementAdapter(BaseAdapter):
    """Mock Measurement Adapter — 返回真实结构。

    用于：
    1. 验证 Canonical Core 链路
    2. 开发阶段替代 open-geo
    3. E2E 测试
    """

    # 预定义的 mock 响应模板
    MOCK_RESPONSES = [
        MockRawResponse(
            query="best industrial sensors manufacturer",
            answer_text="Top manufacturers include Acme Corp, which offers a comprehensive line of precision industrial sensors with industry-leading reliability and support.",
            sources=["https://example.com/sensors-guide"],
            citations=[{"text": "Acme Corp leads the market", "url": "https://example.com/sensors-guide", "type": "authority"}],
            brand_in_answer=True,
            target_source_rank=1,
        ),
        MockRawResponse(
            query="industrial sensor solutions provider",
            answer_text="For industrial automation needs, consider companies like Acme Corp that specialize in sensor technology and system integration.",
            sources=["https://techreview.com/industrial"],
            citations=[{"text": "Acme Corp recommended for industrial", "url": "https://techreview.com/industrial", "type": "recommendation"}],
            brand_in_answer=True,
            target_source_rank=2,
        ),
        MockRawResponse(
            query="AI visibility audit example",
            answer_text="When evaluating AI visibility, brands should check their presence across ChatGPT, Google AI, and Perplexity platforms.",
            sources=["https://ai-visibility.example.com"],
            citations=[],
            brand_in_answer=False,
            target_source_rank=None,
        ),
    ]

    async def health_check(self) -> bool:
        """Mock 适配器始终健康。"""
        return True

    async def collect_prompt(self, prompt) -> PlatformObservation:
        """采集单个 prompt，返回标准 PlatformObservation。

        prompt 可以是：
        - 字符串（query）
        - 字典（含 query/engine 字段）
        - 对象（含 text/prompt_id 属性）
        """
        # 提取 query
        if isinstance(prompt, str):
            query = prompt
        elif isinstance(prompt, dict):
            query = prompt.get("query", prompt.get("text", "unknown"))
        else:
            query = getattr(prompt, 'text', getattr(prompt, 'query', 'unknown'))

        # 选择 mock 响应
        response = self._select_response(query)

        # 构建 PlatformObservation
        return PlatformObservation(
            observation_id=f"OBS-{uuid.uuid4().hex[:8].upper()}",
            prompt_id=0,
            engine="mock",
            timestamp=datetime.now().isoformat(),
            prompt_text=query,
            answer_raw=response.answer_text,
            answer_clean=response.answer_text.strip(),
            answer_char_count=len(response.answer_text),
            extraction_method="mock_adapter",
            validation_status="PASS",
            brand="",  # 由上层填充
            brand_mentioned=response.brand_in_answer,
            brand_status="MENTIONED" if response.brand_in_answer else "NOT_FOUND",
            first_mention_position=response.target_source_rank,
            recommendation_level=3 if response.target_source_rank and response.target_source_rank <= 2 else 0,
            recommendation_rank=response.target_source_rank,
            recommendation_evidence=self._format_evidence(response),
            competitors=[c.get("competitor", "Unknown") for c in response.citations if c.get("competitor")],
            citations=[{
                "text": c.get("text", ""),
                "url": c.get("url", ""),
                "type": c.get("type", "other"),
            } for c in response.citations],
            citations_status="found" if response.citations else "none",
            status="success",
            raw_metadata={
                "query": query,
                "response_type": "mock",
                "brand_in_answer": response.brand_in_answer,
                "target_rank": response.target_source_rank,
            },
        )

    async def collect_batch(
        self,
        prompts: List[Any],
        progress_callback=None,
    ) -> List[PlatformObservation]:
        """批量采集，单个失败不影响整体。"""
        results = []
        for i, prompt in enumerate(prompts):
            try:
                obs = await self.collect_prompt(prompt)
                results.append(obs)
            except Exception as e:
                results.append(self._create_error_observation(prompt, e))
            if progress_callback:
                progress_callback(i + 1, len(prompts))
        return results

    def _select_response(self, query: str) -> MockRawResponse:
        """根据 query 选择最匹配的 mock 响应。"""
        # 简单规则：按 query 长度取模选择
        idx = abs(hash(query)) % len(self.MOCK_RESPONSES)
        return self.MOCK_RESPONSES[idx]

    def _format_evidence(self, response: MockRawResponse) -> str:
        """格式化证据文本。"""
        if response.citations:
            return f"Found {len(response.citations)} citations"
        return "No citations found"

    def _create_error_observation(self, prompt, error: Exception) -> PlatformObservation:
        """创建错误观察。"""
        from ..compatibility.base import PlatformObservation
        query = getattr(prompt, 'text', str(prompt)) if hasattr(prompt, 'text') else str(prompt)
        return PlatformObservation(
            observation_id=f"err_mock_{uuid.uuid4().hex[:8].upper()}",
            prompt_id=0,
            engine="mock",
            timestamp=datetime.now().isoformat(),
            prompt_text=query,
            answer_raw="",
            answer_clean="",
            answer_char_count=0,
            extraction_method="error",
            validation_status="FAIL",
            brand="",
            brand_mentioned=False,
            brand_status="ERROR",
            first_mention_position=None,
            recommendation_level=-1,
            recommendation_rank=None,
            recommendation_evidence=str(error),
            competitors=[],
            citations=[],
            citations_status="error",
            status="failed",
            raw_metadata={"error": str(error)},
        )


class MockMeasurementService:
    """Mock 测量服务 — 执行完整 Measurement → Evidence → Finding 链路。"""

    def __init__(self, adapter: Optional[MockMeasurementAdapter] = None):
        self.adapter = adapter or MockMeasurementAdapter()
        self.observations: List[Dict[str, Any]] = []
        self.evidences: List[Dict[str, Any]] = []
        self.findings: List[Dict[str, Any]] = []

    async def execute_measurement(
        self,
        project_id: str,
        queries: List[str],
        scope: Dict[str, Any],
    ) -> Dict[str, Any]:
        """执行 Mock Measurement，返回标准化结果。"""
        # 构建 prompts
        prompts = [{"query": q, "engine": "mock"} for q in queries]

        # 执行采集
        observations = await self.adapter.collect_batch(prompts)

        # 转换为内部表示
        results = {
            "project_id": project_id,
            "observation_count": len(observations),
            "observations": [],
            "evidences": [],
            "findings": [],
        }

        for obs in observations:
            obs_dict = obs.to_dict() if hasattr(obs, 'to_dict') else dict(obs)
            results["observations"].append(obs_dict)

            # 创建 Evidence（如果 observation 有效）
            if obs_dict.get("status") == "success":
                evidence = self._create_evidence(project_id, obs_dict)
                results["evidences"].append(evidence)

            # 创建 Finding（如果有品牌提及）
            if obs_dict.get("brand_mentioned"):
                finding = self._create_finding(project_id, obs_dict)
                results["findings"].append(finding)

        # 保存
        self.observations.extend(results["observations"])
        self.evidences.extend(results["evidences"])
        self.findings.extend(results["findings"])

        return results

    def _create_evidence(self, project_id: str, observation: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Evidence 记录。"""
        evidence_id = f"EVD-{uuid.uuid4().hex[:8].upper()}"
        return {
            "evidence_id": evidence_id,
            "project_id": project_id,
            "observation_id": observation.get("observation_id"),
            "source_type": "citation",
            "content": observation.get("answer_clean", ""),
            "url": observation.get("citations", [{}])[0].get("url", "") if observation.get("citations") else "",
            "credibility_score": 0.85,
            "level": "E2",  # repeated observation
            "verified_at": datetime.now().isoformat(),
        }

    def _create_finding(self, project_id: str, observation: Dict[str, Any]) -> Dict[str, Any]:
        """创建 Finding 记录。"""
        finding_id = f"FND-{uuid.uuid4().hex[:8].upper()}"
        return {
            "finding_id": finding_id,
            "project_id": project_id,
            "category": "visibility_gap",
            "severity": "HIGH" if observation.get("recommendation_level", 0) < 2 else "MEDIUM",
            "statement": f"Brand mentioned at rank {observation.get('recommendation_rank', 'N/A')}",
            "evidence_refs": [f"EVD-{uuid.uuid4().hex[:8].upper()}"],
            "recommendation": "Improve AI visibility through content optimization",
            "confidence": 0.75,
            "created_by": "MOCK_SYSTEM",
        }


# 导出
__all__ = ["MockMeasurementAdapter", "MockMeasurementService", "MockQuerySet", "MockRawResponse"]
