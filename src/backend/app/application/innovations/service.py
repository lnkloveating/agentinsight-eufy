"""候选场景创建、评分、红队评审和查询用例。"""

from datetime import UTC, datetime
from uuid import uuid4

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.domain.innovation import (
    EventUnderstandingGate,
    InnovationPortfolioGate,
    InnovationRuleError,
    InnovationScorer,
)
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.innovation_repository import InnovationRepository
from app.infrastructure.database.models import InnovationModel, ProjectEventModel
from app.infrastructure.database.repositories import ProjectRepository
from app.schemas.evidence import EvidenceStatus
from app.schemas.innovation import (
    Innovation,
    InnovationCreate,
    InnovationPortfolioGateResult,
    InnovationScoreInput,
    InnovationStatus,
    RedTeamDecision,
    RedTeamReview,
)

_ELIGIBLE_EVIDENCE_STATUSES = {
    EvidenceStatus.VERIFIED,
    EvidenceStatus.PARTIALLY_VERIFIED,
}


class InnovationService:
    def __init__(
        self,
        repository: InnovationRepository,
        evidence_repository: EvidenceRepository,
        project_repository: ProjectRepository,
        trace_id: str,
        event_broker: ProjectEventBroker,
    ) -> None:
        self.repository = repository
        self.evidence_repository = evidence_repository
        self.project_repository = project_repository
        self.trace_id = trace_id
        self.event_broker = event_broker
        self.event_gate = EventUnderstandingGate()
        self.scorer = InnovationScorer()
        self.portfolio_gate = InnovationPortfolioGate()

    async def create(self, project_id: str, payload: InnovationCreate) -> Innovation:
        await self._require_project(project_id)
        valid_evidence_ids, evidence_issues = await self._validate_evidence(
            project_id, payload.evidence_ids
        )
        if not valid_evidence_ids:
            raise AppError(
                code="INNOVATION_EVIDENCE_REQUIRED",
                message="候选场景至少需要一条同项目且已验证的 Evidence。",
                status_code=422,
                details={"issues": evidence_issues},
            )

        event_result = self.event_gate.evaluate(payload.event_understanding)
        gate_issues = [*evidence_issues, *event_result.issues]
        if evidence_issues:
            status = InnovationStatus.EVIDENCE_PENDING
        elif not event_result.passed:
            status = InnovationStatus.NEEDS_REVISION
        elif not payload.technical_assessment:
            status = InnovationStatus.TECH_REVIEW
        else:
            status = InnovationStatus.BUSINESS_REVIEW

        now = datetime.now(UTC)
        model = InnovationModel(
            innovation_id=f"inv_{uuid4().hex[:16]}",
            project_id=project_id,
            name=payload.name,
            status=status,
            target_user_json=payload.target_user.model_dump(mode="json"),
            problem_json=payload.problem.model_dump(mode="json"),
            event_understanding_json=payload.event_understanding.model_dump(mode="json"),
            competitor_gap_ids_json=list(dict.fromkeys(payload.competitor_gap_ids)),
            technical_assessment_json=payload.technical_assessment,
            business_assessment_json=payload.business_assessment,
            red_team_review_json=None,
            evidence_ids_json=valid_evidence_ids,
            score_breakdown_json={},
            base_score=0,
            final_score=0,
            gate_issues_json=gate_issues,
            created_at=now,
            updated_at=now,
        )
        try:
            await self.repository.add(model)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return self._to_innovation(model)

    async def score(
        self,
        project_id: str,
        innovation_id: str,
        payload: InnovationScoreInput,
    ) -> Innovation:
        model = await self._require_innovation(project_id, innovation_id)
        if model.gate_issues_json:
            raise AppError(
                code="INNOVATION_GATE_BLOCKED",
                message="候选场景仍有未解决的 Evidence 或事件理解缺口。",
                status_code=409,
                details={"issues": model.gate_issues_json},
            )
        if not model.technical_assessment_json or not model.business_assessment_json:
            raise AppError(
                code="INNOVATION_ASSESSMENT_INCOMPLETE",
                message="技术评估和商业评估完成后才能计算候选得分。",
                status_code=409,
                details={"innovation_id": innovation_id},
            )
        try:
            base_score = self.scorer.calculate_base_score(
                payload, allowed_evidence_ids=set(model.evidence_ids_json)
            )
        except InnovationRuleError as exc:
            raise AppError(
                code="INNOVATION_SCORE_INVALID",
                message="候选评分不符合统一维度、权重或 Evidence 规则。",
                status_code=422,
                details={"issues": list(exc.issues)},
            ) from exc

        now = datetime.now(UTC)
        model.score_breakdown_json = payload.model_dump(mode="json")["score_breakdown"]
        model.base_score = base_score
        model.final_score = base_score
        model.status = InnovationStatus.RED_TEAM_REVIEW
        model.updated_at = now
        await self._record_event(
            model,
            "innovation_scored",
            {
                "innovation_id": innovation_id,
                "base_score": base_score,
                "final_score": base_score,
                "status": model.status,
            },
            now,
        )
        return self._to_innovation(model)

    async def apply_red_team(
        self,
        project_id: str,
        innovation_id: str,
        review: RedTeamReview,
    ) -> Innovation:
        model = await self._require_innovation(project_id, innovation_id)
        if model.status != InnovationStatus.RED_TEAM_REVIEW or not model.score_breakdown_json:
            raise AppError(
                code="INNOVATION_NOT_READY_FOR_RED_TEAM",
                message="候选完成统一评分后才能提交红队评审。",
                status_code=409,
                details={"innovation_id": innovation_id, "status": model.status},
            )

        score_payload = InnovationScoreInput.model_validate(
            {"score_breakdown": model.score_breakdown_json}
        )
        final_score = self.scorer.apply_red_team(
            score_payload,
            review,
            allowed_evidence_ids=set(model.evidence_ids_json),
        )
        next_status = {
            RedTeamDecision.PASS: InnovationStatus.RECOMMENDED,
            RedTeamDecision.REVISE: InnovationStatus.NEEDS_REVISION,
            RedTeamDecision.RESEARCH_MORE: InnovationStatus.NEEDS_REVISION,
            RedTeamDecision.REJECT: InnovationStatus.REJECTED,
        }[review.decision]
        now = datetime.now(UTC)
        model.red_team_review_json = review.model_dump(mode="json")
        model.final_score = final_score
        model.status = next_status
        model.updated_at = now
        await self._record_event(
            model,
            "red_team_reviewed",
            {
                "innovation_id": innovation_id,
                "severity": review.severity,
                "decision": review.decision,
                "base_score": model.base_score,
                "final_score": final_score,
                "status": next_status,
                "required_actions": review.required_actions,
            },
            now,
        )
        return self._to_innovation(model)

    async def list_innovations(self, project_id: str) -> list[Innovation]:
        await self._require_project(project_id)
        return [
            self._to_innovation(model)
            for model in await self.repository.list_by_project(project_id)
        ]

    async def evaluate_portfolio(self, project_id: str) -> InnovationPortfolioGateResult:
        return self.portfolio_gate.evaluate(await self.list_innovations(project_id))

    async def _validate_evidence(
        self, project_id: str, requested_ids: list[str]
    ) -> tuple[list[str], list[str]]:
        unique_ids = list(dict.fromkeys(requested_ids))
        models = await self.evidence_repository.get_evidence_by_ids(set(unique_ids))
        by_id = {model.evidence_id: model for model in models}
        valid: list[str] = []
        issues: list[str] = []
        for evidence_id in unique_ids:
            model = by_id.get(evidence_id)
            if model is None:
                issues.append(f"evidence_not_found:{evidence_id}")
            elif model.project_id != project_id:
                issues.append(f"evidence_cross_project:{evidence_id}")
            elif EvidenceStatus(model.status) not in _ELIGIBLE_EVIDENCE_STATUSES:
                issues.append(f"evidence_status_not_eligible:{evidence_id}:{model.status}")
            else:
                valid.append(evidence_id)
        return valid, issues

    async def _record_event(
        self,
        model: InnovationModel,
        event_type: str,
        data: dict[str, object],
        now: datetime,
    ) -> None:
        try:
            await self.project_repository.add_event(
                ProjectEventModel(
                    event_id=f"evt_{uuid4().hex[:16]}",
                    project_id=model.project_id,
                    sequence_number=0,
                    event_type=event_type,
                    data_json=data,
                    trace_id=self.trace_id,
                    created_at=now,
                )
            )
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        await self.event_broker.notify(model.project_id)

    async def _require_project(self, project_id: str) -> None:
        if not await self.repository.project_exists(project_id):
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )

    async def _require_innovation(
        self, project_id: str, innovation_id: str
    ) -> InnovationModel:
        model = await self.repository.get(project_id, innovation_id)
        if model is None:
            raise AppError(
                code="INNOVATION_NOT_FOUND",
                message="候选场景不存在。",
                status_code=404,
                details={"project_id": project_id, "innovation_id": innovation_id},
            )
        return model

    @staticmethod
    def _to_innovation(model: InnovationModel) -> Innovation:
        return Innovation.model_validate(
            {
                "innovation_id": model.innovation_id,
                "name": model.name,
                "status": model.status,
                "target_user": model.target_user_json,
                "problem": model.problem_json,
                "event_understanding": model.event_understanding_json,
                "competitor_gap_ids": model.competitor_gap_ids_json,
                "technical_assessment": model.technical_assessment_json,
                "business_assessment": model.business_assessment_json,
                "red_team_review": model.red_team_review_json,
                "evidence_ids": model.evidence_ids_json,
                "score_breakdown": model.score_breakdown_json,
                "base_score": model.base_score,
                "final_score": model.final_score,
                "gate_issues": model.gate_issues_json,
            }
        )
