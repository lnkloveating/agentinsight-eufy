"""资料失败/不足后的确定性补充、证据入湖与恢复指令。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.application.events import ProjectEventBroker
from app.application.runtime import ArtifactAccessDeniedError, ArtifactStore
from app.application.runtime.contracts import StoredArtifact
from app.application.source_recovery.gaps import AgentGapProjector
from app.application.source_requirements import SourceRequirementService
from app.core.errors import AppError
from app.evidence.normalization import build_content_hash
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import (
    CollectionJobModel,
    EvidenceModel,
    ParsedArtifactModel,
    ProjectEventModel,
    SourceAssetModel,
    SourceFragmentModel,
    SourceRecoveryModel,
    SourceRecoverySubmissionModel,
    SourceRoutingModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.runtime_repository import AgentRuntimeRepository
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_recovery_repository import SourceRecoveryRepository
from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.schemas.source import (
    SourceAssetKind,
    SourceAssetStatus,
    SourceAuthorizationBasis,
    SourceMediaCategory,
)
from app.schemas.source_recovery import (
    AgentArtifactGap,
    AgentArtifactGapPage,
    AgentArtifactSourceRecoveryCreate,
    ProductTechnicalSourceRecoveryCreate,
    RecoverableAgentType,
    SourceRecovery,
    SourceRecoveryAnswer,
    SourceRecoveryCreate,
    SourceRecoveryDecisionAction,
    SourceRecoveryDecisionCreate,
    SourceRecoveryEvidenceSubmissionCreate,
    SourceRecoveryPage,
    SourceRecoveryReasonCode,
    SourceRecoveryRequestedField,
    SourceRecoveryResumeDirective,
    SourceRecoveryResumeMode,
    SourceRecoveryStatus,
    SourceRecoverySubmission,
    SourceRecoverySubmissionCreate,
    SourceRecoverySubmissionKind,
)
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    SourceRequirementAssessment,
    SourceRequirementItem,
    SourceRequirementStatus,
)
from app.schemas.source_routing import SourceRouteTarget
from app.workflows.contracts import ResearchAgentType

_TERMINAL_RECOVERY_STATUSES = {
    SourceRecoveryStatus.RESOLVED,
    SourceRecoveryStatus.PROCEEDING_WITH_GAPS,
    SourceRecoveryStatus.CANCELLED,
}

_DIMENSION_FIELDS: dict[CompetitorResearchDimension, tuple[tuple[EvidenceClaimType, bool], ...]] = {
    CompetitorResearchDimension.OFFICIAL_PRODUCT: (
        (EvidenceClaimType.CAPABILITY, True),
        (EvidenceClaimType.SPECIFICATION, False),
        (EvidenceClaimType.LIMITATION, False),
    ),
    CompetitorResearchDimension.PRICE_CHANNEL: (
        (EvidenceClaimType.PRICE_OBSERVATION, True),
        (EvidenceClaimType.CHANNEL_AVAILABILITY, False),
        (EvidenceClaimType.PROMOTION, False),
    ),
    CompetitorResearchDimension.USER_REVIEW: ((EvidenceClaimType.USER_OPINION, True),),
}

_FIELD_COPY: dict[EvidenceClaimType, tuple[str, str]] = {
    EvidenceClaimType.CAPABILITY: ("关键功能", "请填写该产品支持的关键功能或能力。"),
    EvidenceClaimType.SPECIFICATION: ("核心规格", "请填写与本次研究相关的核心规格。"),
    EvidenceClaimType.LIMITATION: ("已知限制", "请填写已知限制、缺失能力或使用条件。"),
    EvidenceClaimType.PRICE_OBSERVATION: ("当前价格", "请填写当前价格、币种及适用地区。"),
    EvidenceClaimType.CHANNEL_AVAILABILITY: ("销售渠道", "请填写可购买渠道和当前是否有货。"),
    EvidenceClaimType.PROMOTION: ("促销信息", "请填写促销价格及有效条件；没有可跳过。"),
    EvidenceClaimType.USER_OPINION: (
        "用户反馈",
        "请填写可复述的用户评价、使用场景及主要优缺点。",
    ),
}

_AGENT_BY_ROUTE: dict[SourceRouteTarget, tuple[ResearchAgentType, ...]] = {
    SourceRouteTarget.OFFICIAL_PRODUCT: (ResearchAgentType.COMPETITOR_RESEARCH,),
    SourceRouteTarget.PRICE_CHANNEL: (ResearchAgentType.COMPETITOR_RESEARCH,),
    SourceRouteTarget.USER_REVIEW: (ResearchAgentType.COMPETITOR_RESEARCH,),
    SourceRouteTarget.USER_RESEARCH: (ResearchAgentType.USER_RESEARCH,),
    SourceRouteTarget.MEDIA_REVIEW: (ResearchAgentType.USER_RESEARCH,),
    SourceRouteTarget.TECHNICAL_DOCUMENT: (ResearchAgentType.PRODUCT_TECHNICAL,),
    SourceRouteTarget.MARKET_RESEARCH: (
        ResearchAgentType.PRODUCT_TECHNICAL,
        ResearchAgentType.COMMERCIAL_EVALUATION,
    ),
    SourceRouteTarget.COMMERCIAL_DATA: (ResearchAgentType.COMMERCIAL_EVALUATION,),
    SourceRouteTarget.ENTERPRISE_INTERNAL: (
        ResearchAgentType.USER_RESEARCH,
        ResearchAgentType.COMPETITOR_RESEARCH,
    ),
}


class SourceRecoveryService:
    """不调用模型；只编排已有确定性资料与 Evidence 能力。"""

    def __init__(
        self,
        database: Database,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.event_broker = event_broker
        self.trace_id = trace_id
        self.requirements = SourceRequirementService(database, event_broker, trace_id)

    async def create(self, project_id: str, payload: SourceRecoveryCreate) -> SourceRecovery:
        assessment = await self.requirements.get(project_id)
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            asset = await repository.get_source_asset(project_id, payload.source_asset_id)
            if asset is None:
                raise self._not_found("SOURCE_ASSET_NOT_FOUND", "没有找到待恢复的资料。")
            job = await repository.get_collection_job(project_id, asset.collection_job_id)
            if job is None:
                raise self._not_found("COLLECTION_JOB_NOT_FOUND", "资料处理任务不存在。")
            existing = await repository.find_open_for_source(project_id, asset.source_asset_id)
            if existing is not None:
                return self._to_recovery(existing)

            requirements = self._select_requirements(
                assessment, asset.source_asset_id, payload.requirement_ids
            )
            requested_fields = self._build_requested_fields(requirements, assessment.region)
            if not requested_fields:
                requested_fields = self._build_generic_fields(
                    asset.source_asset_id,
                    payload.missing_questions,
                    assessment.region,
                    asset.purpose,
                )
            if not requested_fields:
                raise AppError(
                    code="SOURCE_RECOVERY_FIELDS_NOT_AVAILABLE",
                    message="当前缺口不能通过补充事实解决，请先确认研究范围或准确型号。",
                    status_code=409,
                    details={"missing_actions": assessment.missing_actions},
                )
            if (
                job.status == "succeeded"
                and requirements
                and all(item.status is SourceRequirementStatus.SATISFIED for item in requirements)
            ):
                raise AppError(
                    code="SOURCE_RECOVERY_NOT_REQUIRED",
                    message="该资料已处理成功且相关资料要求已经满足。",
                    status_code=409,
                )

            reason_code, reason_message = self._classify_reason(job.error_code, job.status)
            affected_agent_types = (
                list(payload.affected_agent_types)
                if payload.affected_agent_types
                else self._affected_agent_types(requested_fields)
            )
            affected_task_ids = list(payload.affected_task_ids)
            if job.task_id and job.task_id not in affected_task_ids:
                affected_task_ids.append(job.task_id)
            now = datetime.now(UTC)
            recovery = SourceRecoveryModel(
                source_recovery_id=f"recovery_{uuid4().hex[:16]}",
                project_id=project_id,
                failed_source_asset_id=asset.source_asset_id,
                failed_collection_job_id=job.collection_job_id,
                source_artifact_id=None,
                source_gap_ids_json=[],
                status=SourceRecoveryStatus.WAITING_FOR_USER_INPUT,
                reason_code=reason_code,
                reason_message=reason_message,
                requirement_ids_json=list(
                    dict.fromkeys(item.requirement_id for item in requested_fields)
                ),
                requested_fields_json=[item.model_dump(mode="json") for item in requested_fields],
                affected_task_ids_json=affected_task_ids,
                affected_agent_types_json=affected_agent_types,
                assessment_before_json=assessment.model_dump(mode="json"),
                current_assessment_json=assessment.model_dump(mode="json"),
                requested_by=payload.requested_by,
                request_reason=payload.reason,
                trace_id=self.trace_id,
                created_at=now,
                updated_at=now,
            )
            event = self._event(
                project_id,
                "source_recovery_requested",
                {
                    "source_recovery_id": recovery.source_recovery_id,
                    "source_asset_id": asset.source_asset_id,
                    "reason_code": reason_code,
                    "requirement_ids": recovery.requirement_ids_json,
                    "requested_field_count": len(requested_fields),
                    "affected_task_ids": affected_task_ids,
                    "affected_agent_types": affected_agent_types,
                },
                now,
            )
            try:
                await repository.add_recovery(recovery)
                await ProjectRepository(session).add_event(event)
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise
        await self.event_broker.notify(project_id)
        return await self.get(project_id, recovery.source_recovery_id)

    async def create_from_product_technical(
        self,
        project_id: str,
        artifact_id: str,
        payload: ProductTechnicalSourceRecoveryCreate,
    ) -> SourceRecovery:
        return await self.create_from_agent_artifact(
            project_id,
            RecoverableAgentType.PRODUCT_TECHNICAL,
            artifact_id,
            payload,
        )

    async def list_agent_artifact_gaps(
        self,
        project_id: str,
        agent_type: RecoverableAgentType,
        artifact_id: str,
    ) -> AgentArtifactGapPage:
        _, gaps = await self._load_agent_artifact_gaps(project_id, agent_type, artifact_id)
        return AgentArtifactGapPage(
            artifact_id=artifact_id,
            agent_type=agent_type,
            items=gaps,
            total=len(gaps),
        )

    async def create_from_agent_artifact(
        self,
        project_id: str,
        agent_type: RecoverableAgentType,
        artifact_id: str,
        payload: AgentArtifactSourceRecoveryCreate,
    ) -> SourceRecovery:
        stored, gaps = await self._load_agent_artifact_gaps(project_id, agent_type, artifact_id)
        gaps_by_id = {gap.gap_id: gap for gap in gaps}
        selected_ids = payload.gap_ids or list(gaps_by_id)
        missing_ids = sorted(set(selected_ids) - set(gaps_by_id))
        if missing_ids:
            raise AppError(
                code="AGENT_ARTIFACT_GAP_NOT_FOUND",
                message="选择的补研缺口不属于该 Agent Artifact。",
                status_code=422,
                details={"gap_ids": missing_ids},
            )
        if not selected_ids:
            raise AppError(
                code="AGENT_ARTIFACT_RECOVERY_NOT_REQUIRED",
                message="该 Agent Artifact 没有需要用户补充的资料缺口。",
                status_code=409,
                details={"artifact_id": artifact_id, "agent_type": agent_type.value},
            )
        selected_gaps = [gaps_by_id[gap_id] for gap_id in selected_ids]
        fields, affected_agents = self._build_agent_gap_fields(selected_gaps)
        affected_agents.add(agent_type.value)
        assessment = await self.requirements.get(project_id)
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            await self._require_project(repository, project_id)
            for existing in await repository.list_open_for_artifact(project_id, artifact_id):
                if set(existing.source_gap_ids_json) == set(selected_ids):
                    return self._to_recovery(existing)

            input_models = await AgentRuntimeRepository(session).get_artifacts_by_ids(
                set(stored.input_artifact_ids)
            )
            affected_task_ids = [stored.artifact.task_id]
            for model in input_models:
                if model.artifact_type in affected_agents:
                    affected_task_ids.append(model.task_id)
            affected_task_ids = list(dict.fromkeys(affected_task_ids))
            now = datetime.now(UTC)
            recovery = SourceRecoveryModel(
                source_recovery_id=f"recovery_{uuid4().hex[:16]}",
                project_id=project_id,
                failed_source_asset_id=None,
                failed_collection_job_id=None,
                source_artifact_id=artifact_id,
                source_gap_ids_json=selected_ids,
                status=SourceRecoveryStatus.WAITING_FOR_USER_INPUT,
                reason_code=SourceRecoveryReasonCode.INSUFFICIENT_INFORMATION,
                reason_message=(
                    f"{agent_type.value} Artifact 缺少可验证信息，需要用户或企业补充事实。"
                ),
                requirement_ids_json=list(dict.fromkeys(field.requirement_id for field in fields)),
                requested_fields_json=[field.model_dump(mode="json") for field in fields],
                affected_task_ids_json=affected_task_ids,
                affected_agent_types_json=sorted(affected_agents),
                assessment_before_json=assessment.model_dump(mode="json"),
                current_assessment_json=assessment.model_dump(mode="json"),
                requested_by=payload.requested_by,
                request_reason=payload.reason,
                trace_id=self.trace_id,
                created_at=now,
                updated_at=now,
            )
            event = self._event(
                project_id,
                "source_recovery_requested",
                {
                    "source_recovery_id": recovery.source_recovery_id,
                    "source_artifact_id": artifact_id,
                    "source_gap_ids": selected_ids,
                    "requested_field_count": len(fields),
                    "affected_task_ids": affected_task_ids,
                    "affected_agent_types": sorted(affected_agents),
                    "origin": "agent_artifact_gap",
                    "agent_type": agent_type.value,
                },
                now,
            )
            try:
                await repository.add_recovery(recovery)
                await ProjectRepository(session).add_event(event)
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise
        await self.event_broker.notify(project_id)
        return await self.get(project_id, recovery.source_recovery_id)

    async def _load_agent_artifact_gaps(
        self,
        project_id: str,
        agent_type: RecoverableAgentType,
        artifact_id: str,
    ) -> tuple[StoredArtifact, list[AgentArtifactGap]]:
        try:
            stored = await ArtifactStore(self.database).get(project_id, artifact_id)
        except ArtifactAccessDeniedError as exc:
            raise self._not_found(
                "AGENT_ARTIFACT_NOT_FOUND",
                "没有找到当前项目的 Agent Artifact。",
            ) from exc
        if stored is None:
            raise self._not_found(
                "AGENT_ARTIFACT_NOT_FOUND",
                "没有找到当前项目的 Agent Artifact。",
            )
        if stored.artifact.artifact_type != agent_type.value:
            raise AppError(
                code="AGENT_ARTIFACT_TYPE_MISMATCH",
                message="路径中的 Agent 类型与 Artifact 类型不一致。",
                status_code=422,
                details={
                    "artifact_id": artifact_id,
                    "expected_agent_type": agent_type.value,
                    "actual_agent_type": stored.artifact.artifact_type,
                },
            )
        gaps = AgentGapProjector().project(stored.artifact, agent_type)
        return stored, gaps

    async def get(self, project_id: str, source_recovery_id: str) -> SourceRecovery:
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            await self._require_project(repository, project_id)
            model = await repository.get(project_id, source_recovery_id)
            if model is None:
                raise self._not_found("SOURCE_RECOVERY_NOT_FOUND", "没有找到指定的资料恢复任务。")
            return self._to_recovery(model)

    async def list_recoveries(self, project_id: str) -> SourceRecoveryPage:
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            await self._require_project(repository, project_id)
            models = await repository.list(project_id)
            return SourceRecoveryPage(
                items=[self._to_recovery(model) for model in models], total=len(models)
            )

    async def submit(
        self,
        project_id: str,
        source_recovery_id: str,
        payload: SourceRecoverySubmissionCreate,
    ) -> SourceRecovery:
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            recovery = await self._require_recovery(repository, project_id, source_recovery_id)
            replay = await repository.get_submission_by_request(
                source_recovery_id, payload.request_id
            )
            if replay is not None:
                return self._to_recovery(recovery)
            self._require_open(recovery)
            requested_fields = {
                item.field_id: item
                for item in map(
                    SourceRecoveryRequestedField.model_validate,
                    recovery.requested_fields_json,
                )
            }
            unknown_fields = sorted(
                {answer.field_id for answer in payload.answers} - set(requested_fields)
            )
            if unknown_fields:
                raise AppError(
                    code="SOURCE_RECOVERY_FIELD_UNKNOWN",
                    message="提交内容包含不属于当前恢复任务的字段。",
                    status_code=422,
                    details={"field_ids": unknown_fields},
                )
            generic_required_fields = {
                field.field_id
                for field in requested_fields.values()
                if field.required
                and field.requirement_id.startswith(
                    (
                        "requirement_source_gap_",
                        "requirement_product_gap_",
                        "requirement_agent_gap_",
                    )
                )
            }
            missing_generic_fields = sorted(
                generic_required_fields - {answer.field_id for answer in payload.answers}
            )
            if missing_generic_fields:
                raise AppError(
                    code="SOURCE_RECOVERY_REQUIRED_FIELD_MISSING",
                    message="通用资料缺口必须逐项回答；不知道时请选择带缺口继续。",
                    status_code=422,
                    details={"field_ids": missing_generic_fields},
                )

            now = datetime.now(UTC)
            submission_id = f"submission_{uuid4().hex[:12]}"
            source_asset_id = f"source_{uuid4().hex[:16]}"
            collection_job_id = f"job_{uuid4().hex[:16]}"
            parsed_artifact_id = f"parsed_{uuid4().hex[:16]}"
            answer_rows = [
                self._answer_row(answer, requested_fields[answer.field_id])
                for answer in payload.answers
            ]
            canonical = json.dumps(
                {
                    "source_recovery_id": source_recovery_id,
                    "request_id": payload.request_id,
                    "answers": answer_rows,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            product_labels = sorted(
                {
                    self._product_label(field.product)
                    for field in requested_fields.values()
                    if field.product is not None
                }
            )
            display_name = "用户补充资料"
            if product_labels:
                display_name = f"用户补充：{'、'.join(product_labels)}"

            job = CollectionJobModel(
                collection_job_id=collection_job_id,
                project_id=project_id,
                task_id=(
                    recovery.affected_task_ids_json[0] if recovery.affected_task_ids_json else None
                ),
                source_url=None,
                source_type="user_declaration",
                status="succeeded",
                attempt_count=1,
                result_json={
                    "source_recovery_id": source_recovery_id,
                    "submission_id": submission_id,
                    "user_supplied": True,
                },
                started_at=now,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
            asset = SourceAssetModel(
                source_asset_id=source_asset_id,
                project_id=project_id,
                collection_job_id=collection_job_id,
                kind=SourceAssetKind.USER_INPUT,
                status=SourceAssetStatus.READY,
                display_name=display_name,
                original_filename=None,
                source_url=None,
                normalized_source_url=None,
                storage_key=None,
                media_type="application/json",
                media_category=SourceMediaCategory.DATASET,
                content_hash=content_hash,
                byte_size=len(canonical.encode("utf-8")),
                authorization_basis=payload.authorization_basis,
                authorization_confirmed_at=now,
                authorized_by=payload.actor,
                purpose=f"补充资料恢复任务 {source_recovery_id} 缺少的具体内容",
                created_at=now,
                updated_at=now,
            )
            artifact = ParsedArtifactModel(
                parsed_artifact_id=parsed_artifact_id,
                project_id=project_id,
                source_asset_id=source_asset_id,
                collection_job_id=collection_job_id,
                parser_id="source_recovery_structured_input",
                parser_version="1.0",
                source_content_hash=content_hash,
                fragment_count=len(answer_rows),
                created_at=now,
            )

            routes = sorted(
                {
                    field.route.value
                    for field in requested_fields.values()
                    if field.route is not None
                    and field.field_id in {answer.field_id for answer in payload.answers}
                }
            )
            claim_types = sorted(
                {requested_fields[answer.field_id].claim_type.value for answer in payload.answers}
            )
            routing = SourceRoutingModel(
                source_routing_id=f"routing_{uuid4().hex[:16]}",
                project_id=project_id,
                source_asset_id=source_asset_id,
                status="confirmed",
                method="manual",
                suggestions_json=[],
                confirmed_routes_json=routes,
                confirmed_claim_types_json=claim_types,
                rule_signals_json=["source_recovery_user_confirmation"],
                input_hash=content_hash,
                model_id=None,
                model_call_id=None,
                analyzed_at=now,
                decided_at=now,
                decided_by=payload.actor,
                decision_reason="用户在资料恢复表单中确认并提交。",
                updated_at=now,
            )

            session.add(job)
            await session.flush()
            session.add(asset)
            await session.flush()
            session.add(artifact)
            await session.flush()
            session.add(routing)
            await session.flush()

            evidence_ids: list[str] = []
            authority_score = self._authority_score(payload.authorization_basis)
            for ordinal, (answer, row) in enumerate(zip(payload.answers, answer_rows, strict=True)):
                field = requested_fields[answer.field_id]
                excerpt = str(row["excerpt"])
                fragment = SourceFragmentModel(
                    source_fragment_id=f"fragment_{uuid4().hex[:16]}",
                    parsed_artifact_id=parsed_artifact_id,
                    project_id=project_id,
                    source_asset_id=source_asset_id,
                    ordinal=ordinal,
                    locator_json={
                        "kind": "json",
                        "json_pointer": f"/answers/{ordinal}/value",
                        "char_start": 0,
                        "char_end": len(excerpt),
                    },
                    original_excerpt=excerpt,
                    excerpt_hash=build_content_hash(excerpt),
                    verification_status="verified",
                    created_at=now,
                )
                session.add(fragment)
                await session.flush()
                existing_evidence = await session.scalar(
                    select(EvidenceModel).where(
                        EvidenceModel.project_id == project_id,
                        EvidenceModel.content_hash == fragment.excerpt_hash,
                    )
                )
                if existing_evidence is not None:
                    evidence_ids.append(existing_evidence.evidence_id)
                    continue
                evidence_id = f"ev_{uuid4().hex[:16]}"
                evidence = EvidenceModel(
                    evidence_id=evidence_id,
                    project_id=project_id,
                    collection_job_id=collection_job_id,
                    source_url=None,
                    normalized_source_url=None,
                    source_domain=None,
                    source_asset_id=source_asset_id,
                    source_fragment_id=fragment.source_fragment_id,
                    source_locator_json=fragment.locator_json,
                    source_type="user_declaration",
                    title=f"{display_name}｜{field.label}",
                    original_excerpt=excerpt,
                    claim_type=field.claim_type,
                    product=self._product_label(field.product) if field.product else None,
                    region=field.region,
                    user_segment=None,
                    published_at=None,
                    collected_at=now,
                    status=EvidenceStatus.PARTIALLY_VERIFIED,
                    content_hash=fragment.excerpt_hash,
                    confidence=0.7,
                    authority_score=authority_score,
                    recency_score=1.0,
                    diversity_score=0.2,
                )
                session.add(evidence)
                await session.flush()
                evidence_ids.append(evidence_id)

            submission = SourceRecoverySubmissionModel(
                submission_id=submission_id,
                source_recovery_id=source_recovery_id,
                project_id=project_id,
                request_id=payload.request_id,
                submission_kind=SourceRecoverySubmissionKind.DIRECT_ANSWER,
                source_asset_id=source_asset_id,
                field_ids_json=[answer.field_id for answer in payload.answers],
                evidence_ids_json=evidence_ids,
                answer_count=len(payload.answers),
                actor=payload.actor,
                created_at=now,
            )
            event = self._event(
                project_id,
                "source_recovery_submission_recorded",
                {
                    "source_recovery_id": source_recovery_id,
                    "submission_id": submission_id,
                    "source_asset_id": source_asset_id,
                    "evidence_ids": evidence_ids,
                    "source_type": "user_declaration",
                },
                now,
            )
            try:
                await repository.add_submission(submission)
                await ProjectRepository(session).add_event(event)
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise

        assessment = await self.requirements.get(project_id)
        await self._update_after_assessment(project_id, source_recovery_id, assessment)
        await self.event_broker.notify(project_id)
        return await self.get(project_id, source_recovery_id)

    async def submit_evidence(
        self,
        project_id: str,
        source_recovery_id: str,
        payload: SourceRecoveryEvidenceSubmissionCreate,
    ) -> SourceRecovery:
        """关联已完成处理的 Evidence；不把原始文件或 URL 直接当成事实。"""

        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            recovery = await self._require_recovery(repository, project_id, source_recovery_id)
            replay = await repository.get_submission_by_request(
                source_recovery_id, payload.request_id
            )
            if replay is not None:
                return self._to_recovery(recovery)
            self._require_open(recovery)
            asset = await repository.get_source_asset(project_id, payload.source_asset_id)
            if asset is None:
                raise self._not_found(
                    "SOURCE_RECOVERY_EVIDENCE_ASSET_NOT_FOUND",
                    "没有找到已完成处理的补研资料。",
                )
            requested_fields = {
                item.field_id: item
                for item in map(
                    SourceRecoveryRequestedField.model_validate,
                    recovery.requested_fields_json,
                )
            }
            bound_field_ids = {binding.field_id for binding in payload.bindings}
            unknown_fields = sorted(bound_field_ids - set(requested_fields))
            if unknown_fields:
                raise AppError(
                    code="SOURCE_RECOVERY_FIELD_UNKNOWN",
                    message="Evidence 绑定包含不属于当前恢复任务的字段。",
                    status_code=422,
                    details={"field_ids": unknown_fields},
                )
            evidence_ids = list(
                dict.fromkeys(
                    evidence_id
                    for binding in payload.bindings
                    for evidence_id in binding.evidence_ids
                )
            )
            evidence_models = await EvidenceRepository(session).get_evidence_by_ids(
                set(evidence_ids)
            )
            evidence_by_id = {model.evidence_id: model for model in evidence_models}
            missing_evidence_ids = sorted(set(evidence_ids) - set(evidence_by_id))
            if missing_evidence_ids:
                raise AppError(
                    code="SOURCE_RECOVERY_EVIDENCE_NOT_FOUND",
                    message="部分 Evidence 不存在。",
                    status_code=422,
                    details={"evidence_ids": missing_evidence_ids},
                )
            invalid_scope_ids = sorted(
                model.evidence_id
                for model in evidence_models
                if model.project_id != project_id
                or model.source_asset_id != payload.source_asset_id
            )
            if invalid_scope_ids:
                raise AppError(
                    code="SOURCE_RECOVERY_EVIDENCE_SCOPE_INVALID",
                    message="Evidence 必须来自当前项目中指定的已处理资料。",
                    status_code=422,
                    details={"evidence_ids": invalid_scope_ids},
                )
            ineligible_ids = sorted(
                model.evidence_id
                for model in evidence_models
                if model.status
                not in {EvidenceStatus.VERIFIED.value, EvidenceStatus.PARTIALLY_VERIFIED.value}
            )
            if ineligible_ids:
                raise AppError(
                    code="SOURCE_RECOVERY_EVIDENCE_INELIGIBLE",
                    message="只有 verified 或 partially_verified Evidence 可用于补研。",
                    status_code=422,
                    details={"evidence_ids": ineligible_ids},
                )
            mismatches: list[dict[str, str]] = []
            for binding in payload.bindings:
                field = requested_fields[binding.field_id]
                for evidence_id in binding.evidence_ids:
                    actual = EvidenceClaimType(evidence_by_id[evidence_id].claim_type)
                    if not self._claim_type_compatible(field.claim_type, actual):
                        mismatches.append(
                            {
                                "field_id": field.field_id,
                                "evidence_id": evidence_id,
                                "expected": field.claim_type.value,
                                "actual": actual.value,
                            }
                        )
            if mismatches:
                raise AppError(
                    code="SOURCE_RECOVERY_EVIDENCE_TYPE_MISMATCH",
                    message="Evidence 类型与所绑定的缺口字段不匹配。",
                    status_code=422,
                    details={"bindings": mismatches},
                )

            now = datetime.now(UTC)
            submission = SourceRecoverySubmissionModel(
                submission_id=f"submission_{uuid4().hex[:12]}",
                source_recovery_id=source_recovery_id,
                project_id=project_id,
                request_id=payload.request_id,
                submission_kind=SourceRecoverySubmissionKind.EXISTING_EVIDENCE,
                source_asset_id=payload.source_asset_id,
                field_ids_json=sorted(bound_field_ids),
                evidence_ids_json=evidence_ids,
                answer_count=len(payload.bindings),
                actor=payload.actor,
                created_at=now,
            )
            event = self._event(
                project_id,
                "source_recovery_evidence_linked",
                {
                    "source_recovery_id": source_recovery_id,
                    "submission_id": submission.submission_id,
                    "source_asset_id": payload.source_asset_id,
                    "evidence_ids": evidence_ids,
                    "field_ids": sorted(bound_field_ids),
                    "actor": payload.actor,
                    "reason": payload.reason,
                },
                now,
            )
            try:
                await repository.add_submission(submission)
                await ProjectRepository(session).add_event(event)
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise

        assessment = await self.requirements.get(project_id)
        await self._update_after_assessment(project_id, source_recovery_id, assessment)
        await self.event_broker.notify(project_id)
        return await self.get(project_id, source_recovery_id)

    async def decide(
        self,
        project_id: str,
        source_recovery_id: str,
        payload: SourceRecoveryDecisionCreate,
    ) -> SourceRecovery:
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            recovery = await self._require_recovery(repository, project_id, source_recovery_id)
            self._require_open(recovery)
            now = datetime.now(UTC)
            recovery.status = (
                SourceRecoveryStatus.PROCEEDING_WITH_GAPS
                if payload.action is SourceRecoveryDecisionAction.PROCEED_WITH_GAPS
                else SourceRecoveryStatus.CANCELLED
            )
            recovery.decision_actor = payload.actor
            recovery.decision_reason = payload.reason
            recovery.updated_at = now
            recovery.resolved_at = now
            event = self._event(
                project_id,
                "source_recovery_decided",
                {
                    "source_recovery_id": source_recovery_id,
                    "action": payload.action,
                    "actor": payload.actor,
                    "affected_task_ids": recovery.affected_task_ids_json,
                    "affected_agent_types": recovery.affected_agent_types_json,
                },
                now,
            )
            try:
                await ProjectRepository(session).add_event(event)
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise
        await self.event_broker.notify(project_id)
        return await self.get(project_id, source_recovery_id)

    async def _update_after_assessment(
        self,
        project_id: str,
        source_recovery_id: str,
        assessment: SourceRequirementAssessment,
    ) -> None:
        async with self.database.session() as session:
            repository = SourceRecoveryRepository(session)
            recovery = await self._require_recovery(repository, project_id, source_recovery_id)
            status_by_id = {item.requirement_id: item.status for item in assessment.requirements}
            requested_fields = [
                SourceRecoveryRequestedField.model_validate(item)
                for item in recovery.requested_fields_json
            ]
            submitted_field_ids = {
                field_id
                for submission in recovery.submissions
                for field_id in submission.field_ids_json
            }
            synthetic_field_by_requirement = {
                field.requirement_id: field.field_id
                for field in requested_fields
                if field.requirement_id.startswith(
                    (
                        "requirement_source_gap_",
                        "requirement_product_gap_",
                        "requirement_agent_gap_",
                    )
                )
            }
            resolved = all(
                (
                    synthetic_field_by_requirement[requirement_id] in submitted_field_ids
                    if requirement_id in synthetic_field_by_requirement
                    else status_by_id.get(requirement_id) is SourceRequirementStatus.SATISFIED
                )
                for requirement_id in recovery.requirement_ids_json
            )
            now = datetime.now(UTC)
            recovery.current_assessment_json = assessment.model_dump(mode="json")
            recovery.status = (
                SourceRecoveryStatus.RESOLVED
                if resolved
                else SourceRecoveryStatus.NEEDS_MORE_INFORMATION
            )
            recovery.updated_at = now
            recovery.resolved_at = now if resolved else None
            event = self._event(
                project_id,
                "source_recovery_reassessed",
                {
                    "source_recovery_id": source_recovery_id,
                    "status": recovery.status,
                    "readiness": assessment.status,
                    "assessment_input_hash": assessment.input_hash,
                    "affected_task_ids": recovery.affected_task_ids_json,
                    "affected_agent_types": recovery.affected_agent_types_json,
                },
                now,
            )
            try:
                await ProjectRepository(session).add_event(event)
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise

    @staticmethod
    async def _require_project(repository: SourceRecoveryRepository, project_id: str) -> None:
        if await repository.get_project(project_id) is None:
            raise AppError(
                code="PROJECT_NOT_FOUND",
                message="研究项目不存在。",
                status_code=404,
                details={"project_id": project_id},
            )

    async def _require_recovery(
        self,
        repository: SourceRecoveryRepository,
        project_id: str,
        source_recovery_id: str,
    ) -> SourceRecoveryModel:
        await self._require_project(repository, project_id)
        recovery = await repository.get(project_id, source_recovery_id)
        if recovery is None:
            raise self._not_found("SOURCE_RECOVERY_NOT_FOUND", "没有找到指定的资料恢复任务。")
        return recovery

    @staticmethod
    def _require_open(recovery: SourceRecoveryModel) -> None:
        if SourceRecoveryStatus(recovery.status) in _TERMINAL_RECOVERY_STATUSES:
            raise AppError(
                code="SOURCE_RECOVERY_ALREADY_CLOSED",
                message="该资料恢复任务已经结束，不能重复提交或决策。",
                status_code=409,
                details={"status": recovery.status},
            )

    @staticmethod
    def _select_requirements(
        assessment: SourceRequirementAssessment,
        source_asset_id: str,
        requested_ids: list[str],
    ) -> list[SourceRequirementItem]:
        material = [
            item
            for item in assessment.requirements
            if item.dimension is not None and item.status is not SourceRequirementStatus.SATISFIED
        ]
        by_id = {item.requirement_id: item for item in material}
        if requested_ids:
            missing = sorted(set(requested_ids) - set(by_id))
            if missing:
                raise AppError(
                    code="SOURCE_RECOVERY_REQUIREMENT_INVALID",
                    message="指定的资料要求不存在、已满足或不能通过内容补充解决。",
                    status_code=422,
                    details={"requirement_ids": missing},
                )
            return [by_id[item_id] for item_id in requested_ids]
        detected = [item for item in material if source_asset_id in item.detected_source_asset_ids]
        if detected:
            return detected
        return []

    @classmethod
    def _build_agent_gap_fields(
        cls,
        gaps: list[AgentArtifactGap],
    ) -> tuple[list[SourceRecoveryRequestedField], set[str]]:
        fields: list[SourceRecoveryRequestedField] = []
        affected_agents: set[str] = set()
        for gap in gaps:
            evidence_types = (
                gap.required_evidence_types
                or gap.recommended_source_types[:1]
                or ["supporting_fact"]
            )
            for evidence_type in evidence_types:
                claim_type, route, agents, label = cls._agent_gap_evidence_rule(evidence_type, gap)
                affected_agents.update(agent.value for agent in agents)
                identity = f"{gap.artifact_id}:{gap.gap_id}:{evidence_type}"
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
                question = f"{gap.question} 请补充{label}，并说明适用范围、限制和信息来源。"
                fields.append(
                    SourceRecoveryRequestedField(
                        field_id=f"field_{digest}",
                        requirement_id=f"requirement_agent_gap_{digest}",
                        field_key=(
                            evidence_type if len(evidence_type) <= 80 else f"evidence_{digest}"
                        ),
                        label=f"补充{label}",
                        question=question[:500],
                        required=True,
                        claim_type=claim_type,
                        evidence_type_hint=evidence_type,
                        affected_candidate_ids=gap.affected_candidate_ids[:5],
                        product=None,
                        region=None,
                        route=route,
                    )
                )
        return fields, affected_agents

    @staticmethod
    def _agent_gap_evidence_rule(
        evidence_type: str,
        gap: AgentArtifactGap,
    ) -> tuple[
        EvidenceClaimType,
        SourceRouteTarget,
        tuple[ResearchAgentType, ...],
        str,
    ]:
        normalized = " ".join(
            filter(
                None,
                (
                    evidence_type,
                    gap.dimension or "",
                    gap.agent_type.value,
                ),
            )
        ).casefold()
        if any(
            token in normalized
            for token in ("user", "pain", "opinion", "review", "interview", "voc")
        ):
            return (
                EvidenceClaimType.USER_OPINION,
                SourceRouteTarget.USER_RESEARCH,
                (ResearchAgentType.USER_RESEARCH,),
                "用户事件、痛点或反馈事实",
            )
        if "price" in normalized or "pricing" in normalized:
            return (
                EvidenceClaimType.PRICE_OBSERVATION,
                SourceRouteTarget.PRICE_CHANNEL,
                (ResearchAgentType.COMPETITOR_RESEARCH,),
                "带地区、币种和观察时间的价格事实",
            )
        if "channel" in normalized or "availability" in normalized:
            return (
                EvidenceClaimType.CHANNEL_AVAILABILITY,
                SourceRouteTarget.PRICE_CHANNEL,
                (ResearchAgentType.COMPETITOR_RESEARCH,),
                "渠道和可售状态事实",
            )
        if "competitor" in normalized or "official" in normalized:
            return (
                EvidenceClaimType.LIMITATION,
                SourceRouteTarget.OFFICIAL_PRODUCT,
                (ResearchAgentType.COMPETITOR_RESEARCH,),
                "竞品能力、限制或差异事实",
            )
        if any(token in normalized for token in ("context", "signal", "technical", "api", "data")):
            return (
                EvidenceClaimType.TECHNICAL_FACT,
                SourceRouteTarget.TECHNICAL_DOCUMENT,
                (ResearchAgentType.PRODUCT_TECHNICAL,),
                "数据接口、信号可用性和授权事实",
            )
        if "market" in normalized or "commercial" in normalized:
            return (
                EvidenceClaimType.MARKET_FACT,
                SourceRouteTarget.COMMERCIAL_DATA,
                (ResearchAgentType.COMMERCIAL_EVALUATION,),
                "市场规模、成本、收入或渠道事实",
            )
        return (
            EvidenceClaimType.FACT,
            SourceRouteTarget.ENTERPRISE_INTERNAL,
            (
                ResearchAgentType.USER_RESEARCH,
                ResearchAgentType.COMPETITOR_RESEARCH,
            ),
            "能够支持该机会判断的具体事实",
        )

    @classmethod
    def _build_requested_fields(
        cls,
        requirements: list[SourceRequirementItem],
        region: str,
    ) -> list[SourceRecoveryRequestedField]:
        fields: list[SourceRecoveryRequestedField] = []
        for requirement in requirements:
            if requirement.dimension is None:
                continue
            accepted = set(requirement.accepted_claim_types)
            preferred_route = SourceRouteTarget(requirement.dimension.value)
            route = (
                preferred_route
                if preferred_route in requirement.accepted_routes
                else (requirement.accepted_routes[0] if requirement.accepted_routes else None)
            )
            candidates = [
                (claim_type, required)
                for claim_type, required in _DIMENSION_FIELDS[requirement.dimension]
                if claim_type in accepted
            ]
            if not candidates and accepted:
                candidates = [(sorted(accepted, key=lambda item: item.value)[0], True)]
            product_label = cls._product_label(requirement.product)
            for claim_type, required in candidates:
                label, prompt = _FIELD_COPY.get(
                    claim_type,
                    (claim_type.value, "请填写与当前资料缺口相关的具体内容。"),
                )
                identity = f"{requirement.requirement_id}:{claim_type.value}"
                field_id = f"field_{hashlib.sha256(identity.encode()).hexdigest()[:16]}"
                fields.append(
                    SourceRecoveryRequestedField(
                        field_id=field_id,
                        requirement_id=requirement.requirement_id,
                        field_key=claim_type.value,
                        label=label,
                        question=f"{product_label}：{prompt}" if product_label else prompt,
                        required=required,
                        claim_type=claim_type,
                        product=requirement.product,
                        region=(
                            region
                            if requirement.dimension is CompetitorResearchDimension.PRICE_CHANNEL
                            else None
                        ),
                        route=route,
                    )
                )
        return fields

    @staticmethod
    def _affected_agent_types(fields: list[SourceRecoveryRequestedField]) -> list[str]:
        agents = {
            agent.value
            for field in fields
            if field.route is not None
            for agent in _AGENT_BY_ROUTE[field.route]
        }
        return sorted(agents)

    @staticmethod
    def _build_generic_fields(
        source_asset_id: str,
        questions: list[str],
        region: str,
        purpose: str,
    ) -> list[SourceRecoveryRequestedField]:
        prompts = questions or [
            (
                "请填写这份资料原本要支持的关键信息，包含研究对象、具体事实、"
                f"适用范围和必要限制。资料用途：{purpose}"
            )
        ]
        fields: list[SourceRecoveryRequestedField] = []
        for ordinal, question in enumerate(prompts):
            identity = f"{source_asset_id}:{ordinal}:{question}"
            digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
            fields.append(
                SourceRecoveryRequestedField(
                    field_id=f"field_{digest}",
                    requirement_id=f"requirement_source_gap_{digest}",
                    field_key="fact",
                    label=f"缺失信息 {ordinal + 1}",
                    question=question,
                    required=True,
                    claim_type=EvidenceClaimType.FACT,
                    product=None,
                    region=region or None,
                    route=SourceRouteTarget.ENTERPRISE_INTERNAL,
                )
            )
        return fields

    @staticmethod
    def _classify_reason(
        error_code: str | None,
        status: str,
    ) -> tuple[SourceRecoveryReasonCode, str]:
        code = (error_code or "").upper()
        if "ROBOTS" in code:
            return (
                SourceRecoveryReasonCode.ROBOTS_BLOCKED,
                "网站禁止自动访问，需要用户补充缺失内容。",
            )
        if "AUTHENTICATION" in code:
            return (
                SourceRecoveryReasonCode.AUTHENTICATION_REQUIRED,
                "网站需要登录或授权，系统不能代替用户访问。",
            )
        if "ACCESS_RESTRICTED" in code or "FORBIDDEN" in code:
            return SourceRecoveryReasonCode.ACCESS_DENIED, "网站拒绝访问，需要用户补充缺失内容。"
        if "RETRYABLE_STATUS" in code or "RATE" in code:
            return SourceRecoveryReasonCode.RATE_LIMITED, "网站暂时限制访问，当前资料无法完成。"
        if "CONNECTOR_NOT_CONFIGURED" in code or "CONNECTOR_UNAVAILABLE" in code:
            return (
                SourceRecoveryReasonCode.CONNECTOR_UNAVAILABLE,
                "当前环境没有可用的解析连接器，需要用户补充文字内容。",
            )
        if "UNSUPPORTED" in code or "STREAM_MISSING" in code:
            return (
                SourceRecoveryReasonCode.UNSUPPORTED_MEDIA,
                "当前资料格式或媒体内容无法理解，需要用户补充文字内容。",
            )
        if "EMPTY" in code:
            return SourceRecoveryReasonCode.EMPTY_CONTENT, "资料没有产生可用文本或片段。"
        if status in {"failed", "blocked", "cancelled"}:
            return SourceRecoveryReasonCode.PROCESSING_FAILED, "资料处理未完成，需要用户补充内容。"
        return (
            SourceRecoveryReasonCode.INSUFFICIENT_INFORMATION,
            "资料虽然完成处理，但没有覆盖当前研究需要的关键信息。",
        )

    @staticmethod
    def _answer_row(
        answer: SourceRecoveryAnswer,
        field: SourceRecoveryRequestedField,
    ) -> dict[str, object]:
        value = answer.value
        source_note = answer.source_note
        product_label = SourceRecoveryService._product_label(field.product)
        prefix = f"{product_label}｜" if product_label else ""
        excerpt = f"{prefix}{field.label}：{value}"
        if source_note:
            excerpt = f"{excerpt}\n用户来源说明：{source_note}"
        return {
            "field_id": field.field_id,
            "field_key": field.field_key,
            "value": value,
            "source_note": source_note,
            "excerpt": excerpt,
        }

    @staticmethod
    def _authority_score(basis: SourceAuthorizationBasis) -> float:
        if basis is SourceAuthorizationBasis.ENTERPRISE_AUTHORIZED:
            return 0.65
        if basis is SourceAuthorizationBasis.USER_OWNED:
            return 0.45
        return 0.35

    @staticmethod
    def _claim_type_compatible(
        expected: EvidenceClaimType,
        actual: EvidenceClaimType,
    ) -> bool:
        if expected is EvidenceClaimType.FACT:
            return actual is not EvidenceClaimType.AGENT_INFERENCE
        compatible: dict[EvidenceClaimType, set[EvidenceClaimType]] = {
            EvidenceClaimType.LIMITATION: {
                EvidenceClaimType.LIMITATION,
                EvidenceClaimType.CAPABILITY,
                EvidenceClaimType.SPECIFICATION,
                EvidenceClaimType.VENDOR_CLAIM,
            },
            EvidenceClaimType.TECHNICAL_FACT: {
                EvidenceClaimType.TECHNICAL_FACT,
                EvidenceClaimType.SPECIFICATION,
                EvidenceClaimType.CAPABILITY,
            },
            EvidenceClaimType.MARKET_FACT: {
                EvidenceClaimType.MARKET_FACT,
                EvidenceClaimType.PRICE_OBSERVATION,
                EvidenceClaimType.CHANNEL_AVAILABILITY,
            },
        }
        return actual in compatible.get(expected, {expected})

    @staticmethod
    def _product_label(product: object | None) -> str:
        if product is None:
            return ""
        return " ".join(
            filter(
                None,
                (
                    getattr(product, "brand", None),
                    getattr(product, "model", None),
                    getattr(product, "variant", None),
                ),
            )
        )

    @classmethod
    def _to_recovery(cls, model: SourceRecoveryModel) -> SourceRecovery:
        status = SourceRecoveryStatus(model.status)
        if status is SourceRecoveryStatus.RESOLVED:
            directive = SourceRecoveryResumeDirective(
                ready=True,
                mode=SourceRecoveryResumeMode.TARGETED_RETRY,
                affected_task_ids=model.affected_task_ids_json,
                affected_agent_types=model.affected_agent_types_json,
                reason="资料缺口已复评通过，只需恢复受影响的研究任务。",
            )
        elif status is SourceRecoveryStatus.PROCEEDING_WITH_GAPS:
            directive = SourceRecoveryResumeDirective(
                ready=True,
                mode=SourceRecoveryResumeMode.PROCEED_WITH_GAPS,
                affected_task_ids=model.affected_task_ids_json,
                affected_agent_types=model.affected_agent_types_json,
                reason="用户已明确同意保留未知项并继续，只能输出带缺口结论。",
            )
        else:
            directive = SourceRecoveryResumeDirective(
                ready=False,
                mode=SourceRecoveryResumeMode.NONE,
                affected_task_ids=model.affected_task_ids_json,
                affected_agent_types=model.affected_agent_types_json,
                reason=(
                    "恢复任务已取消。"
                    if status is SourceRecoveryStatus.CANCELLED
                    else "仍在等待用户补充或资料复评尚未通过。"
                ),
            )
        submissions = sorted(model.submissions, key=lambda item: item.created_at)
        return SourceRecovery(
            source_recovery_id=model.source_recovery_id,
            project_id=model.project_id,
            status=status,
            reason_code=SourceRecoveryReasonCode(model.reason_code),
            reason_message=model.reason_message,
            failed_source_asset_id=model.failed_source_asset_id,
            failed_collection_job_id=model.failed_collection_job_id,
            source_artifact_id=model.source_artifact_id,
            source_gap_ids=list(model.source_gap_ids_json),
            requirement_ids=list(model.requirement_ids_json),
            requested_fields=[
                SourceRecoveryRequestedField.model_validate(item)
                for item in model.requested_fields_json
            ],
            affected_task_ids=list(model.affected_task_ids_json),
            affected_agent_types=list(model.affected_agent_types_json),
            assessment_before=SourceRequirementAssessment.model_validate(
                model.assessment_before_json
            ),
            current_assessment=SourceRequirementAssessment.model_validate(
                model.current_assessment_json
            ),
            submissions=[
                SourceRecoverySubmission(
                    submission_id=item.submission_id,
                    request_id=item.request_id,
                    submission_kind=SourceRecoverySubmissionKind(item.submission_kind),
                    source_asset_id=item.source_asset_id,
                    field_ids=list(item.field_ids_json),
                    evidence_ids=list(item.evidence_ids_json),
                    answer_count=item.answer_count,
                    actor=item.actor,
                    created_at=item.created_at,
                )
                for item in submissions
            ],
            resume_directive=directive,
            requested_by=model.requested_by,
            request_reason=model.request_reason,
            decision_actor=model.decision_actor,
            decision_reason=model.decision_reason,
            created_at=model.created_at,
            updated_at=model.updated_at,
            resolved_at=model.resolved_at,
        )

    def _event(
        self,
        project_id: str,
        event_type: str,
        data: dict[str, object],
        now: datetime,
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type=event_type,
            data_json=data,
            trace_id=self.trace_id,
            created_at=now,
        )

    @staticmethod
    def _not_found(code: str, message: str) -> AppError:
        return AppError(code=code, message=message, status_code=404)
