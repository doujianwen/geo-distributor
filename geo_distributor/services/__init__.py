"""服务层包。

Sprint 0 新增服务：
    - intake: IntakeService（请求完整性验证）
    - scoping: ScopingService（商业→技术 Scope 转换）
    - project_service: ProjectService（Project 全生命周期管理）
"""

from .distribution import DistributionService
from .intake import IntakeService
from .scoping import ScopingService
from .project_service import ProjectService
from .intervention_loop import (
    InterventionRecommendation,
    InterventionExecution,
    BaselineMetrics,
    DeltaCalculator,
    ReMeasurementService,
)
from .evidence_library import EvidenceRecord, EvidenceLibraryService
from .measurement_analysis import aggregate_metrics

__all__ = [
    "DistributionService",
    "IntakeService",
    "ScopingService",
    "ProjectService",
    "InterventionRecommendation",
    "InterventionExecution",
    "BaselineMetrics",
    "DeltaCalculator",
    "ReMeasurementService",
    "EvidenceRecord",
    "EvidenceLibraryService",
    "aggregate_metrics",
]
