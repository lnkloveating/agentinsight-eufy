"""从 Evidence Lake 构建官方产品专家的最小受控上下文。"""

from __future__ import annotations

import hashlib
import json

from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import EvidenceModel
from app.infrastructure.database.session import Database
from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext


class OfficialProductEvidenceContextBuilder:
    def __init__(
        self,
        database: Database,
        *,
        max_items: int,
        max_excerpt_chars: int,
        max_total_chars: int,
    ) -> None:
        if max_items <= 0 or max_excerpt_chars <= 0 or max_total_chars <= 0:
            raise ValueError("official product evidence limits must be positive")
        self.database = database
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars

    async def build(self, project_id: str) -> AgentEvidenceContext:
        candidate_limit = min(max(self.max_items * 10, self.max_items), 2_000)
        async with self.database.session() as session:
            candidates, available_count = await EvidenceRepository(
                session
            ).list_eligible_agent_evidence(
                project_id,
                statuses={
                    EvidenceStatus.VERIFIED.value,
                    EvidenceStatus.PARTIALLY_VERIFIED.value,
                },
                claim_types={
                    EvidenceClaimType.VENDOR_CLAIM.value,
                    EvidenceClaimType.FACT.value,
                },
                limit=candidate_limit,
            )

        items: list[AgentEvidence] = []
        remaining_chars = self.max_total_chars
        for model in self._select_diverse(candidates):
            if remaining_chars <= 0:
                break
            excerpt_limit = min(self.max_excerpt_chars, remaining_chars)
            excerpt = model.original_excerpt[:excerpt_limit].strip()
            if not excerpt:
                continue
            items.append(self._to_agent_evidence(model, excerpt))
            remaining_chars -= len(excerpt)
        return AgentEvidenceContext(
            items=items,
            available_evidence_count=available_count,
            included_evidence_count=len(items),
            omitted_evidence_count=max(available_count - len(items), 0),
            context_hash=self._context_hash(items),
        )

    def _select_diverse(self, candidates: list[EvidenceModel]) -> list[EvidenceModel]:
        selected: list[EvidenceModel] = []
        deferred: list[EvidenceModel] = []
        seen_sources: set[str] = set()
        for candidate in candidates:
            source_key = self._source_key(candidate)
            if source_key in seen_sources:
                deferred.append(candidate)
                continue
            selected.append(candidate)
            seen_sources.add(source_key)
            if len(selected) >= self.max_items:
                return selected
        for candidate in deferred:
            selected.append(candidate)
            if len(selected) >= self.max_items:
                break
        return selected

    @staticmethod
    def _source_key(model: EvidenceModel) -> str:
        if model.source_domain:
            return f"domain:{model.source_domain}"
        if model.source_asset_id:
            return f"asset:{model.source_asset_id}"
        return f"source_type:{model.source_type}"

    @staticmethod
    def _to_agent_evidence(model: EvidenceModel, excerpt: str) -> AgentEvidence:
        return AgentEvidence(
            evidence_id=model.evidence_id,
            title=model.title,
            original_excerpt=excerpt,
            claim_type=model.claim_type,
            status=model.status,
            source_type=model.source_type,
            source_url=model.source_url,
            source_domain=model.source_domain,
            source_asset_id=model.source_asset_id,
            source_fragment_id=model.source_fragment_id,
            source_locator=model.source_locator_json,
            product=model.product,
            region=model.region,
            user_segment=model.user_segment,
            published_at=model.published_at,
            confidence=model.confidence,
            authority_score=model.authority_score,
            recency_score=model.recency_score,
            diversity_score=model.diversity_score,
        )

    @staticmethod
    def _context_hash(items: list[AgentEvidence]) -> str:
        canonical = json.dumps(
            [item.model_dump(mode="json") for item in items],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
