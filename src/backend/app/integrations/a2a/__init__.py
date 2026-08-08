"""竞品研究的 A2A 调用边界。"""

from app.integrations.a2a.contracts import (
    A2AErrorCode,
    A2AGatewayError,
    A2ASpecialistAdapter,
    A2ASpecialistInvocation,
    A2ATaskStatus,
    CompetitorA2ABatchError,
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
    EvidenceRequest,
    SpecialistTaskResult,
)
from app.integrations.a2a.gateway import CompetitorA2AGateway
from app.integrations.a2a.registry import A2ASpecialistRegistry, SpecialistBinding

__all__ = [
    "A2AErrorCode",
    "A2AGatewayError",
    "A2ASpecialistAdapter",
    "A2ASpecialistInvocation",
    "A2ASpecialistRegistry",
    "A2ATaskStatus",
    "CompetitorA2ABatchError",
    "CompetitorA2AGateway",
    "CompetitorFinding",
    "CompetitorSpecialistArtifact",
    "CompetitorSpecialistType",
    "EvidenceRequest",
    "SpecialistBinding",
    "SpecialistTaskResult",
]
