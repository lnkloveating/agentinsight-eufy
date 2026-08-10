"""所有领域 Agent 共用的项目级 Evidence 检索服务。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from app.core.errors import AppError
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import EvidenceModel
from app.infrastructure.database.session import Database
from app.schemas.evidence_retrieval import (
    EvidenceRetrievalMatch,
    EvidenceRetrievalQuery,
    EvidenceRetrievalResult,
    EvidenceRetrievalStrategy,
)
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._+-]*|[\u3400-\u4dbf\u4e00-\u9fff]+")


@dataclass(frozen=True, slots=True)
class _RankedEvidence:
    model: EvidenceModel
    relevance_score: float
    quality_score: float
    matched_terms: tuple[str, ...]
    match_reasons: tuple[str, ...]

    @property
    def ranking_score(self) -> float:
        return self.relevance_score * 0.75 + self.quality_score * 0.25


class EvidenceRetrievalService:
    """Deterministic retrieval foundation; no generation or vector provider is used."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def retrieve(
        self,
        project_id: str,
        query: EvidenceRetrievalQuery,
    ) -> EvidenceRetrievalResult:
        async with self.database.session() as session:
            repository = EvidenceRepository(session)
            if not await repository.project_exists(project_id):
                raise AppError(
                    code="PROJECT_NOT_FOUND",
                    message="研究项目不存在。",
                    status_code=404,
                    details={"project_id": project_id},
                )
            candidates, metadata_count = await repository.list_retrieval_candidates(
                project_id,
                statuses={status.value for status in query.statuses},
                claim_types=self._enum_values(query.claim_types),
                source_types=self._optional_set(query.source_types),
                source_asset_ids=self._optional_set(query.source_asset_ids),
                evidence_ids=self._optional_set(query.evidence_ids),
                products=self._casefold_set(query.products),
                regions=self._casefold_set(query.regions),
                user_segments=self._casefold_set(query.user_segments),
                limit=query.candidate_limit,
            )

        terms = self._query_terms(query.question)
        ranked = [self._rank(model, terms, query) for model in candidates]
        if query.require_text_match:
            ranked = [item for item in ranked if item.relevance_score > 0]

        strategy = self._strategy(query, terms)
        if query.preserve_evidence_order:
            requested_order = {
                evidence_id: index for index, evidence_id in enumerate(query.evidence_ids)
            }
            ranked.sort(
                key=lambda item: requested_order.get(
                    item.model.evidence_id, len(requested_order)
                )
            )
        else:
            ranked.sort(
                key=lambda item: (
                    -item.ranking_score,
                    -item.relevance_score,
                    -item.quality_score,
                    item.model.evidence_id,
                )
            )

        selected = self._select(ranked, query)
        context_items: list[AgentEvidence] = []
        matches: list[EvidenceRetrievalMatch] = []
        remaining_chars = query.max_total_chars
        for ranked_item in selected:
            if remaining_chars <= 0:
                break
            excerpt = ranked_item.model.original_excerpt[
                : min(query.max_excerpt_chars, remaining_chars)
            ].strip()
            if not excerpt:
                continue
            context_items.append(self._to_agent_evidence(ranked_item.model, excerpt))
            matches.append(
                EvidenceRetrievalMatch(
                    evidence_id=ranked_item.model.evidence_id,
                    rank=len(matches) + 1,
                    relevance_score=ranked_item.relevance_score,
                    matched_terms=list(ranked_item.matched_terms),
                    match_reasons=list(ranked_item.match_reasons),
                )
            )
            remaining_chars -= len(excerpt)

        available_count = len(ranked) if query.require_text_match else metadata_count
        context = AgentEvidenceContext(
            items=context_items,
            available_evidence_count=available_count,
            included_evidence_count=len(context_items),
            omitted_evidence_count=max(available_count - len(context_items), 0),
            context_hash=self.context_hash(context_items),
        )
        return EvidenceRetrievalResult(
            consumer=query.consumer,
            strategy=strategy,
            query_hash=self.query_hash(query),
            candidate_evidence_count=metadata_count,
            context=context,
            matches=matches,
        )

    @staticmethod
    def query_hash(query: EvidenceRetrievalQuery) -> str:
        canonical = json.dumps(
            query.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def context_hash(items: list[AgentEvidence]) -> str:
        canonical = json.dumps(
            [item.model_dump(mode="json") for item in items],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def empty_context(cls) -> AgentEvidenceContext:
        return AgentEvidenceContext(
            items=[],
            available_evidence_count=0,
            included_evidence_count=0,
            omitted_evidence_count=0,
            context_hash=cls.context_hash([]),
        )

    @classmethod
    def _rank(
        cls,
        model: EvidenceModel,
        terms: tuple[str, ...],
        query: EvidenceRetrievalQuery,
    ) -> _RankedEvidence:
        fields = {
            "title": (cls._normalize(model.title), 4.0),
            "product": (cls._normalize(model.product), 3.0),
            "region": (cls._normalize(model.region), 2.0),
            "user_segment": (cls._normalize(model.user_segment), 2.0),
            "excerpt": (cls._normalize(model.original_excerpt), 1.0),
        }
        matched_terms: list[str] = []
        matched_fields: set[str] = set()
        lexical_score = 0.0
        for term in terms:
            matched = False
            for field_name, (field_text, weight) in fields.items():
                if term in field_text:
                    lexical_score += weight
                    matched_fields.add(field_name)
                    matched = True
            if matched:
                matched_terms.append(term)
        maximum_lexical_score = len(terms) * sum(weight for _, weight in fields.values())
        relevance = (
            min(lexical_score / maximum_lexical_score, 1.0)
            if maximum_lexical_score
            else 0.0
        )
        reasons = sorted(matched_fields)
        if query.claim_types:
            reasons.append("claim_type_filter")
        if query.source_types:
            reasons.append("source_type_filter")
        if query.source_asset_ids:
            reasons.append("source_route_filter")
        if query.evidence_ids:
            reasons.append("evidence_id_boundary")
        if query.products:
            reasons.append("product_filter")
        if query.regions:
            reasons.append("region_filter")
        if query.user_segments:
            reasons.append("user_segment_filter")
        quality = (
            model.confidence
            + model.authority_score
            + model.recency_score
            + model.diversity_score
        ) / 4
        return _RankedEvidence(
            model=model,
            relevance_score=round(relevance, 6),
            quality_score=quality,
            matched_terms=tuple(matched_terms),
            match_reasons=tuple(dict.fromkeys(reasons)),
        )

    @classmethod
    def _select(
        cls,
        ranked: list[_RankedEvidence],
        query: EvidenceRetrievalQuery,
    ) -> list[_RankedEvidence]:
        if not query.diversify_sources or query.preserve_evidence_order:
            return ranked[: query.max_items]
        selected: list[_RankedEvidence] = []
        deferred: list[_RankedEvidence] = []
        seen_sources: set[str] = set()
        for item in ranked:
            source_key = cls._source_key(item.model)
            if source_key in seen_sources:
                deferred.append(item)
                continue
            selected.append(item)
            seen_sources.add(source_key)
            if len(selected) >= query.max_items:
                return selected
        return [*selected, *deferred[: query.max_items - len(selected)]]

    @staticmethod
    def _source_key(model: EvidenceModel) -> str:
        if model.source_domain:
            return f"domain:{model.source_domain.casefold()}"
        if model.source_asset_id:
            return f"asset:{model.source_asset_id}"
        return f"source_type:{model.source_type.casefold()}"

    @classmethod
    def _query_terms(cls, question: str | None) -> tuple[str, ...]:
        if question is None:
            return ()
        normalized = cls._normalize(question)
        terms: list[str] = []
        for match in _TOKEN_PATTERN.finditer(normalized):
            token = match.group(0)
            if cls._contains_cjk(token) and len(token) > 2:
                terms.extend(token[index : index + 2] for index in range(len(token) - 1))
            terms.append(token)
        return tuple(dict.fromkeys(term for term in terms if term))

    @staticmethod
    def _contains_cjk(value: str) -> bool:
        return any("\u3400" <= char <= "\u9fff" for char in value)

    @staticmethod
    def _normalize(value: str | None) -> str:
        return unicodedata.normalize("NFKC", value or "").casefold()

    @staticmethod
    def _strategy(
        query: EvidenceRetrievalQuery,
        terms: tuple[str, ...],
    ) -> EvidenceRetrievalStrategy:
        if query.evidence_ids and query.preserve_evidence_order:
            return EvidenceRetrievalStrategy.EXACT_EVIDENCE_IDS
        if terms:
            return EvidenceRetrievalStrategy.LEXICAL_METADATA
        return EvidenceRetrievalStrategy.METADATA_QUALITY

    @staticmethod
    def _enum_values(values: Sequence[object]) -> set[str] | None:
        if not values:
            return None
        return {str(getattr(value, "value", value)) for value in values}

    @staticmethod
    def _optional_set(values: list[str]) -> set[str] | None:
        return set(values) if values else None

    @staticmethod
    def _casefold_set(values: list[str]) -> set[str] | None:
        return {value.casefold() for value in values} if values else None

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
            collected_at=model.collected_at,
            confidence=model.confidence,
            authority_score=model.authority_score,
            recency_score=model.recency_score,
            diversity_score=model.diversity_score,
        )
