"""Build the minimum Evidence context allowed by the research handoff."""

from app.application.evidence import EvidenceRetrievalService
from app.infrastructure.database.session import Database
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery
from app.workflows.contracts import AgentEvidenceContext, ResearchHandoff


class ProductTechnicalEvidenceContextBuilder:
    def __init__(
        self,
        database: Database,
        *,
        max_items: int,
        max_excerpt_chars: int,
        max_total_chars: int,
    ) -> None:
        if max_items <= 0 or max_excerpt_chars <= 0 or max_total_chars <= 0:
            raise ValueError("product technical evidence limits must be positive")
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars
        self.retrieval = EvidenceRetrievalService(database)

    async def build(self, project_id: str, handoff: ResearchHandoff) -> AgentEvidenceContext:
        requested = list(
            dict.fromkeys(
                [*handoff.merged_evidence_ids, *handoff.supplemental_evidence_ids]
            )
        )
        if not requested:
            return self.retrieval.empty_context()
        bounded_requested = requested[:500]
        result = await self.retrieval.retrieve(
            project_id,
            EvidenceRetrievalQuery(
                consumer="product_technical",
                evidence_ids=bounded_requested,
                max_items=min(self.max_items, len(bounded_requested)),
                max_excerpt_chars=self.max_excerpt_chars,
                max_total_chars=self.max_total_chars,
                candidate_limit=max(self.max_items, len(bounded_requested)),
                diversify_sources=False,
                preserve_evidence_order=True,
            ),
        )
        return result.context
