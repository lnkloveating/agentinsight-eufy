"""价格渠道模型输出的确定性 Evidence、范围、地区与时间门禁。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.agents.competitor.price_channel_contracts import (
    ChannelObservation,
    PriceChannelEvidenceCoverage,
    PriceChannelModelOutput,
    PriceChannelPayload,
    PriceGapSeverity,
    PriceObservation,
    PriceResearchGap,
)
from app.integrations.a2a import (
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    EvidenceRequest,
)
from app.schemas.evidence import EvidenceClaimType
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext, ResearchTaskStatus

ALLOWED_PRICE_CLAIM_TYPES = {
    EvidenceClaimType.PRICE_OBSERVATION.value,
    EvidenceClaimType.CHANNEL_AVAILABILITY.value,
    EvidenceClaimType.SELLER_INFORMATION.value,
    EvidenceClaimType.PROMOTION.value,
}


@dataclass(frozen=True)
class PriceChannelValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class PriceChannelOutputValidator:
    def build_blocked(
        self,
        *,
        a2a_task_id: str,
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
    ) -> CompetitorSpecialistArtifact:
        gap = PriceResearchGap(
            scope_label=request.product_scope[0] if request.product_scope else "未指定产品",
            question="缺少哪些目标地区的已审核价格渠道证据？",
            reason=(
                "Evidence Context 中没有同时满足 price_channel 路由、产品、地区、状态和"
                "Claim 类型要求的证据。"
            ),
            severity=PriceGapSeverity.HIGH,
            recommended_source_types=["official_store_page", "authorized_channel_page"],
        )
        payload = PriceChannelPayload(
            summary="没有可供价格渠道专家使用的有效证据，未调用模型生成结论。",
            summary_evidence_ids=[],
            price_observations=[],
            channel_observations=[],
            contradictions=[],
            research_gaps=[gap],
            evidence_coverage=self._coverage(
                request,
                evidence_context,
                cited_ids=set(),
                source_count=0,
                price_products=set(),
                channel_products=set(),
                price_count=0,
                channel_count=0,
                time_count=0,
            ),
        )
        return CompetitorSpecialistArtifact(
            a2a_task_id=a2a_task_id,
            request_id=request.request_id,
            specialist_type=request.specialist_type,
            status=ResearchTaskStatus.BLOCKED,
            findings=[],
            evidence_ids=[],
            unknowns=[gap.question],
            errors=["PRICE_CHANNEL_EVIDENCE_REQUIRED"],
            quality_score=0,
            structured_payload=payload.model_dump(mode="json"),
        )

    def validate(
        self,
        *,
        a2a_task_id: str,
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
        output: PriceChannelModelOutput,
    ) -> CompetitorSpecialistArtifact:
        evidence_by_id = {item.evidence_id: item for item in evidence_context.items}
        cited_ids = output.cited_evidence_ids()
        unsupported = sorted(cited_ids - set(evidence_by_id))
        if unsupported:
            raise PriceChannelValidationError(
                "价格渠道输出引用了未提供给模型的 Evidence。",
                {"unsupported_evidence_ids": unsupported},
            )
        disallowed = sorted(
            evidence_id
            for evidence_id in cited_ids
            if evidence_by_id[evidence_id].claim_type not in ALLOWED_PRICE_CLAIM_TYPES
        )
        if disallowed:
            raise PriceChannelValidationError(
                "价格渠道输出引用了不允许的 Evidence Claim 类型。",
                {"disallowed_evidence_ids": disallowed},
            )

        requested_scope = set(request.product_scope)
        represented_scope = {
            *(item.scope_label for item in output.price_observations),
            *(item.scope_label for item in output.channel_observations),
            *(item.scope_label for item in output.research_gaps),
        }
        unexpected_scope = sorted(represented_scope - requested_scope)
        if unexpected_scope:
            raise PriceChannelValidationError(
                "价格渠道输出包含主管请求范围外的产品。",
                {"unexpected_scope_labels": unexpected_scope},
            )

        prices = [
            self._price_observation(item, request, evidence_by_id)
            for item in output.price_observations
        ]
        channels = [
            self._channel_observation(item, request, evidence_by_id)
            for item in output.channel_observations
        ]
        observation_ids = {
            *(item.observation_id for item in prices),
            *(item.observation_id for item in channels),
        }
        if len(observation_ids) != len(prices) + len(channels):
            raise PriceChannelValidationError(
                "价格渠道 observation_id 重复。", {"duplicate_observation_id": True}
            )

        price_products = {item.scope_label for item in prices}
        channel_products = {item.scope_label for item in channels}
        observation_evidence_ids = {
            evidence_id
            for item in [*prices, *channels]
            for evidence_id in item.evidence_ids
        }
        sources = self._independent_sources(observation_evidence_ids, evidence_by_id)
        high_gap = any(gap.severity is PriceGapSeverity.HIGH for gap in output.research_gaps)
        completed = (
            bool(requested_scope)
            and price_products == requested_scope
            and channel_products == requested_scope
            and len(sources) >= request.minimum_independent_domains
            and not high_gap
        )
        status = ResearchTaskStatus.COMPLETED if completed else ResearchTaskStatus.PARTIAL
        coverage = self._coverage(
            request,
            evidence_context,
            cited_ids=cited_ids,
            source_count=len(sources),
            price_products=price_products,
            channel_products=channel_products,
            price_count=len(prices),
            channel_count=len(channels),
            time_count=len(prices) + len(channels),
        )
        payload = PriceChannelPayload(
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            price_observations=prices,
            channel_observations=channels,
            contradictions=output.contradictions,
            research_gaps=output.research_gaps,
            evidence_coverage=coverage,
        )
        return CompetitorSpecialistArtifact(
            a2a_task_id=a2a_task_id,
            request_id=request.request_id,
            specialist_type=request.specialist_type,
            status=status,
            findings=self._findings(prices, channels),
            evidence_ids=sorted(cited_ids),
            unknowns=self._unique(
                [*output.unknowns, *(gap.question for gap in output.research_gaps)]
            ),
            errors=[],
            quality_score=self._quality_score(
                request,
                output,
                price_products=price_products,
                channel_products=channel_products,
                source_count=len(sources),
            ),
            structured_payload=payload.model_dump(mode="json"),
        )

    def _price_observation(
        self,
        item: Any,
        request: EvidenceRequest,
        evidence_by_id: dict[str, AgentEvidence],
    ) -> PriceObservation:
        evidence = self._validate_observation_scope(item, request, evidence_by_id)
        if not any(
            candidate.claim_type == EvidenceClaimType.PRICE_OBSERVATION.value
            for candidate in evidence
        ):
            raise PriceChannelValidationError(
                "价格记录必须至少引用一条 price_observation Evidence。",
                {"observation_id": item.observation_id},
            )
        observed_from, observed_to = self._time_range(item.observation_id, evidence)
        return PriceObservation.model_validate(
            {
                **item.model_dump(mode="python"),
                "observed_from": observed_from,
                "observed_to": observed_to,
            }
        )

    def _channel_observation(
        self,
        item: Any,
        request: EvidenceRequest,
        evidence_by_id: dict[str, AgentEvidence],
    ) -> ChannelObservation:
        evidence = self._validate_observation_scope(item, request, evidence_by_id)
        if not any(
            candidate.claim_type == EvidenceClaimType.CHANNEL_AVAILABILITY.value
            for candidate in evidence
        ):
            raise PriceChannelValidationError(
                "渠道状态必须至少引用一条 channel_availability Evidence。",
                {"observation_id": item.observation_id},
            )
        observed_from, observed_to = self._time_range(item.observation_id, evidence)
        return ChannelObservation.model_validate(
            {
                **item.model_dump(mode="python"),
                "observed_from": observed_from,
                "observed_to": observed_to,
            }
        )

    @staticmethod
    def _validate_observation_scope(
        item: Any,
        request: EvidenceRequest,
        evidence_by_id: dict[str, AgentEvidence],
    ) -> list[AgentEvidence]:
        if item.scope_label not in request.product_scope:
            raise PriceChannelValidationError(
                "价格渠道记录包含主管请求范围外的产品。",
                {"observation_id": item.observation_id, "scope_label": item.scope_label},
            )
        if request.region is None or item.region.casefold() != request.region.casefold():
            raise PriceChannelValidationError(
                "价格渠道记录与主管请求地区不一致。",
                {"observation_id": item.observation_id, "region": item.region},
            )
        evidence = [evidence_by_id[evidence_id] for evidence_id in item.evidence_ids]
        wrong_product = sorted(
            candidate.evidence_id
            for candidate in evidence
            if candidate.product != item.scope_label
        )
        wrong_region = sorted(
            candidate.evidence_id
            for candidate in evidence
            if candidate.region is None
            or candidate.region.casefold() != request.region.casefold()
        )
        if wrong_product or wrong_region:
            raise PriceChannelValidationError(
                "价格渠道记录引用了产品或地区血缘不匹配的 Evidence。",
                {
                    "observation_id": item.observation_id,
                    "wrong_product_evidence_ids": wrong_product,
                    "wrong_region_evidence_ids": wrong_region,
                },
            )
        return evidence

    @staticmethod
    def _time_range(
        observation_id: str, evidence: list[AgentEvidence]
    ) -> tuple[datetime, datetime]:
        missing = sorted(item.evidence_id for item in evidence if item.collected_at is None)
        if missing:
            raise PriceChannelValidationError(
                "价格渠道事实缺少可审计的 Evidence 采集时间。",
                {"observation_id": observation_id, "missing_time_evidence_ids": missing},
            )
        timestamps = [item.collected_at for item in evidence if item.collected_at is not None]
        return min(timestamps), max(timestamps)

    @staticmethod
    def _findings(
        prices: list[PriceObservation], channels: list[ChannelObservation]
    ) -> list[CompetitorFinding]:
        findings: list[CompetitorFinding] = []
        for price in prices:
            qualifiers = [f"地区={price.region}", f"渠道={price.channel_name}"]
            if price.seller_name:
                qualifiers.append(f"卖家={price.seller_name}")
            if price.variant:
                qualifiers.append(f"变体={price.variant}")
            qualifiers.append(f"观察截至={price.observed_to.isoformat()}")
            findings.append(
                CompetitorFinding(
                    finding_id=price.observation_id,
                    category=f"price_{price.price_kind.value}",
                    statement=(
                        f"{price.scope_label} 的{price.price_kind.value}价格观察为 "
                        f"{format(price.amount, 'f')} {price.currency}"
                        f"（{'；'.join(qualifiers)}）。"
                    ),
                    evidence_ids=price.evidence_ids,
                    confidence=price.confidence,
                )
            )
        for channel in channels:
            findings.append(
                CompetitorFinding(
                    finding_id=channel.observation_id,
                    category="channel_availability",
                    statement=(
                        f"{channel.scope_label} 在 {channel.channel_name} 的渠道状态观察为 "
                        f"{channel.availability.value}（地区={channel.region}；"
                        f"观察截至={channel.observed_to.isoformat()}）。"
                    ),
                    evidence_ids=channel.evidence_ids,
                    confidence=channel.confidence,
                )
            )
        return findings

    @staticmethod
    def _coverage(
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
        *,
        cited_ids: set[str],
        source_count: int,
        price_products: set[str],
        channel_products: set[str],
        price_count: int,
        channel_count: int,
        time_count: int,
    ) -> PriceChannelEvidenceCoverage:
        return PriceChannelEvidenceCoverage(
            requested_product_count=len(request.product_scope),
            price_product_count=len(price_products),
            channel_product_count=len(channel_products),
            available_evidence_count=evidence_context.available_evidence_count,
            included_evidence_count=evidence_context.included_evidence_count,
            cited_evidence_count=len(cited_ids),
            independent_source_count=source_count,
            price_observation_count=price_count,
            channel_observation_count=channel_count,
            time_bounded_observation_count=time_count,
            context_hash=evidence_context.context_hash,
        )

    @staticmethod
    def _independent_sources(
        evidence_ids: set[str], evidence_by_id: dict[str, AgentEvidence]
    ) -> set[str]:
        sources: set[str] = set()
        for evidence_id in evidence_ids:
            evidence = evidence_by_id[evidence_id]
            if evidence.source_domain:
                sources.add(f"domain:{evidence.source_domain}")
            elif evidence.source_asset_id:
                sources.add(f"asset:{evidence.source_asset_id}")
            else:
                sources.add(f"source_type:{evidence.source_type}")
        return sources

    @staticmethod
    def _quality_score(
        request: EvidenceRequest,
        output: PriceChannelModelOutput,
        *,
        price_products: set[str],
        channel_products: set[str],
        source_count: int,
    ) -> float:
        requested = max(len(request.product_scope), 1)
        score = min(len(price_products) / requested, 1.0) * 30
        score += min(len(channel_products) / requested, 1.0) * 20
        score += min(source_count / request.minimum_independent_domains, 1.0) * 25
        score += 15 if output.price_observations and output.channel_observations else 0
        score += 10 if output.contradictions else 0
        if any(gap.severity is PriceGapSeverity.HIGH for gap in output.research_gaps):
            score -= 15
        return max(0.0, min(round(score, 2), 100.0))

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value.strip()))
