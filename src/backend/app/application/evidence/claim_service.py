"""Claim 创建与 Evidence Gate 应用用例。"""

from uuid import uuid4

from app.core.errors import AppError
from app.evidence.claim_gate import ClaimGate, EvidenceCandidate
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import ClaimEvidenceLinkModel, ClaimModel
from app.schemas.evidence import (
    Claim,
    ClaimCreate,
    ClaimGateResult,
    EvidenceRelationship,
    EvidenceStatus,
)


class ClaimService:
    def __init__(self, repository: EvidenceRepository, gate: ClaimGate | None = None) -> None:
        self.repository = repository
        self.gate = gate or ClaimGate()

    async def create_and_evaluate(
        self, project_id: str, payload: ClaimCreate
    ) -> ClaimGateResult:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )

        requested_ids = set(payload.evidence_ids) | set(payload.contradicting_evidence_ids)
        evidence_models = await self.repository.get_evidence_by_ids(requested_ids)
        candidates = [
            EvidenceCandidate(
                evidence_id=model.evidence_id,
                project_id=model.project_id,
                status=EvidenceStatus(model.status),
            )
            for model in evidence_models
        ]
        decision = self.gate.evaluate(
            project_id=project_id,
            claim_type=payload.claim_type,
            requested_supporting_ids=payload.evidence_ids,
            requested_contradicting_ids=payload.contradicting_evidence_ids,
            candidates=candidates,
        )

        claim_model = ClaimModel(
            claim_id=f"claim_{uuid4().hex[:16]}",
            project_id=project_id,
            statement=payload.statement,
            claim_type=payload.claim_type,
            scope_json=payload.scope,
            status=decision.status,
        )
        links = [
            self._link(
                project_id,
                claim_model.claim_id,
                evidence_id,
                EvidenceRelationship.SUPPORTS,
            )
            for evidence_id in decision.supporting_evidence_ids
        ]
        links.extend(
            self._link(
                project_id,
                claim_model.claim_id,
                evidence_id,
                EvidenceRelationship.CONTRADICTS,
            )
            for evidence_id in decision.contradicting_evidence_ids
        )

        try:
            await self.repository.add_claim(claim_model)
            for link in links:
                await self.repository.add_claim_evidence_link(link)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise

        claim = Claim.model_validate(
            {
                "claim_id": claim_model.claim_id,
                "statement": claim_model.statement,
                "claim_type": claim_model.claim_type,
                "evidence_ids": list(decision.supporting_evidence_ids),
                "contradicting_evidence_ids": list(decision.contradicting_evidence_ids),
                "scope": claim_model.scope_json,
                "status": claim_model.status,
            }
        )
        return ClaimGateResult(
            claim=claim,
            eligible_for_factual_use=decision.eligible_for_factual_use,
            rejected_evidence_ids=decision.rejected_evidence_ids,
        )

    @staticmethod
    def _link(
        project_id: str,
        claim_id: str,
        evidence_id: str,
        relationship: EvidenceRelationship,
    ) -> ClaimEvidenceLinkModel:
        return ClaimEvidenceLinkModel(
            link_id=f"link_{uuid4().hex[:16]}",
            project_id=project_id,
            claim_id=claim_id,
            evidence_id=evidence_id,
            relation_type=relationship,
        )
