"""竞品研究主管及其 A2A 专家边界。"""

from app.agents.competitor.official_product_adapter import (
    OfficialProductModelSpecialistAdapter,
)
from app.agents.competitor.official_product_context import (
    OfficialProductEvidenceContextBuilder,
)
from app.agents.competitor.official_product_contracts import (
    GapSeverity,
    OfficialFactType,
    OfficialProductEvidenceCoverage,
    OfficialProductFact,
    OfficialProductModelOutput,
    OfficialProductPayload,
    OfficialProductRecord,
    OfficialResearchGap,
)
from app.agents.competitor.official_product_prompt import (
    register_official_product_prompt,
)
from app.agents.competitor.supervisor import (
    CompetitorA2ASupervisorAdapter,
    build_competitor_evidence_requests,
)

__all__ = [
    "CompetitorA2ASupervisorAdapter",
    "GapSeverity",
    "OfficialFactType",
    "OfficialProductEvidenceContextBuilder",
    "OfficialProductEvidenceCoverage",
    "OfficialProductFact",
    "OfficialProductModelOutput",
    "OfficialProductModelSpecialistAdapter",
    "OfficialProductPayload",
    "OfficialProductRecord",
    "OfficialResearchGap",
    "build_competitor_evidence_requests",
    "register_official_product_prompt",
]
