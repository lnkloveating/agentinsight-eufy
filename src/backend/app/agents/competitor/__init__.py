"""竞品研究主管及其 A2A 专家边界。"""

from app.agents.competitor.discovery_adapter import CompetitorDiscoveryModelAgentAdapter
from app.agents.competitor.discovery_contracts import (
    CompetitorCandidateDecision,
    CompetitorCandidateDecisionAction,
    CompetitorCandidateDecisionCreate,
    CompetitorCandidateDecisionResult,
    CompetitorCandidateGateStatus,
    CompetitorDiscoveryArtifact,
    CompetitorDiscoveryRunCreate,
)
from app.agents.competitor.discovery_prompt import register_competitor_discovery_prompt
from app.agents.competitor.ecosystem_adapter import CompetitorEcosystemModelAdapter
from app.agents.competitor.ecosystem_contracts import (
    CompetitorEcosystemArtifact,
    CompetitorEcosystemEvidenceAudit,
    CompetitorEcosystemModelOutput,
    CompetitorEcosystemPayload,
    CompetitorEcosystemProfile,
    EcosystemCapabilityAssessment,
    EcosystemCapabilityDimension,
    EcosystemCapabilityStatus,
    EcosystemComparisonInsight,
    EcosystemDimensionCoverage,
    EcosystemDiscoveryProjection,
    EcosystemGapSeverity,
    EcosystemOpportunitySignal,
    EcosystemResearchGap,
    EcosystemRole,
    EcosystemSourceDimension,
)
from app.agents.competitor.ecosystem_prompt import register_competitor_ecosystem_prompt
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
from app.agents.competitor.price_channel_adapter import PriceChannelModelSpecialistAdapter
from app.agents.competitor.price_channel_context import PriceChannelEvidenceContextBuilder
from app.agents.competitor.price_channel_contracts import (
    ChannelAvailabilityStatus,
    ChannelObservation,
    ChannelObservationDraft,
    PriceChannelEvidenceCoverage,
    PriceChannelModelOutput,
    PriceChannelPayload,
    PriceGapSeverity,
    PriceKind,
    PriceObservation,
    PriceObservationDraft,
    PriceResearchGap,
)
from app.agents.competitor.price_channel_prompt import register_price_channel_prompt
from app.agents.competitor.supervisor import (
    CompetitorA2ASupervisorAdapter,
    build_competitor_evidence_requests,
)
from app.agents.competitor.synthesis_adapter import CompetitorSynthesisModelAdapter
from app.agents.competitor.synthesis_contracts import (
    ComparativeInsight,
    CompetitorEvidenceAudit,
    CompetitorProductProfile,
    CompetitorSynthesisModelOutput,
    CompetitorSynthesisPayload,
    HypothesisStatus,
    OpportunitySignal,
    ProductAssessmentPoint,
    ProductDimensionCoverage,
    SynthesisDimension,
    SynthesisGapSeverity,
    SynthesisResearchGap,
)
from app.agents.competitor.synthesis_prompt import register_competitor_synthesis_prompt
from app.agents.competitor.user_review_adapter import (
    CompetitorUserReviewModelSpecialistAdapter,
)
from app.agents.competitor.user_review_context import UserReviewEvidenceContextBuilder
from app.agents.competitor.user_review_contracts import (
    CompetitorUserReviewEvidenceCoverage,
    CompetitorUserReviewModelOutput,
    CompetitorUserReviewPayload,
    ReviewContradiction,
    ReviewGapSeverity,
    ReviewRecurrenceStatus,
    ReviewResearchGap,
    ReviewSampleLimitation,
    ReviewSentiment,
    ReviewTheme,
    ReviewThemeDraft,
)
from app.agents.competitor.user_review_prompt import (
    register_competitor_user_review_prompt,
)

__all__ = [
    "CompetitorCandidateDecision",
    "CompetitorCandidateDecisionAction",
    "CompetitorCandidateDecisionCreate",
    "CompetitorCandidateDecisionResult",
    "CompetitorCandidateGateStatus",
    "CompetitorDiscoveryArtifact",
    "CompetitorDiscoveryModelAgentAdapter",
    "CompetitorDiscoveryRunCreate",
    "CompetitorEcosystemArtifact",
    "CompetitorEcosystemEvidenceAudit",
    "CompetitorEcosystemModelAdapter",
    "CompetitorEcosystemModelOutput",
    "CompetitorEcosystemPayload",
    "CompetitorEcosystemProfile",
    "CompetitorA2ASupervisorAdapter",
    "CompetitorEvidenceAudit",
    "CompetitorProductProfile",
    "CompetitorSynthesisModelAdapter",
    "CompetitorSynthesisModelOutput",
    "CompetitorSynthesisPayload",
    "CompetitorUserReviewEvidenceCoverage",
    "CompetitorUserReviewModelOutput",
    "CompetitorUserReviewModelSpecialistAdapter",
    "CompetitorUserReviewPayload",
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
    "ChannelAvailabilityStatus",
    "ChannelObservation",
    "ChannelObservationDraft",
    "PriceChannelEvidenceContextBuilder",
    "PriceChannelEvidenceCoverage",
    "PriceChannelModelOutput",
    "PriceChannelModelSpecialistAdapter",
    "PriceChannelPayload",
    "PriceGapSeverity",
    "PriceKind",
    "PriceObservation",
    "PriceObservationDraft",
    "PriceResearchGap",
    "ProductAssessmentPoint",
    "ProductDimensionCoverage",
    "ComparativeInsight",
    "HypothesisStatus",
    "EcosystemCapabilityAssessment",
    "EcosystemCapabilityDimension",
    "EcosystemCapabilityStatus",
    "EcosystemComparisonInsight",
    "EcosystemDimensionCoverage",
    "EcosystemDiscoveryProjection",
    "EcosystemGapSeverity",
    "EcosystemOpportunitySignal",
    "EcosystemResearchGap",
    "EcosystemRole",
    "EcosystemSourceDimension",
    "OpportunitySignal",
    "ReviewContradiction",
    "ReviewGapSeverity",
    "ReviewRecurrenceStatus",
    "ReviewResearchGap",
    "ReviewSampleLimitation",
    "ReviewSentiment",
    "ReviewTheme",
    "ReviewThemeDraft",
    "SynthesisDimension",
    "SynthesisGapSeverity",
    "SynthesisResearchGap",
    "UserReviewEvidenceContextBuilder",
    "build_competitor_evidence_requests",
    "register_competitor_discovery_prompt",
    "register_competitor_ecosystem_prompt",
    "register_competitor_user_review_prompt",
    "register_competitor_synthesis_prompt",
    "register_official_product_prompt",
    "register_price_channel_prompt",
]
