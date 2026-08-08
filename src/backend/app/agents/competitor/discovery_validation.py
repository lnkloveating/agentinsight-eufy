"""竞品候选输出的确定性 candidate_id、目标范围和质量门禁。"""

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.agents.competitor.discovery_contracts import (
    CompetitorDiscoveryCoverage,
    CompetitorDiscoveryInputContext,
    CompetitorDiscoveryModelOutput,
    CompetitorDiscoveryPayload,
    CompetitorDiscoveryProposal,
)
from app.workflows.contracts import (
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)


@dataclass(frozen=True)
class CompetitorDiscoveryValidationError(ValueError):
    message: str
    details: dict[str, Any]

    def __str__(self) -> str:
        return self.message


class CompetitorDiscoveryOutputValidator:
    def validate(
        self,
        task: ResearchTask,
        context: CompetitorDiscoveryInputContext,
        output: CompetitorDiscoveryModelOutput,
    ) -> ResearchArtifact:
        input_ids = {item.candidate_id for item in context.candidates}
        proposal_ids = [
            candidate_id
            for proposal in output.proposals
            for candidate_id in proposal.candidate_ids
        ]
        excluded_ids = [
            candidate_id
            for exclusion in output.excluded_candidates
            for candidate_id in exclusion.candidate_ids
        ]
        cited_ids = proposal_ids + excluded_ids
        unsupported = sorted(set(cited_ids) - input_ids)
        if unsupported:
            raise CompetitorDiscoveryValidationError(
                "竞品候选输出引用了未提供给模型的 candidate_id。",
                {"unsupported_candidate_ids": unsupported},
            )
        duplicate_ids = sorted(
            candidate_id for candidate_id in set(cited_ids) if cited_ids.count(candidate_id) > 1
        )
        if duplicate_ids:
            raise CompetitorDiscoveryValidationError(
                "每个搜索候选只能被一个提名或排除结论使用。",
                {"duplicate_candidate_ids": duplicate_ids},
            )
        unaccounted = sorted(input_ids - set(cited_ids))
        if unaccounted:
            raise CompetitorDiscoveryValidationError(
                "竞品候选输出没有处理全部输入 candidate_id。",
                {"unaccounted_candidate_ids": unaccounted},
            )

        target_identities = {
            self._product_identity(item.brand, item.model or "", item.variant)
            for item in context.target_products
        }
        proposal_identities = [
            self._product_identity(item.brand, item.model, item.variant)
            for item in output.proposals
        ]
        duplicates = sorted(
            " ".join(part for part in identity if part)
            for identity in set(proposal_identities)
            if proposal_identities.count(identity) > 1
        )
        if duplicates:
            raise CompetitorDiscoveryValidationError(
                "竞品候选输出包含重复产品。",
                {"duplicate_products": duplicates},
            )
        target_overlap = sorted(
            " ".join(part for part in identity if part)
            for identity in set(proposal_identities) & target_identities
        )
        if target_overlap:
            raise CompetitorDiscoveryValidationError(
                "目标产品不能被提名为自身竞品。",
                {"target_product_overlap": target_overlap},
            )

        candidates_by_id = {item.candidate_id: item for item in context.candidates}
        unsubstantiated_products: list[str] = []
        for proposal in output.proposals:
            candidate_text = " ".join(
                f"{candidates_by_id[candidate_id].title} "
                f"{candidates_by_id[candidate_id].snippet}"
                for candidate_id in proposal.candidate_ids
            )
            normalized_candidate_text = self._normalize_text(candidate_text)
            required_parts = [proposal.brand, proposal.model]
            if proposal.variant is not None:
                required_parts.append(proposal.variant)
            if any(
                self._normalize_text(part) not in normalized_candidate_text
                for part in required_parts
            ):
                unsubstantiated_products.append(
                    " ".join(
                        part
                        for part in (proposal.brand, proposal.model, proposal.variant)
                        if part
                    )
                )
        if unsubstantiated_products:
            raise CompetitorDiscoveryValidationError(
                "竞品品牌、型号或变体没有在所引用的搜索候选文本中明确出现。",
                {"unsubstantiated_products": sorted(unsubstantiated_products)},
            )

        proposals = [self._proposal(item) for item in output.proposals]
        status = (
            ResearchTaskStatus.COMPLETED
            if len(proposals) >= context.minimum_candidates
            else ResearchTaskStatus.PARTIAL
            if proposals
            else ResearchTaskStatus.BLOCKED
        )
        coverage = CompetitorDiscoveryCoverage(
            input_candidate_count=len(input_ids),
            accounted_candidate_count=len(cited_ids),
            proposal_count=len(proposals),
            exact_model_count=len(proposals),
            minimum_candidates=context.minimum_candidates,
            context_hash=context.context_hash,
        )
        payload = CompetitorDiscoveryPayload(
            summary=output.summary,
            target_products=context.target_products,
            input_candidates=context.candidates,
            proposals=proposals,
            excluded_candidates=output.excluded_candidates,
            research_gaps=output.research_gaps,
            coverage=coverage,
        )
        unknowns = list(
            dict.fromkeys(
                [
                    *output.unknowns,
                    *(gap.question for gap in output.research_gaps),
                    *(
                        [
                            f"仅识别出 {len(proposals)} 个准确型号，少于要求的 "
                            f"{context.minimum_candidates} 个。"
                        ]
                        if len(proposals) < context.minimum_candidates
                        else []
                    ),
                ]
            )
        )
        return ResearchArtifact(
            artifact_id="artifact_pending",
            task_id=task.task_id,
            artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
            schema_version="1.0",
            status=status,
            payload=payload.model_dump(mode="json"),
            evidence_ids=[],
            contradictions=[],
            unknowns=unknowns,
            quality_score=self._quality_score(output, context),
            errors=(
                []
                if proposals
                else ["COMPETITOR_DISCOVERY_EXACT_MODEL_CANDIDATE_REQUIRED"]
            ),
        )

    @staticmethod
    def _proposal(model: Any) -> CompetitorDiscoveryProposal:
        identity = CompetitorDiscoveryOutputValidator._product_identity(
            model.brand, model.model, model.variant
        )
        digest = hashlib.sha256("|".join(identity).encode("utf-8")).hexdigest()
        return CompetitorDiscoveryProposal(
            proposal_id=f"proposal_{digest[:16]}",
            **model.model_dump(),
        )

    @staticmethod
    def _product_identity(brand: str, model: str, variant: str | None) -> tuple[str, str, str]:
        return (
            brand.strip().casefold(),
            model.strip().casefold(),
            (variant or "").strip().casefold(),
        )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold(), flags=re.UNICODE)

    @staticmethod
    def _quality_score(
        output: CompetitorDiscoveryModelOutput,
        context: CompetitorDiscoveryInputContext,
    ) -> float:
        proposal_count = len(output.proposals)
        score = 30.0
        score += min(proposal_count / context.minimum_candidates, 1.0) * 40
        if output.proposals:
            score += sum(item.confidence for item in output.proposals) / proposal_count * 20
        score += 10 if not output.research_gaps else max(0, 10 - len(output.research_gaps) * 2)
        return min(round(score, 2), 100.0)
