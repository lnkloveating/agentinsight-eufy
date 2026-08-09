"""竞品用户评价输出的确定性 Evidence、产品与重复主题门禁。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.competitor.user_review_contracts import (
    CompetitorUserReviewEvidenceCoverage,
    CompetitorUserReviewModelOutput,
    CompetitorUserReviewPayload,
    ReviewGapSeverity,
    ReviewRecurrenceStatus,
    ReviewResearchGap,
    ReviewSentiment,
    ReviewTheme,
    ReviewThemeDraft,
)
from app.integrations.a2a import (
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    EvidenceRequest,
)
from app.schemas.evidence import EvidenceClaimType
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext, ResearchTaskStatus


@dataclass(frozen=True)
class CompetitorUserReviewValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class CompetitorUserReviewOutputValidator:
    def build_blocked(
        self,
        *,
        a2a_task_id: str,
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
    ) -> CompetitorSpecialistArtifact:
        gap = ReviewResearchGap(
            scope_label=request.product_scope[0] if request.product_scope else "未指定产品",
            question="缺少哪些与准确产品绑定的已审核用户评价？",
            reason=(
                "Evidence Context 中没有同时满足 user_review 路由、产品、状态和"
                "user_opinion Claim 类型要求的证据。"
            ),
            severity=ReviewGapSeverity.HIGH,
            recommended_source_types=["authorized_user_review", "authorized_research_file"],
        )
        payload = CompetitorUserReviewPayload(
            summary="没有可供竞品用户评价专家使用的有效证据，未调用模型生成结论。",
            summary_evidence_ids=[],
            review_themes=[],
            contradictions=[],
            sample_limitations=[],
            research_gaps=[gap],
            evidence_coverage=self._coverage(
                request,
                evidence_context,
                cited_ids=set(),
                source_count=0,
                represented_products=set(),
                repeated_products=set(),
                themes=[],
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
            errors=["COMPETITOR_USER_REVIEW_EVIDENCE_REQUIRED"],
            quality_score=0,
            structured_payload=payload.model_dump(mode="json"),
        )

    def validate(
        self,
        *,
        a2a_task_id: str,
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
        output: CompetitorUserReviewModelOutput,
    ) -> CompetitorSpecialistArtifact:
        evidence_by_id = {item.evidence_id: item for item in evidence_context.items}
        cited_ids = output.cited_evidence_ids()
        unsupported = sorted(cited_ids - set(evidence_by_id))
        if unsupported:
            raise CompetitorUserReviewValidationError(
                "竞品用户评价输出引用了未提供给模型的 Evidence。",
                {"unsupported_evidence_ids": unsupported},
            )
        disallowed = sorted(
            evidence_id
            for evidence_id in cited_ids
            if evidence_by_id[evidence_id].claim_type
            != EvidenceClaimType.USER_OPINION.value
        )
        if disallowed:
            raise CompetitorUserReviewValidationError(
                "竞品用户评价输出引用了非 user_opinion Evidence。",
                {"disallowed_evidence_ids": disallowed},
            )

        requested_scope = set(request.product_scope)
        represented_scope = {
            *(item.scope_label for item in output.review_themes),
            *(item.scope_label for item in output.contradictions),
            *(item.scope_label for item in output.sample_limitations),
            *(item.scope_label for item in output.research_gaps),
        }
        unexpected_scope = sorted(represented_scope - requested_scope)
        if unexpected_scope:
            raise CompetitorUserReviewValidationError(
                "竞品用户评价输出包含主管请求范围外的产品。",
                {"unexpected_scope_labels": unexpected_scope},
            )

        themes = [
            self._validated_theme(theme, request, evidence_by_id)
            for theme in output.review_themes
        ]
        self._validate_cited_scope(
            [*output.contradictions, *output.sample_limitations],
            requested_scope,
            evidence_by_id,
        )
        theme_products = {theme.scope_label for theme in themes}
        repeated_products = {
            theme.scope_label
            for theme in themes
            if theme.recurrence_status is ReviewRecurrenceStatus.REPEATED_ACROSS_SOURCES
        }
        theme_evidence_ids = {
            evidence_id for theme in themes for evidence_id in theme.evidence_ids
        }
        sources = self._independent_sources(theme_evidence_ids, evidence_by_id)
        high_gap = any(gap.severity is ReviewGapSeverity.HIGH for gap in output.research_gaps)
        completed = (
            bool(requested_scope)
            and theme_products == requested_scope
            and repeated_products == requested_scope
            and len(sources) >= request.minimum_independent_domains
            and not high_gap
        )
        status = ResearchTaskStatus.COMPLETED if completed else ResearchTaskStatus.PARTIAL
        coverage = self._coverage(
            request,
            evidence_context,
            cited_ids=cited_ids,
            source_count=len(sources),
            represented_products=theme_products,
            repeated_products=repeated_products,
            themes=themes,
        )
        payload = CompetitorUserReviewPayload(
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            review_themes=themes,
            contradictions=output.contradictions,
            sample_limitations=output.sample_limitations,
            research_gaps=output.research_gaps,
            evidence_coverage=coverage,
        )
        return CompetitorSpecialistArtifact(
            a2a_task_id=a2a_task_id,
            request_id=request.request_id,
            specialist_type=request.specialist_type,
            status=status,
            findings=self._findings(themes),
            evidence_ids=sorted(cited_ids),
            unknowns=self._unique(
                [*output.unknowns, *(gap.question for gap in output.research_gaps)]
            ),
            errors=[],
            quality_score=self._quality_score(
                request,
                output,
                represented_products=theme_products,
                repeated_products=repeated_products,
                source_count=len(sources),
            ),
            structured_payload=payload.model_dump(mode="json"),
        )

    def _validated_theme(
        self,
        theme: ReviewThemeDraft,
        request: EvidenceRequest,
        evidence_by_id: dict[str, AgentEvidence],
    ) -> ReviewTheme:
        if theme.scope_label not in request.product_scope:
            raise CompetitorUserReviewValidationError(
                "用户评价主题包含主管请求范围外的产品。",
                {"theme_id": theme.theme_id, "scope_label": theme.scope_label},
            )
        evidence = [evidence_by_id[evidence_id] for evidence_id in theme.evidence_ids]
        wrong_product = sorted(
            item.evidence_id for item in evidence if item.product != theme.scope_label
        )
        if wrong_product:
            raise CompetitorUserReviewValidationError(
                "用户评价主题引用了产品血缘不匹配的 Evidence。",
                {"theme_id": theme.theme_id, "wrong_product_evidence_ids": wrong_product},
            )
        if theme.region is not None:
            wrong_region = sorted(
                item.evidence_id
                for item in evidence
                if item.region is not None and item.region.casefold() != theme.region.casefold()
            )
            if wrong_region:
                raise CompetitorUserReviewValidationError(
                    "用户评价主题的地区与 Evidence 元数据冲突。",
                    {"theme_id": theme.theme_id, "wrong_region_evidence_ids": wrong_region},
                )
        if theme.user_segment is not None:
            wrong_segment = sorted(
                item.evidence_id
                for item in evidence
                if item.user_segment is not None
                and item.user_segment.casefold() != theme.user_segment.casefold()
            )
            if wrong_segment:
                raise CompetitorUserReviewValidationError(
                    "用户评价主题的用户分群与 Evidence 元数据冲突。",
                    {"theme_id": theme.theme_id, "wrong_segment_evidence_ids": wrong_segment},
                )
        source_count = len(self._independent_sources(set(theme.evidence_ids), evidence_by_id))
        recurrence = (
            ReviewRecurrenceStatus.REPEATED_ACROSS_SOURCES
            if len(theme.evidence_ids) >= 2 and source_count >= 2
            else ReviewRecurrenceStatus.SINGLE_REPORT
        )
        return ReviewTheme.model_validate(
            {
                **theme.model_dump(mode="python"),
                "support_count": len(theme.evidence_ids),
                "independent_source_count": source_count,
                "recurrence_status": recurrence,
            }
        )

    @staticmethod
    def _validate_cited_scope(
        items: list[Any],
        requested_scope: set[str],
        evidence_by_id: dict[str, AgentEvidence],
    ) -> None:
        for item in items:
            if item.scope_label not in requested_scope:
                raise CompetitorUserReviewValidationError(
                    "用户评价附属记录包含主管请求范围外的产品。",
                    {"scope_label": item.scope_label},
                )
            wrong_product = sorted(
                evidence_id
                for evidence_id in item.evidence_ids
                if evidence_by_id[evidence_id].product != item.scope_label
            )
            if wrong_product:
                raise CompetitorUserReviewValidationError(
                    "用户评价附属记录引用了产品血缘不匹配的 Evidence。",
                    {
                        "scope_label": item.scope_label,
                        "wrong_product_evidence_ids": wrong_product,
                    },
                )

    @staticmethod
    def _findings(themes: list[ReviewTheme]) -> list[CompetitorFinding]:
        return [
            CompetitorFinding(
                finding_id=theme.theme_id,
                category=f"user_review_{theme.sentiment.value}",
                statement=(
                    f"{theme.scope_label} 用户评价主题：{theme.theme}；"
                    f"事件={theme.event_context}；影响={theme.user_impact}；"
                    f"重复性={theme.recurrence_status.value}。"
                ),
                evidence_ids=theme.evidence_ids,
                confidence=theme.confidence,
            )
            for theme in themes
        ]

    @staticmethod
    def _coverage(
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
        *,
        cited_ids: set[str],
        source_count: int,
        represented_products: set[str],
        repeated_products: set[str],
        themes: list[ReviewTheme],
    ) -> CompetitorUserReviewEvidenceCoverage:
        return CompetitorUserReviewEvidenceCoverage(
            requested_product_count=len(request.product_scope),
            represented_product_count=len(represented_products),
            repeated_theme_product_count=len(repeated_products),
            available_evidence_count=evidence_context.available_evidence_count,
            included_evidence_count=evidence_context.included_evidence_count,
            cited_evidence_count=len(cited_ids),
            independent_source_count=source_count,
            review_theme_count=len(themes),
            single_report_theme_count=sum(
                theme.recurrence_status is ReviewRecurrenceStatus.SINGLE_REPORT
                for theme in themes
            ),
            repeated_theme_count=sum(
                theme.recurrence_status is ReviewRecurrenceStatus.REPEATED_ACROSS_SOURCES
                for theme in themes
            ),
            positive_theme_count=sum(
                theme.sentiment is ReviewSentiment.POSITIVE for theme in themes
            ),
            negative_theme_count=sum(
                theme.sentiment is ReviewSentiment.NEGATIVE for theme in themes
            ),
            mixed_theme_count=sum(theme.sentiment is ReviewSentiment.MIXED for theme in themes),
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
        output: CompetitorUserReviewModelOutput,
        *,
        represented_products: set[str],
        repeated_products: set[str],
        source_count: int,
    ) -> float:
        requested = max(len(request.product_scope), 1)
        score = min(len(represented_products) / requested, 1.0) * 25
        score += min(len(repeated_products) / requested, 1.0) * 30
        score += min(source_count / request.minimum_independent_domains, 1.0) * 25
        score += 10 if output.sample_limitations else 0
        score += 10 if output.contradictions else 0
        if any(gap.severity is ReviewGapSeverity.HIGH for gap in output.research_gaps):
            score -= 15
        return max(0.0, min(round(score, 2), 100.0))

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value.strip()))
