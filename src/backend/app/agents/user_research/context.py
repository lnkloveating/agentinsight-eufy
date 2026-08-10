"""从 Evidence Lake 构建用户研究 Agent 的确定性最小上下文。"""

from app.application.evidence import EvidenceRetrievalService
from app.infrastructure.database.session import Database
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery
from app.workflows.contracts import AgentEvidenceContext


class UserResearchEvidenceContextBuilder:
    def __init__(
        self,
        database: Database,
        *,
        max_items: int,
        max_excerpt_chars: int,
        max_total_chars: int,
    ) -> None:
        if max_items <= 0 or max_excerpt_chars <= 0 or max_total_chars <= 0:
            raise ValueError("user research evidence limits must be positive")
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars
        self.retrieval = EvidenceRetrievalService(database)

    async def build(self, project_id: str) -> AgentEvidenceContext:
        candidate_limit = min(max(self.max_items * 10, self.max_items), 2_000)
        result = await self.retrieval.retrieve(
            project_id,
            EvidenceRetrievalQuery(
                consumer="user_research",
                max_items=self.max_items,
                max_excerpt_chars=self.max_excerpt_chars,
                max_total_chars=self.max_total_chars,
                candidate_limit=candidate_limit,
            ),
        )
        return result.context
