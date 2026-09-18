"""商业产品层 + GEO Intelligence 层统一数据模型。

核心链路（从 geo-collector 继承语义，在本层定义契约）：
    Prompt → Observation → Citation → Measurement → Diagnosis

平台模型（Organization / Project / Brand 等）与链路模型共存于此文件，
通过文档注释区分层级归属。

Sprint 0 新增（2026-09-13）：
    - tenant.py: Tenant/User/AuditEntry（P0 身份与隔离）
    - request.py: ServiceRequest/RequestStatus（P0 统一状态机）
    - scope.py: TechnicalScope（P0 商业→技术转换层）
    - project.py: Project/ProjectStatus（P0 统一状态机）
    - work_item.py: WorkItem（P0 最小技术执行单位）
    - geo_core.py: Evidence/Report/ReportVersion（P0 证据链与报告版本）
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum, auto


# ====================================================================
# 平台层模型（Commercial Product）
# ====================================================================

class OrganizationStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TRIAL = "trial"


class CollectionProjectStatus(Enum):
    """采集项目状态（平台层，调度用）。

    ⚠️ 命名说明：原名 `ProjectStatus`，与 models/project.py 中商业交付项目的
    `ProjectStatus`（approved / in_execution / delivered ...）**同名不同义**。
    为消除歧义，平台层采集侧统一加 `Collection` 前缀。
    """
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class BrandTarget(Enum):
    PRIMARY = "primary"
    COMPETITOR = "competitor"


@dataclass
class Organization:
    org_id: str
    name: str
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    contact_email: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict = field(default_factory=dict)


@dataclass
class Account:
    account_id: str
    org_id: str
    email: str
    role: str = "viewer"
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Brand:
    brand_id: str
    org_id: str
    name: str
    target: BrandTarget = BrandTarget.PRIMARY
    aliases: List[str] = field(default_factory=list)
    competitors: List[str] = field(default_factory=list)
    is_active: bool = True


@dataclass
class CollectionProject:
    """采集项目（平台层，调度用）。

    ⚠️ 命名说明：原名 `Project`。它描述的是"一次采集任务的配置"
    （org + brand + prompts + 引擎 + cron），与 models/project.py 中
    "商业交付容器"的 `Project` 完全不是一回事。

    `geo_distributor.models.Project` 现指向商业交付容器——如需本类，
    请显式使用 `CollectionProject`。
    """
    project_id: str
    org_id: str
    brand_id: str
    name: str
    status: CollectionProjectStatus = CollectionProjectStatus.DRAFT
    prompts_file: str = ""
    engines: List[str] = field(default_factory=list)
    schedule_cron: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Run:
    run_id: str
    project_id: str
    started_at: str
    ended_at: Optional[str] = None
    status: str = "running"
    total_prompts: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    error_summary: str = ""
    # prompt_id 命中但 prompt_text 不一致的条数（错配，已从指标中剔除）
    prompt_mismatch: int = 0


@dataclass
class CollectionReport:
    """采集报告（平台层，一次 Run 的结果汇总）。

    ⚠️ 命名说明：原名 `Report`。与 models/geo_core.py 中"双报告模型"
    （Technical / Client + 版本链）**同名不同义**。

    `geo_distributor.models.Report` 现指向 geo_core 的双报告模型——
    如需本类，请显式使用 `CollectionReport`。
    """
    report_id: str
    project_id: str
    run_ids: List[str] = field(default_factory=list)
    title: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    summary: dict = field(default_factory=dict)
    total_observations: int = 0
    brand_mentioned_count: int = 0
    brand_recommended_count: int = 0


# ====================================================================
# GEO 智能链路模型（与 geo-collector 同构，Platform 层消费）
# ====================================================================

@dataclass
class Prompt:
    """采集用的 prompt 定义，与 geo-collector storage.models.Prompt 对齐。"""
    prompt_id: int
    category: str
    intent: str
    location: str
    text: str
    source: str = ""
    family_id: str = ""
    variant: str = "original"
    tier: str = ""


@dataclass
class Observation:
    """单次采集结果，PlatformObservation 的底层存储格式。

    注意：上层业务应使用 compatibility.PlatformObservation。
    此模型仅在 Adapter → Compatibility 映射内部使用。
    """
    observation_id: str
    prompt_id: int
    engine: str
    timestamp: str
    prompt_text: str
    answer_raw: str
    answer_clean: str
    answer_char_count: int
    extraction_method: str
    validation_status: str
    brand: str
    brand_mentioned: bool
    brand_status: str
    first_mention_position: Optional[int]
    recommendation_level: int
    recommendation_rank: Optional[int]
    recommendation_evidence: str
    competitors: List[dict] = field(default_factory=list)
    citations: List[dict] = field(default_factory=list)
    citations_status: str = "unavailable"
    status: str = "success"
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class Citation:
    """引用来源，与 geo-collector citation_parser 输出对齐。"""
    observation_id: str
    url: str
    domain: str
    title: str
    citation_index: int
    citation_type: str    # A/B/C/D/E 分类
    anchor_text: str = ""
    context: str = ""


# ====================================================================
# GEO 智能链路模型 — Provider / Measurement / Diagnosis（V0.3 新增）
# ====================================================================

class ProviderType(Enum):
    """AI 搜索引擎/生成式引擎类型。"""
    CHATGPT = "chatgpt"
    PERPLEXITY = "perplexity"
    GEMINI = "gemini"
    GOOGLE_AI = "google_ai"
    ELMO = "elmo"
    UNKNOWN = "unknown"


@dataclass
class Provider:
    """AI 搜索引擎/平台的元数据。

    同一个 Prompt 在不同 Provider 下结果不同，
    因此 Provider 是 Observation 的维度之一，而不是只靠 engine 字符串。
    """
    provider_id: str          # 如 "chatgpt", "perplexity", "elmo"
    name: str                 # 显示名，如 "ChatGPT", "Perplexity"
    provider_type: ProviderType
    version: str = ""         # 如 "gpt-4o", "perplexity-online", "gemini-2.0"
    is_active: bool = True
    metadata: dict = field(default_factory=dict)


@dataclass
class Measurement:
    """GEO 指标测量结果。

    商业价值核心：对 Observation 的量化评分，
    而非原始回答本身。
    """
    measurement_id: str
    observation_id: str
    # --- 品牌位置指标 ---
    brand_position: Optional[int] = None       # 首次提及位置（段落级）
    brand_recommendation_level: int = -1       # 0-4，与 Observation.recommendation_level 对齐
    brand_recommendation_rank: Optional[int] = None
    # --- 引用质量指标 ---
    citation_count: int = 0
    authority_citation_count: int = 0          # B类（.gov/.edu）
    brand_owned_citation_count: int = 0        # A类
    # --- 综合分数 ---
    geo_score: Optional[float] = None          # 综合 GEO 得分（0-100）
    measured_at: str = field(default_factory=lambda: datetime.now().isoformat())
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class Diagnosis:
    """GEO 诊断结论。

    对 Measurement 的解释，回答"为什么是这个分数"。
    """
    diagnosis_id: str
    observation_id: str
    measurement_id: str
    # --- 诊断结论 ---
    verdict: str = ""                # PASS / WARN / FAIL
    summary: str = ""                # 人类可读结论
    findings: List[dict] = field(default_factory=list)   # 结构化发现列表
    recommendations: List[str] = field(default_factory=list)  # 改进建议
    diagnosed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    raw_metadata: dict = field(default_factory=dict)


# ====================================================================
# 子模块 re-export（P1 统一导入面）
#
# 背景：本文件是"平台层 + 链路层"的混合定义文件，子模块（client.py /
# service_stage.py / geo_core.py / finding.py）另有一批模型。此前调用方
# 必须按文件路径二选一，容易导入到错误的同名类。
#
# 规则：本文件只保留"平台层（采集侧）"模型，且一律带 Collection 前缀；
# 商业交付侧模型从子模块 re-export，构成单一导入面。
#
# 2026-09-18 已消除的同名割裂（原平台层类已重命名）：
#   - Project       → CollectionProject（采集任务配置）
#   - Report        → CollectionReport（单次 Run 结果汇总）
#   - ProjectStatus → CollectionProjectStatus（采集状态）
#   现在 `models.Project` / `models.Report` / `models.ProjectStatus`
#   唯一指向商业交付侧定义，与 `from geo_distributor.models.project import ...`
#   完全一致，不会再出现"导入到错误同名类"的问题。
# ====================================================================

from .project import Project, ProjectStatus, PROJECT_TRANSITIONS  # 商业交付容器
from .geo_core import Report, ReportType, ReportVersion            # 双报告模型
from .client import Client
from .service_stage import (
    ServiceStage,
    StageStatus,
    StageRecord,
    DEFAULT_STAGE_SEQUENCE,
    STAGE_TRANSITIONS,
    init_stage_records,
    can_transition_stage,
    next_stage,
)
from .geo_core import Evidence, EvidenceLevel
from .finding import Finding, FindingSeverity, FindingCategory
