"""官方产品模型输出的确定性 Evidence 门禁与状态计算。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.agents.competitor.official_product_contracts import (
    GapSeverity,
    OfficialProductEvidenceCoverage,
    OfficialProductModelOutput,
    OfficialProductPayload,
    OfficialResearchGap,
)
from app.integrations.a2a import (
    CompetitorFinding,
    CompetitorSpecialistArtifact,
    EvidenceRequest,
)
from app.schemas.evidence import EvidenceClaimType
from app.workflows.contracts import AgentEvidence, AgentEvidenceContext, ResearchTaskStatus


@dataclass(frozen=True)
class OfficialProductValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class OfficialProductOutputValidator:
    def build_blocked(
        self,
        *,
        a2a_task_id: str,
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
    ) -> CompetitorSpecialistArtifact:
        gap = OfficialResearchGap(
            scope_label=request.product_scope[0] if request.product_scope else "未指定产品",
            question="缺少哪些可用于官方产品研究的已验证资料？",
            reason="Evidence Context 中没有 vendor_claim 或 fact 类型的有效证据。",
            severity=GapSeverity.HIGH,
            recommended_source_types=["official_product_page", "official_document"],
        )
        payload = OfficialProductPayload(
            summary="没有可供官方产品专家使用的有效证据，未调用模型生成结论。",
            summary_evidence_ids=[],
            products=[],
            contradictions=[],
            research_gaps=[gap],
            evidence_coverage=self._coverage(
                request, evidence_context, set(), set(), represented_count=0
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
            errors=["OFFICIAL_PRODUCT_EVIDENCE_REQUIRED"],
            quality_score=0,
            structured_payload=payload.model_dump(mode="json"),
        )

    def validate(
        self,
        *,
        a2a_task_id: str,
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
        output: OfficialProductModelOutput,
    ) -> CompetitorSpecialistArtifact:
        evidence_by_id = {item.evidence_id: item for item in evidence_context.items}
        cited_ids = output.cited_evidence_ids()
        unsupported = sorted(cited_ids - set(evidence_by_id))
        if unsupported:
            raise OfficialProductValidationError(
                "官方产品输出引用了未提供给模型的 Evidence。",
                {"unsupported_evidence_ids": unsupported},
            )
        disallowed = sorted(
            evidence_id
            for evidence_id in cited_ids
            if evidence_by_id[evidence_id].claim_type
            not in {
                EvidenceClaimType.VENDOR_CLAIM.value,
                EvidenceClaimType.FACT.value,
            }
        )
        if disallowed:
            raise OfficialProductValidationError(
                "官方产品输出引用了不允许的 Evidence Claim 类型。",
                {"disallowed_evidence_ids": disallowed},
            )

        requested_scope = set(request.product_scope)
        represented_scope = {product.scope_label for product in output.products}
        unexpected_scope = sorted(represented_scope - requested_scope)
        if unexpected_scope:
            raise OfficialProductValidationError(
                "官方产品输出包含主管请求范围外的产品。",
                {"unexpected_scope_labels": unexpected_scope},
            )

        independent_sources = self._independent_sources(cited_ids, evidence_by_id)
        high_gap = any(gap.severity is GapSeverity.HIGH for gap in output.research_gaps)
        each_product_has_facts = bool(output.products) and all(
            product.facts for product in output.products
        )
        completed = (
            bool(requested_scope)
            and represented_scope == requested_scope
            and each_product_has_facts
            and len(independent_sources) >= request.minimum_independent_domains
            and not high_gap
        )
        status = ResearchTaskStatus.COMPLETED if completed else ResearchTaskStatus.PARTIAL
        coverage = self._coverage(
            request,
            evidence_context,
            cited_ids,
            independent_sources,
            represented_count=len(represented_scope),
        )
        payload = OfficialProductPayload(
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            products=output.products,
            contradictions=output.contradictions,
            research_gaps=output.research_gaps,
            evidence_coverage=coverage,
        )
        findings = self._findings(output)
        unknowns = self._unique([*output.unknowns, *(gap.question for gap in output.research_gaps)])
        return CompetitorSpecialistArtifact(
            a2a_task_id=a2a_task_id,
            request_id=request.request_id,
            specialist_type=request.specialist_type,
            status=status,
            findings=findings,
            evidence_ids=sorted(cited_ids),
            unknowns=unknowns,
            errors=[],
            quality_score=self._quality_score(
                request,
                output,
                represented_scope=represented_scope,
                source_count=len(independent_sources),
            ),
            structured_payload=payload.model_dump(mode="json"),
        )

    @staticmethod
    def _findings(output: OfficialProductModelOutput) -> list[CompetitorFinding]:
        findings: list[CompetitorFinding] = []
        for product in output.products:
            model_suffix = (
                f"，型号：{', '.join(product.model_numbers)}" if product.model_numbers else ""
            )
            findings.append(
                CompetitorFinding(
                    finding_id=(
                        "identity_"
                        + hashlib.sha256(product.scope_label.encode("utf-8")).hexdigest()[:16]
                    ),
                    category="official_identity",
                    statement=(
                        f"{product.scope_label} 对应官方名称：{product.official_name}"
                        f"{model_suffix}。"
                    ),
                    evidence_ids=product.evidence_ids,
                    confidence=min([fact.confidence for fact in product.facts] or [0.8]),
                )
            )
            for fact in product.facts:
                qualifiers = "；".join(
                    f"{key}={value}" for key, value in sorted(fact.qualifiers.items())
                )
                qualifier_suffix = f"（{qualifiers}）" if qualifiers else ""
                findings.append(
                    CompetitorFinding(
                        finding_id=fact.fact_id,
                        category=fact.fact_type.value,
                        statement=(
                            f"{product.scope_label}：{fact.field_name}={fact.value}"
                            f"{qualifier_suffix}。"
                        ),
                        evidence_ids=fact.evidence_ids,
                        confidence=fact.confidence,
                    )
                )
        return findings

    @staticmethod
    def _coverage(
        request: EvidenceRequest,
        evidence_context: AgentEvidenceContext,
        cited_ids: set[str],
        independent_sources: set[str],
        *,
        represented_count: int,
    ) -> OfficialProductEvidenceCoverage:
        by_id = {item.evidence_id: item for item in evidence_context.items}
        return OfficialProductEvidenceCoverage(
            requested_product_count=len(request.product_scope),
            represented_product_count=represented_count,
            available_evidence_count=evidence_context.available_evidence_count,
            included_evidence_count=evidence_context.included_evidence_count,
            cited_evidence_count=len(cited_ids),
            independent_source_count=len(independent_sources),
            vendor_claim_count=sum(
                by_id[evidence_id].claim_type == EvidenceClaimType.VENDOR_CLAIM.value
                for evidence_id in cited_ids
            ),
            fact_count=sum(
                by_id[evidence_id].claim_type == EvidenceClaimType.FACT.value
                for evidence_id in cited_ids
            ),
            context_hash=evidence_context.context_hash,
        )

    @staticmethod
    def _independent_sources(
        evidence_ids: set[str],
        evidence_by_id: dict[str, AgentEvidence],
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
        output: OfficialProductModelOutput,
        *,
        represented_scope: set[str],
        source_count: int,
    ) -> float:
        requested = max(len(request.product_scope), 1)
        score = min(len(represented_scope) / requested, 1.0) * 35
        score += min(source_count / request.minimum_independent_domains, 1.0) * 20
        score += 25 if output.products and all(product.facts for product in output.products) else 0
        score += 10 if output.summary_evidence_ids else 0
        score += 10 if output.contradictions else 0
        if any(gap.severity is GapSeverity.HIGH for gap in output.research_gaps):
            score -= 15
        return max(0.0, min(round(score, 2), 100.0))

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value.strip()))
