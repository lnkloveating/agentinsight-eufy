"""Build the minimum Evidence context allowed by the research handoff."""

from __future__ import annotations

import hashlib
import json

from app.agents.user_research.context import UserResearchEvidenceContextBuilder
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.session import Database
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
        self.database = database
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars

    async def build(self, project_id: str, handoff: ResearchHandoff) -> AgentEvidenceContext:
        requested = list(
            dict.fromkeys(
                [*handoff.merged_evidence_ids, *handoff.supplemental_evidence_ids]
            )
        )
        async with self.database.session() as session:
            models = await EvidenceRepository(session).get_evidence_by_ids(set(requested))
        by_id = {model.evidence_id: model for model in models if model.project_id == project_id}
        items = []
        remaining = self.max_total_chars
        for evidence_id in requested[: self.max_items]:
            model = by_id.get(evidence_id)
            if model is None or remaining <= 0:
                continue
            excerpt = model.original_excerpt[: min(self.max_excerpt_chars, remaining)].strip()
            if not excerpt:
                continue
            items.append(UserResearchEvidenceContextBuilder._to_agent_evidence(model, excerpt))
            remaining -= len(excerpt)
        canonical = json.dumps(
            [item.model_dump(mode="json") for item in items],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return AgentEvidenceContext(
            items=items,
            available_evidence_count=len(requested),
            included_evidence_count=len(items),
            omitted_evidence_count=max(len(requested) - len(items), 0),
            context_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
