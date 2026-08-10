"""Build one shared, bounded Evidence Context for all competitor ecosystem specialists."""

from app.application.evidence import EvidenceRetrievalService
from app.infrastructure.database.session import Database
from app.schemas.evidence import EvidenceClaimType
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery
from app.workflows.contracts import AgentEvidenceContext


class CompetitorEcosystemEvidenceContextBuilder:
    def __init__(
        self,
        database: Database,
        *,
        max_items: int,
        max_excerpt_chars: int,
        max_total_chars: int,
    ) -> None:
        if max_items <= 0 or max_excerpt_chars <= 0 or max_total_chars <= 0:
            raise ValueError("competitor ecosystem evidence limits must be positive")
        self.retrieval = EvidenceRetrievalService(database)
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars

    async def build(self, project_id: str) -> AgentEvidenceContext:
        result = await self.retrieval.retrieve(
            project_id,
            EvidenceRetrievalQuery(
                consumer="competitor_ecosystem_analysis",
                claim_types=[
                    EvidenceClaimType.FACT,
                    EvidenceClaimType.USER_OPINION,
                    EvidenceClaimType.VENDOR_CLAIM,
                    EvidenceClaimType.PRODUCT_IDENTITY,
                    EvidenceClaimType.CAPABILITY,
                    EvidenceClaimType.SPECIFICATION,
                    EvidenceClaimType.COMPATIBILITY,
                    EvidenceClaimType.LIMITATION,
                    EvidenceClaimType.PRICE_OBSERVATION,
                    EvidenceClaimType.CHANNEL_AVAILABILITY,
                    EvidenceClaimType.SELLER_INFORMATION,
                    EvidenceClaimType.PROMOTION,
                    EvidenceClaimType.MARKET_FACT,
                    EvidenceClaimType.TECHNICAL_FACT,
                ],
                max_items=self.max_items,
                max_excerpt_chars=self.max_excerpt_chars,
                max_total_chars=self.max_total_chars,
                candidate_limit=min(max(self.max_items * 10, self.max_items), 2_000),
            ),
        )
        return result.context
