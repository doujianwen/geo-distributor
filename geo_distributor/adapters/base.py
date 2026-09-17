"""适配器基类。

V0.2 关键变化：
- BaseAdapter.collect_prompt() 统一返回 PlatformObservation（不再返回 Run）
- Run 是高层编排结果，不属于 Adapter 契约
- 未来 ElmoAdapter 与 GeoCollectorAdapter 输出相同格式，可互换
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import logging

from ..compatibility.base import PlatformObservation
from ..models import Prompt

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    """所有 Adapter 的契约：输入 Prompt，输出 PlatformObservation。"""

    @abstractmethod
    async def health_check(self) -> bool:
        """检查适配器及下游系统是否可用。"""
        ...

    @abstractmethod
    async def collect_prompt(self, prompt: Prompt) -> PlatformObservation:
        """采集单个 prompt，返回统一格式的 PlatformObservation。

        无论数据来源是 geo-collector 还是 Elmo，
        返回值始终是 PlatformObservation，上层代码无需感知具体来源。
        """
        ...

    @abstractmethod
    async def collect_batch(
        self,
        prompts: List[Prompt],
        progress_callback=None,
    ) -> List[PlatformObservation]:
        """批量采集，可选 progress_callback(current, total) 用于进度汇报。"""
        ...


class ElmoAdapter(BaseAdapter):
    """Elmo 适配器 — REST API 通信，禁止直接访问 PostgreSQL。

    实现状态：V0.4 MVP（A1.7）
    - health_check: 调用 /api/v1/me
    - collect_prompt: 获取 prompt → run → brand → 映射到 PlatformObservation
    - collect_batch: 逐个采集，单个失败不影响整体
    """

    def __init__(
        self,
        elmo_url: str = "",
        api_key: str = "",
        version: str = "v0.3.0",
        timeout_seconds: int = 30,
        max_retries: int = 2,
    ):
        self.elmo_url = elmo_url
        self.api_key = api_key
        self.version = version
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def health_check(self) -> bool:
        if not self.elmo_url or not self.api_key:
            return False
        try:
            from .elmo_client import ElmoClient
            client = ElmoClient(
                base_url=self.elmo_url,
                api_key=self.api_key,
                version=self.version,
                timeout_seconds=self.timeout_seconds,
                max_retries=self.max_retries,
            )
            return await client.health_check()
        except Exception:
            return False

    async def collect_prompt(self, prompt: Prompt) -> PlatformObservation:
        """采集单个 Elmo prompt，返回 PlatformObservation。

        流程：
        1. 获取 prompt 详情（验证 prompt 存在）
        2. 获取最新 run
        3. 获取 brand 信息（名称 + 域名）
        4. 映射到 PlatformObservation
        """
        from .elmo_client import ElmoClient
        from ..compatibility.elmo import map_elmo_to_platform
        from ..compatibility.base import PlatformObservation

        if not self.elmo_url or not self.api_key:
            # 配置缺失时返回 error 观察，与 GeoCollectorAdapter 保持一致
            return PlatformObservation(
                observation_id=f"err_elmo_{prompt.prompt_id}",
                prompt_id=int(prompt.prompt_id) if prompt.prompt_id else 0,
                engine="elmo",
                timestamp="",
                prompt_text=getattr(prompt, 'text', ''),
                answer_raw="",
                answer_clean="",
                answer_char_count=0,
                extraction_method="elmo_api",
                validation_status="FAIL",
                brand="",
                brand_mentioned=False,
                brand_status="UNKNOWN",
                first_mention_position=None,
                recommendation_level=-1,
                recommendation_rank=None,
                recommendation_evidence="",
                competitors=[],
                citations=[],
                citations_status="unavailable",
                status="failed",
                raw_metadata={"error": "Elmo adapter not configured (missing url or api_key)"},
            )

        client = ElmoClient(
            base_url=self.elmo_url,
            api_key=self.api_key,
            version=self.version,
            timeout_seconds=self.timeout_seconds,
            max_retries=self.max_retries,
        )

        try:
            # 1. 获取 prompt 详情
            prompt_data = await client.get_prompt(str(prompt.prompt_id))
            prompt_uuid = prompt_data.get("id", str(prompt.prompt_id))

            # 2. 获取最新 run
            runs = await client.list_runs(str(prompt.prompt_id), limit=1)
            if not runs:
                return PlatformObservation(
                    observation_id=f"err_elmo_no_run_{prompt.prompt_id}",
                    prompt_id=_prompt_id_to_int(prompt.prompt_id),
                    engine="elmo",
                    timestamp="",
                    prompt_text=getattr(prompt, 'text', ''),
                    answer_raw="",
                    answer_clean="",
                    answer_char_count=0,
                    extraction_method="elmo_api",
                    validation_status="FAIL",
                    brand="",
                    brand_mentioned=False,
                    brand_status="UNKNOWN",
                    first_mention_position=None,
                    recommendation_level=-1,
                    recommendation_rank=None,
                    recommendation_evidence="",
                    competitors=[],
                    citations=[],
                    citations_status="unavailable",
                    status="failed",
                    raw_metadata={"error": "No runs found for prompt", "prompt_id": str(prompt.prompt_id)},
                )

            run = runs[0]
            run_id = run.get("id", "")

            # 3. 获取 brand 信息
            brand_data = await client.get_brand(run.get("brandId", ""))
            brand_name = brand_data.get("name", "")
            brand_domains = brand_data.get("domains", [])

            # 4. 获取 citations
            citations = run.get("citations", [])

            # 5. 模型名
            model_name = run.get("model", prompt_data.get("model", "unknown"))

            # 6. 映射到 PlatformObservation
            mapped = map_elmo_to_platform(
                elmo_run=run,
                elmo_citations=citations,
                brand_name=brand_name,
                brand_domains=brand_domains,
                prompt_id_uuid=prompt_uuid,
                model_name=model_name,
                elmo_version=self.version,
            )

            return PlatformObservation(**mapped)

        except Exception as e:
            logger.error("ElmoAdapter.collect_prompt failed for prompt %s: %s", prompt.prompt_id, e)
            return PlatformObservation(
                observation_id=f"err_elmo_{prompt.prompt_id}",
                prompt_id=_prompt_id_to_int(prompt.prompt_id),
                engine="elmo",
                timestamp="",
                prompt_text=getattr(prompt, 'text', ''),
                answer_raw="",
                answer_clean="",
                answer_char_count=0,
                extraction_method="elmo_api",
                validation_status="FAIL",
                brand="",
                brand_mentioned=False,
                brand_status="UNKNOWN",
                first_mention_position=None,
                recommendation_level=-1,
                recommendation_rank=None,
                recommendation_evidence="",
                competitors=[],
                citations=[],
                citations_status="unavailable",
                status="failed",
                raw_metadata={"error": str(e), "prompt_id": str(prompt.prompt_id)},
            )

    async def collect_batch(
        self,
        prompts: List[Prompt],
        progress_callback=None,
    ) -> List[PlatformObservation]:
        """批量采集，单个失败不影响整体。"""
        results = []
        for i, prompt in enumerate(prompts):
            try:
                obs = await self.collect_prompt(prompt)
                results.append(obs)
            except Exception as e:
                from ..compatibility.base import PlatformObservation
                results.append(PlatformObservation(
                    observation_id=f"err_elmo_batch_{prompt.prompt_id}",
                    prompt_id=_prompt_id_to_int(prompt.prompt_id),
                    engine="elmo",
                    timestamp="",
                    prompt_text=getattr(prompt, 'text', ''),
                    answer_raw="",
                    answer_clean="",
                    answer_char_count=0,
                    extraction_method="elmo_api",
                    validation_status="FAIL",
                    brand="",
                    brand_mentioned=False,
                    brand_status="UNKNOWN",
                    first_mention_position=None,
                    recommendation_level=-1,
                    recommendation_rank=None,
                    recommendation_evidence="",
                    competitors=[],
                    citations=[],
                    citations_status="unavailable",
                    status="failed",
                    raw_metadata={"error": str(e)},
                ))
            if progress_callback:
                progress_callback(i + 1, len(prompts))
        return results


def _prompt_id_to_int(prompt_id) -> int:
    """将 prompt_id 安全转为 int。"""
    try:
        return int(prompt_id)
    except (TypeError, ValueError):
        return 0


class GeoCollectorAdapter(BaseAdapter):
    """直接调用 geo-collector 的适配器（fallback，不依赖 Elmo）。

    通过 sys.path 注入 geo-collector 路径，复用其 storage/parser/collectors。
    当 Elmo 验证失败或 PARTIAL PASS 时，此为唯一数据源。
    """

    def __init__(self, collector_root: Optional[str] = None):
        from ..config import get_geo_collector_root, ensure_sys_path
        ensure_sys_path()
        self._collector_root = collector_root or get_geo_collector_root()

    async def health_check(self) -> bool:
        try:
            from storage.database import Database
            from storage.models import load_prompts
            return True
        except ImportError:
            return False

    async def collect_prompt(self, prompt: Prompt) -> PlatformObservation:
        """采集单个 prompt，经 compatibility 层映射后返回 PlatformObservation。"""
        import asyncio
        from storage.models import gen_observation_id, today_str
        from storage.database import Database
        from collectors.chatgpt import ChatGPTCollector
        from collectors.perplexity import PerplexityCollector
        from collectors.gemini import GeminiCollector
        from collectors.google_ai import GoogleAICollector

        COLLECTORS = {
            "chatgpt": ChatGPTCollector,
            "perplexity": PerplexityCollector,
            "gemini": GeminiCollector,
            "google_ai": GoogleAICollector,
        }

        # 使用 prompt.engine 决定采集引擎，默认 chatgpt
        engine_key = getattr(prompt, 'engine', None) or "chatgpt"
        collector_cls = COLLECTORS.get(engine_key, ChatGPTCollector)

        db = Database(f"{self._collector_root}/geo_distributor.db")

        # 复用 geo-collector 的采集逻辑
        collector = collector_cls()
        try:
            await collector.start()
            obs = await collector.collect_prompt(prompt.prompt_id, prompt.text)
            db.upsert_observation(obs)
        finally:
            await collector.close()

        # 通过 compatibility 层映射到 PlatformObservation
        from ..compatibility.base import map_geo_collector_observation
        return map_geo_collector_observation(obs)

    async def collect_batch(
        self,
        prompts: List[Prompt],
        progress_callback=None,
    ) -> List[PlatformObservation]:
        results = []
        for i, prompt in enumerate(prompts):
            try:
                obs = await self.collect_prompt(prompt)
                results.append(obs)
            except Exception as e:
                # 单个失败不影响整体，记录错误后继续
                from ..compatibility.base import PlatformObservation
                results.append(PlatformObservation(
                    observation_id=f"err_{prompt.prompt_id}",
                    prompt_id=prompt.prompt_id,
                    engine=getattr(prompt, 'engine', 'unknown'),
                    timestamp="",
                    prompt_text=prompt.text,
                    answer_raw="",
                    answer_clean="",
                    answer_char_count=0,
                    extraction_method="error",
                    validation_status="FAIL",
                    brand="",
                    brand_mentioned=False,
                    brand_status="UNKNOWN",
                    first_mention_position=None,
                    recommendation_level=-1,
                    recommendation_rank=None,
                    recommendation_evidence="",
                    competitors=[],
                    citations=[],
                    citations_status="unavailable",
                    status="failed",
                    raw_metadata={"error": str(e)},
                ))
            if progress_callback:
                progress_callback(i + 1, len(prompts))
        return results
