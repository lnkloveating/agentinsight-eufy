"""从已确认用户评价资料构建产品受控的 Evidence Context。"""

from app.application.evidence import EvidenceRetrievalService
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_routing_repository import SourceRoutingRepository
from app.schemas.evidence import EvidenceClaimType
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery
from app.workflows.contracts import AgentEvidenceContext


class UserReviewEvidenceContextBuilder:
    def __init__(
        self,
        database: Database,
        *,
        max_items: int,
        max_excerpt_chars: int,
        max_total_chars: int,
    ) -> None:
        if max_items <= 0 or max_excerpt_chars <= 0 or max_total_chars <= 0:
            raise ValueError("user review evidence limits must be positive")
        self.database = database
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars
        self.retrieval = EvidenceRetrievalService(database)

    async def build(self, project_id: str) -> AgentEvidenceContext:
        candidate_limit = min(max(self.max_items * 20, self.max_items), 2_000)
        async with self.database.session() as session:
            source_asset_ids = await SourceRoutingRepository(session).confirmed_source_asset_ids(
                project_id, "user_review"
            )
        if not source_asset_ids:
            return self.retrieval.empty_context()
        result = await self.retrieval.retrieve(
            project_id,
            EvidenceRetrievalQuery(
                consumer="competitor_user_review",
                claim_types=[EvidenceClaimType.USER_OPINION],
                source_asset_ids=sorted(source_asset_ids),
                max_items=self.max_items,
                max_excerpt_chars=self.max_excerpt_chars,
                max_total_chars=self.max_total_chars,
                candidate_limit=candidate_limit,
            ),
        )
        return result.context
