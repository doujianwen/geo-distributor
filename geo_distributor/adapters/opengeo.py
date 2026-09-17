"""OpenGeoAdapter — Sprint 4 真实测量适配器（规格 §11）。

职责：
- 实现 BaseAdapter（= 规格中的 MeasurementAdapter），输出统一的 PlatformObservation
- 不污染 Canonical Core：只消费 PlatformObservation，不引入 OpenGeo/Bing/GSC 私有字段
- 支持两种数据来源：
    1. collected store：已采集的 PlatformObservation 记录（来自真实导出，经 compatibility 层映射）
    2. live（预留）：配置真实采集 API 后直连；当前环境凭据受限，保留接口但默认走 collected store

禁止：
- 在 Core 模型中添加 provider-specific 字段
- 把 OpenGeo/Bing/GSC 的私有 schema 泄漏到上层业务
"""

from typing import List, Optional

from ..compatibility.base import PlatformObservation
from ..models import Prompt
from .base import BaseAdapter


class OpenGeoAdapter(BaseAdapter):
    """Sprint 4 真实测量适配器。

    典型用法（Sprint 4 Lab）：
        observations = map_bing_ai_performance(export)  # compatibility 层
        adapter = OpenGeoAdapter.from_observations(observations)
        results = await adapter.collect_batch(prompts)

    也可从已落盘的 observations JSON 加载：
        adapter = OpenGeoAdapter.from_json_file("cases/bookconv/baseline/observations.json")
    """

    def __init__(self, observations: Optional[List[PlatformObservation]] = None):
        self._observations: List[PlatformObservation] = list(observations or [])
        # 建立 prompt_text -> observation 索引，便于按 query 精确返回
        self._by_prompt = {o.prompt_text: o for o in self._observations}

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_observations(cls, observations: List[PlatformObservation]) -> "OpenGeoAdapter":
        return cls(observations=observations)

    @classmethod
    def from_dicts(cls, observations: List[dict]) -> "OpenGeoAdapter":
        return cls(observations=[PlatformObservation(**o) for o in observations])

    @classmethod
    def from_json_file(cls, path: str) -> "OpenGeoAdapter":
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        obs_list = data if isinstance(data, list) else data.get("observations", [])
        return cls.from_dicts(obs_list)

    # ------------------------------------------------------------------
    # BaseAdapter 契约
    # ------------------------------------------------------------------

    async def health_check(self) -> bool:
        """有已加载观测即视为健康。"""
        return len(self._observations) > 0

    async def collect_prompt(self, prompt: Prompt) -> PlatformObservation:
        """按 prompt 返回对应观测；无匹配则返回未命中观测（透明、不伪造）。"""
        if isinstance(prompt, str):
            query = prompt
        elif isinstance(prompt, dict):
            query = prompt.get("query", prompt.get("text", ""))
        else:
            query = getattr(prompt, "text", getattr(prompt, "query", ""))

        obs = self._by_prompt.get(query)
        if obs is not None:
            return obs

        # 透明返回「未采集」观测，禁止编造
        return PlatformObservation(
            observation_id=f"obs_missing_{abs(hash(query)) % 10**8:08d}",
            prompt_id=abs(hash(query)) % 10**8,
            engine="opengeo",
            timestamp="",
            prompt_text=query,
            answer_raw="",
            answer_clean="",
            answer_char_count=0,
            extraction_method="opengeo_store",
            validation_status="PASS",
            brand="",
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
            raw_metadata={"note": "query not present in collected store; no fabrication"},
        )

    async def collect_batch(
        self,
        prompts: List[Prompt],
        progress_callback=None,
    ) -> List[PlatformObservation]:
        results: List[PlatformObservation] = []
        for i, prompt in enumerate(prompts):
            results.append(await self.collect_prompt(prompt))
            if progress_callback:
                progress_callback(i + 1, len(prompts))
        return results
