"""把已验证 Source Fragment 通过可审计人工 Gate 晋级到 Evidence Lake。"""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events import ProjectEventBroker
from app.application.evidence import SourceEvidencePromotionService
from app.application.source_requirements import SourceRequirementService
from app.core.errors import AppError
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.fragment_evidence_repository import (
    FragmentEvidenceRepository,
)
from app.infrastructure.database.models import (
    CollectionJobModel,
    CompetitorMaterialSelectionModel,
    CompetitorSourceOnboardingItemModel,
    EvidenceModel,
    FragmentEvidenceBatchItemModel,
    FragmentEvidenceBatchModel,
    ProjectEventModel,
    ProjectModel,
    SourceAssetModel,
    SourceFragmentModel,
    SourceRoutingModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.schemas.evidence import (
    EvidenceClaimType,
    EvidenceFromSourceFragmentIngest,
    EvidenceIngestResult,
)
from app.schemas.fragment_evidence import (
    FragmentEvidenceBatch,
    FragmentEvidenceBatchCreate,
    FragmentEvidenceBatchItem,
    FragmentEvidenceBatchPage,
    FragmentEvidenceBatchStatus,
    FragmentEvidenceDecision,
    FragmentEvidenceDecisionAction,
    FragmentEvidenceDecisionCreate,
    FragmentEvidenceDecisionResult,
    FragmentEvidenceEligibility,
    FragmentEvidencePromotionStatus,
    FragmentEvidenceQualityPrior,
)
from app.schemas.project import ResearchBrief
from app.schemas.source import SourceAssetStatus
from app.schemas.source_processing import (
    CollectionJobStatus,
    SourceFragment,
    SourceFragmentVerificationStatus,
    SourceLocatorKind,
)
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    ProductReference,
    ProductRole,
)
from app.schemas.source_routing import (
    ROUTE_ALLOWED_CLAIM_TYPES,
    SourceRouteTarget,
    SourceRoutingStatus,
)

POLICY_VERSION = "fragment-evidence-v1"
MAX_BATCH_FRAGMENTS = 200
_PRODUCT_ROUTES = {
    SourceRouteTarget.OFFICIAL_PRODUCT,
    SourceRouteTarget.PRICE_CHANNEL,
    SourceRouteTarget.USER_REVIEW,
}
_SUGGESTED_CLAIM_TYPES = {
    CompetitorResearchDimension.OFFICIAL_PRODUCT: EvidenceClaimType.VENDOR_CLAIM,
    CompetitorResearchDimension.PRICE_CHANNEL: EvidenceClaimType.PRICE_OBSERVATION,
    CompetitorResearchDimension.USER_REVIEW: EvidenceClaimType.USER_OPINION,
}
_ROUTE_AUTHORITY = {
    SourceRouteTarget.OFFICIAL_PRODUCT: 0.85,
    SourceRouteTarget.PRICE_CHANNEL: 0.70,
    SourceRouteTarget.USER_REVIEW: 0.55,
    SourceRouteTarget.USER_RESEARCH: 0.65,
    SourceRouteTarget.MARKET_RESEARCH: 0.70,
    SourceRouteTarget.TECHNICAL_DOCUMENT: 0.80,
    SourceRouteTarget.COMMERCIAL_DATA: 0.70,
    SourceRouteTarget.ENTERPRISE_INTERNAL: 0.85,
    SourceRouteTarget.MEDIA_REVIEW: 0.55,
}


@dataclass(frozen=True)
class _Snapshot:
    project: ProjectModel
    assets: tuple[SourceAssetModel, ...]
    fragments: tuple[SourceFragmentModel, ...]
    fragment_overflow: bool
    routings: tuple[SourceRoutingModel, ...]
    material_lineage: tuple[CompetitorMaterialSelectionModel, ...]
    onboarding_lineage: tuple[CompetitorSourceOnboardingItemModel, ...]
    evidence: tuple[EvidenceModel, ...]
    jobs: tuple[CollectionJobModel, ...]
    domain_counts: dict[str, int]


class FragmentEvidencePipelineService:
    def __init__(
        self,
        database: Database,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.event_broker = event_broker
        self.trace_id = trace_id

    async def create(
        self, project_id: str, payload: FragmentEvidenceBatchCreate
    ) -> FragmentEvidenceBatch:
        snapshot = await self._load_snapshot(
            project_id,
            payload.source_asset_ids,
            payload.source_fragment_ids,
        )
        batch_id = f"fragment_batch_{uuid4().hex[:16]}"
        now = datetime.now(UTC)
        draft_rows = self._build_drafts(snapshot)
        input_hash = self._input_hash(snapshot, draft_rows)
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            batch = FragmentEvidenceBatchModel(
                fragment_evidence_batch_id=batch_id,
                project_id=project_id,
                status=FragmentEvidenceBatchStatus.PENDING_REVIEW.value,
                source_asset_ids_json=payload.source_asset_ids,
                policy_version=POLICY_VERSION,
                input_hash=input_hash,
                requested_by=payload.requested_by,
                purpose=payload.purpose,
                fragment_evidence_decision_id=None,
                decision_action=None,
                selected_item_ids_json=[],
                decided_by=None,
                decision_reason=None,
                decided_at=None,
                created_at=now,
                updated_at=now,
            )
            await repository.add(batch)
            for row in draft_rows:
                row.fragment_evidence_batch_id = batch_id
                await repository.add(row)
            await self._event(
                session,
                project_id,
                "fragment_evidence_batch_created",
                {
                    "fragment_evidence_batch_id": batch_id,
                    "source_asset_count": len(payload.source_asset_ids),
                    "item_count": len(draft_rows),
                    "eligible_count": sum(
                        item.eligibility == FragmentEvidenceEligibility.ELIGIBLE.value
                        for item in draft_rows
                    ),
                },
                now,
            )
            await repository.commit()
        await self.event_broker.notify(project_id)
        return await self.get(project_id, batch_id)

    async def get(self, project_id: str, batch_id: str) -> FragmentEvidenceBatch:
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            if await repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            model = await repository.get_batch(project_id, batch_id)
        if model is None:
            raise self._batch_not_found(batch_id)
        return self._to_batch(model)

    async def list_batches(self, project_id: str) -> FragmentEvidenceBatchPage:
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            if await repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            models = await repository.list_batches(project_id)
        return FragmentEvidenceBatchPage(
            items=[self._to_batch(item) for item in models], total=len(models)
        )

    async def decide(
        self,
        project_id: str,
        batch_id: str,
        payload: FragmentEvidenceDecisionCreate,
    ) -> FragmentEvidenceDecisionResult:
        decision_created = await self._save_or_validate_decision(
            project_id, batch_id, payload
        )
        if payload.action is FragmentEvidenceDecisionAction.CONFIRM:
            current = await self.get(project_id, batch_id)
            if decision_created or current.status in {
                FragmentEvidenceBatchStatus.PROCESSING,
                FragmentEvidenceBatchStatus.PARTIAL,
            }:
                await self._process_selected(project_id, batch_id)
        return FragmentEvidenceDecisionResult(
            batch=await self.get(project_id, batch_id),
            decision_created=decision_created,
        )

    async def _save_or_validate_decision(
        self,
        project_id: str,
        batch_id: str,
        payload: FragmentEvidenceDecisionCreate,
    ) -> bool:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            batch = await repository.get_batch(project_id, batch_id)
            if batch is None:
                raise self._batch_not_found(batch_id)
            if batch.fragment_evidence_decision_id is not None:
                self._assert_idempotent(batch, payload)
                return False
            by_id = {item.fragment_evidence_item_id: item for item in batch.items}
            unsupported = sorted(
                {
                    item.fragment_evidence_item_id
                    for item in payload.selections
                    if item.fragment_evidence_item_id not in by_id
                }
            )
            if unsupported:
                raise AppError(
                    code="FRAGMENT_EVIDENCE_ITEM_NOT_FOUND",
                    message="只能选择当前 Evidence Draft 批次中的项目。",
                    status_code=422,
                    details={"unsupported_item_ids": unsupported},
                )
            for selection in payload.selections:
                item = by_id[selection.fragment_evidence_item_id]
                if item.eligibility != FragmentEvidenceEligibility.ELIGIBLE.value:
                    raise AppError(
                        code="FRAGMENT_EVIDENCE_ITEM_NOT_ELIGIBLE",
                        message="只有 eligible Evidence Draft 可以晋级。",
                        status_code=409,
                        details={
                            "fragment_evidence_item_id": item.fragment_evidence_item_id,
                            "eligibility": item.eligibility,
                        },
                    )
                if selection.claim_type.value not in item.allowed_claim_types_json:
                    raise AppError(
                        code="FRAGMENT_EVIDENCE_CLAIM_TYPE_NOT_ALLOWED",
                        message="所选 Claim 类型未通过该资料的确认路由约束。",
                        status_code=422,
                        details={
                            "fragment_evidence_item_id": item.fragment_evidence_item_id,
                            "allowed_claim_types": item.allowed_claim_types_json,
                        },
                    )
            batch.fragment_evidence_decision_id = f"fragment_decision_{uuid4().hex[:12]}"
            batch.decision_action = payload.action.value
            batch.selected_item_ids_json = [
                item.fragment_evidence_item_id for item in payload.selections
            ]
            batch.decided_by = payload.actor
            batch.decision_reason = payload.reason
            batch.decided_at = now
            batch.updated_at = now
            if payload.action is FragmentEvidenceDecisionAction.REJECT:
                batch.status = FragmentEvidenceBatchStatus.REJECTED.value
            else:
                batch.status = FragmentEvidenceBatchStatus.PROCESSING.value
                for selection in payload.selections:
                    item = by_id[selection.fragment_evidence_item_id]
                    item.selected = True
                    item.selected_claim_type = selection.claim_type.value
                    item.published_at = selection.published_at
                    item.user_segment = selection.user_segment
                    item.recency_score = self._recency_score(selection.published_at, now)
                    item.quality_reasons_json = [
                        reason
                        for reason in item.quality_reasons_json
                        if reason != "publication date is unknown"
                    ] + [
                        (
                            "recency prior derived from the reviewer-supplied publication date"
                            if selection.published_at is not None
                            else "publication date is unknown"
                        )
                    ]
                    item.promotion_status = FragmentEvidencePromotionStatus.PENDING.value
                    item.error_code = None
                    item.updated_at = now
            await self._event(
                session,
                project_id,
                "fragment_evidence_decision_saved",
                {
                    "fragment_evidence_batch_id": batch_id,
                    "fragment_evidence_decision_id": batch.fragment_evidence_decision_id,
                    "action": payload.action.value,
                    "selected_item_count": len(payload.selections),
                },
                now,
            )
            await repository.commit()
        await self.event_broker.notify(project_id)
        return True

    async def _process_selected(self, project_id: str, batch_id: str) -> None:
        batch = await self._get_model(project_id, batch_id)
        selected_ids = list(batch.selected_item_ids_json)
        for item_id in selected_ids:
            current = await self._get_item(project_id, batch_id, item_id)
            if current.promotion_status == FragmentEvidencePromotionStatus.SUCCEEDED.value:
                continue
            if current.selected_claim_type is None:
                await self._mark_failed(
                    project_id, batch_id, item_id, "FRAGMENT_EVIDENCE_DECISION_INVALID"
                )
                continue
            try:
                result = await self._promote(project_id, current)
            except AppError as exc:
                await self._mark_failed(project_id, batch_id, item_id, exc.code)
            except Exception:
                await self._mark_failed(
                    project_id, batch_id, item_id, "FRAGMENT_EVIDENCE_PROMOTION_FAILED"
                )
            else:
                await self._mark_succeeded(
                    project_id, batch_id, item_id, result.evidence.evidence_id
                )
        await self._finish_batch(project_id, batch_id)

    async def _promote(
        self, project_id: str, item: FragmentEvidenceBatchItemModel
    ) -> EvidenceIngestResult:
        product = (
            self._product_label(ProductReference.model_validate(item.product_json))
            if item.product_json
            else None
        )
        async with self.database.session() as session:
            service = SourceEvidencePromotionService(
                SourceAssetRepository(session),
                EvidenceRepository(session),
                ProjectRepository(session),
                self.trace_id,
                self.event_broker,
            )
            selected_claim_type = item.selected_claim_type
            if selected_claim_type is None:
                raise AppError(
                    code="FRAGMENT_EVIDENCE_DECISION_INVALID",
                    message="Evidence Draft 缺少已确认 Claim 类型。",
                    status_code=409,
                )
            return await service.promote(
                project_id,
                EvidenceFromSourceFragmentIngest(
                    source_fragment_id=item.source_fragment_id,
                    claim_type=EvidenceClaimType(selected_claim_type),
                    product=product,
                    region=item.region,
                    user_segment=item.user_segment,
                    published_at=item.published_at,
                    confidence=item.confidence,
                    authority_score=item.authority_score,
                    recency_score=item.recency_score,
                    diversity_score=item.diversity_score,
                ),
                expected_source_asset_id=item.source_asset_id,
            )

    async def _mark_succeeded(
        self, project_id: str, batch_id: str, item_id: str, evidence_id: str
    ) -> None:
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            batch = await repository.get_batch(project_id, batch_id)
            if batch is None:
                raise self._batch_not_found(batch_id)
            item = self._item_by_id(batch, item_id)
            item.promotion_status = FragmentEvidencePromotionStatus.SUCCEEDED.value
            item.evidence_id = evidence_id
            item.error_code = None
            item.updated_at = datetime.now(UTC)
            await repository.commit()

    async def _mark_failed(
        self, project_id: str, batch_id: str, item_id: str, error_code: str
    ) -> None:
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            batch = await repository.get_batch(project_id, batch_id)
            if batch is None:
                raise self._batch_not_found(batch_id)
            item = self._item_by_id(batch, item_id)
            item.promotion_status = FragmentEvidencePromotionStatus.FAILED.value
            item.error_code = error_code[:80]
            item.updated_at = datetime.now(UTC)
            await repository.commit()

    async def _finish_batch(self, project_id: str, batch_id: str) -> None:
        now = datetime.now(UTC)
        requirement_status: str | None = None
        requirement_input_hash: str | None = None
        requirement_error: str | None = None
        try:
            assessment = await SourceRequirementService(
                self.database, self.event_broker, self.trace_id
            ).get(project_id)
            requirement_status = assessment.status.value
            requirement_input_hash = assessment.input_hash
        except AppError as exc:
            requirement_error = exc.code
        except Exception:
            requirement_error = "SOURCE_REQUIREMENT_REEVALUATION_FAILED"
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            batch = await repository.get_batch(project_id, batch_id)
            if batch is None:
                raise self._batch_not_found(batch_id)
            selected = [item for item in batch.items if item.selected]
            failed_count = sum(
                item.promotion_status == FragmentEvidencePromotionStatus.FAILED.value
                for item in selected
            )
            succeeded_count = sum(
                item.promotion_status == FragmentEvidencePromotionStatus.SUCCEEDED.value
                for item in selected
            )
            batch.status = (
                FragmentEvidenceBatchStatus.COMPLETED.value
                if selected and failed_count == 0 and succeeded_count == len(selected)
                else FragmentEvidenceBatchStatus.PARTIAL.value
            )
            batch.updated_at = now
            await self._event(
                session,
                project_id,
                "fragment_evidence_batch_completed",
                {
                    "fragment_evidence_batch_id": batch_id,
                    "selected_count": len(selected),
                    "promoted_count": succeeded_count,
                    "failed_count": failed_count,
                    "status": batch.status,
                    "source_requirements_status": requirement_status,
                    "source_requirements_input_hash": requirement_input_hash,
                    "source_requirements_error": requirement_error,
                },
                now,
            )
            await repository.commit()
        await self.event_broker.notify(project_id)

    async def _load_snapshot(
        self,
        project_id: str,
        source_asset_ids: list[str],
        source_fragment_ids: list[str],
    ) -> _Snapshot:
        async with self.database.session() as session:
            repository = FragmentEvidenceRepository(session)
            project = await repository.get_project(project_id)
            if project is None:
                raise self._project_not_found(project_id)
            assets = await repository.list_assets(project_id, source_asset_ids)
            found_ids = {item.source_asset_id for item in assets}
            missing_ids = sorted(set(source_asset_ids) - found_ids)
            if missing_ids:
                raise AppError(
                    code="SOURCE_ASSET_NOT_FOUND",
                    message="部分资料资产不存在或不属于当前项目。",
                    status_code=404,
                    details={"source_asset_ids": missing_ids},
                )
            fragments = await repository.list_fragments(
                project_id,
                source_asset_ids,
                source_fragment_ids or None,
            )
            if source_fragment_ids:
                found_fragment_ids = {item.source_fragment_id for item in fragments}
                missing_fragment_ids = sorted(
                    set(source_fragment_ids) - found_fragment_ids
                )
                if missing_fragment_ids:
                    raise AppError(
                        code="SOURCE_FRAGMENT_NOT_FOUND",
                        message="部分资料片段不存在、不属于当前项目或不属于所选资料。",
                        status_code=404,
                        details={"source_fragment_ids": missing_fragment_ids},
                    )
            if len(fragments) > MAX_BATCH_FRAGMENTS:
                raise AppError(
                    code="FRAGMENT_EVIDENCE_BATCH_LIMIT_EXCEEDED",
                    message="单个 Evidence Draft 批次最多处理 200 个资料片段。",
                    status_code=422,
                    details={
                        "fragment_count": len(fragments),
                        "maximum": MAX_BATCH_FRAGMENTS,
                    },
                )
            routings = await repository.list_routings(project_id, source_asset_ids)
            material_lineage = await repository.list_material_lineage(
                project_id, source_asset_ids
            )
            onboarding_lineage = await repository.list_onboarding_lineage(
                project_id, source_asset_ids
            )
            evidence = await repository.list_evidence_for_fragments(
                project_id, [item.source_fragment_id for item in fragments]
            )
            jobs = await repository.list_collection_jobs(
                project_id, [item.collection_job_id for item in assets]
            )
            domain_counts = await repository.evidence_domain_counts(project_id)
        return _Snapshot(
            project=project,
            assets=tuple(assets),
            fragments=tuple(fragments),
            fragment_overflow=False,
            routings=tuple(routings),
            material_lineage=tuple(material_lineage),
            onboarding_lineage=tuple(onboarding_lineage),
            evidence=tuple(evidence),
            jobs=tuple(jobs),
            domain_counts=domain_counts,
        )

    def _build_drafts(
        self, snapshot: _Snapshot
    ) -> list[FragmentEvidenceBatchItemModel]:
        project = snapshot.project
        assets = {asset.source_asset_id: asset for asset in snapshot.assets}
        jobs = {job.collection_job_id: job for job in snapshot.jobs}
        routings = {routing.source_asset_id: routing for routing in snapshot.routings}
        evidence_by_fragment = {
            evidence.source_fragment_id: evidence for evidence in snapshot.evidence
        }
        material_by_asset: dict[str, list[CompetitorMaterialSelectionModel]] = defaultdict(list)
        for material_lineage in snapshot.material_lineage:
            material_by_asset[material_lineage.source_asset_id].append(material_lineage)
        onboarding_by_asset: dict[
            str, list[CompetitorSourceOnboardingItemModel]
        ] = defaultdict(list)
        for onboarding_lineage in snapshot.onboarding_lineage:
            onboarding_by_asset[onboarding_lineage.source_asset_id].append(
                onboarding_lineage
            )
        domain_counts = snapshot.domain_counts
        rows: list[FragmentEvidenceBatchItemModel] = []
        now = datetime.now(UTC)
        for fragment in snapshot.fragments:
            asset = assets[fragment.source_asset_id]
            job = jobs.get(asset.collection_job_id)
            routing = routings.get(asset.source_asset_id)
            product_role, product, dimensions, lineage_errors = self._lineage(
                asset.source_asset_id,
                material_by_asset,
                onboarding_by_asset,
                routing,
            )
            routes = self._confirmed_routes(routing)
            allowed = self._allowed_claim_types(routing, dimensions)
            blockers = list(lineage_errors)
            if asset.status != SourceAssetStatus.READY.value:
                blockers.append("SOURCE_NOT_READY")
            if job is None or job.status != CollectionJobStatus.SUCCEEDED.value:
                blockers.append("SOURCE_PROCESSING_NOT_SUCCEEDED")
            if fragment.verification_status != SourceFragmentVerificationStatus.VERIFIED.value:
                blockers.append("SOURCE_FRAGMENT_NOT_VERIFIED")
            if routing is None or routing.status != SourceRoutingStatus.CONFIRMED.value:
                blockers.append("SOURCE_ROUTING_NOT_CONFIRMED")
            if not allowed:
                blockers.append("SOURCE_CLAIM_TYPE_NOT_ALLOWED")
            existing = evidence_by_fragment.get(fragment.source_fragment_id)
            eligibility = (
                FragmentEvidenceEligibility.ALREADY_PROMOTED
                if existing is not None
                else FragmentEvidenceEligibility.BLOCKED
                if blockers
                else FragmentEvidenceEligibility.ELIGIBLE
            )
            confidence, authority, diversity, quality_reasons = self._quality_prior(
                fragment,
                asset,
                routes,
                domain_counts,
            )
            suggested = self._suggested_claim_type(dimensions, allowed)
            region = (
                ResearchBrief.model_validate(project.brief_json).primary_market
                if set(dimensions)
                & {
                    CompetitorResearchDimension.PRICE_CHANNEL,
                    CompetitorResearchDimension.USER_REVIEW,
                }
                else None
            )
            rows.append(
                FragmentEvidenceBatchItemModel(
                    fragment_evidence_item_id=f"fragment_item_{uuid4().hex[:16]}",
                    fragment_evidence_batch_id="pending",
                    project_id=fragment.project_id,
                    source_asset_id=fragment.source_asset_id,
                    source_fragment_id=fragment.source_fragment_id,
                    eligibility=eligibility.value,
                    block_reasons_json=sorted(set(blockers)),
                    confirmed_routes_json=[item.value for item in routes],
                    allowed_claim_types_json=[item.value for item in allowed],
                    suggested_claim_type=suggested.value if suggested else None,
                    product_role=product_role.value if product_role else None,
                    product_json=product.model_dump(mode="json") if product else None,
                    dimensions_json=[item.value for item in dimensions],
                    region=region,
                    confidence=confidence,
                    authority_score=authority,
                    recency_score=0.5,
                    diversity_score=diversity,
                    quality_reasons_json=[*quality_reasons, "publication date is unknown"],
                    existing_evidence_id=existing.evidence_id if existing else None,
                    selected=False,
                    selected_claim_type=None,
                    published_at=None,
                    user_segment=None,
                    promotion_status=FragmentEvidencePromotionStatus.NOT_SELECTED.value,
                    evidence_id=existing.evidence_id if existing else None,
                    error_code=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        return rows

    @classmethod
    def _lineage(
        cls,
        source_asset_id: str,
        material_by_asset: dict[str, list[CompetitorMaterialSelectionModel]],
        onboarding_by_asset: dict[str, list[CompetitorSourceOnboardingItemModel]],
        routing: SourceRoutingModel | None,
    ) -> tuple[
        ProductRole | None,
        ProductReference | None,
        list[CompetitorResearchDimension],
        list[str],
    ]:
        material = material_by_asset.get(source_asset_id, [])
        candidates: list[tuple[ProductRole, ProductReference]] = []
        dimensions: set[CompetitorResearchDimension] = set()
        for material_item in material:
            candidates.append(
                (
                    ProductRole(material_item.product_role),
                    ProductReference.model_validate(material_item.product_json),
                )
            )
            dimensions.add(CompetitorResearchDimension(material_item.dimension))
        if not material:
            for onboarding_item in onboarding_by_asset.get(source_asset_id, []):
                candidates.append(
                    (
                        ProductRole.COMPETITOR,
                        ProductReference.model_validate(onboarding_item.product_json),
                    )
                )
            if routing is not None:
                dimensions.update(
                    CompetitorResearchDimension(item)
                    for item in routing.confirmed_routes_json
                    if item in {dimension.value for dimension in CompetitorResearchDimension}
                )
        unique: dict[tuple[str, str, str, str], tuple[ProductRole, ProductReference]] = {}
        for candidate_role, candidate_product in candidates:
            key = (
                candidate_role.value,
                candidate_product.brand.casefold(),
                (candidate_product.model or "").casefold(),
                (candidate_product.variant or "").casefold(),
            )
            unique[key] = (candidate_role, candidate_product)
        errors: list[str] = []
        routes = cls._confirmed_routes(routing)
        resolved_role: ProductRole | None
        resolved_product: ProductReference | None
        if len(unique) > 1:
            errors.append("PRODUCT_LINEAGE_AMBIGUOUS")
            resolved_role = None
            resolved_product = None
        elif unique:
            selected_role, selected_product = next(iter(unique.values()))
            resolved_role = selected_role
            resolved_product = selected_product
        else:
            resolved_role = None
            resolved_product = None
            if set(routes) & _PRODUCT_ROUTES:
                errors.append("PRODUCT_LINEAGE_REQUIRED")
        return (
            resolved_role,
            resolved_product,
            sorted(dimensions, key=lambda item: item.value),
            errors,
        )

    @staticmethod
    def _confirmed_routes(routing: SourceRoutingModel | None) -> list[SourceRouteTarget]:
        if routing is None or routing.status != SourceRoutingStatus.CONFIRMED.value:
            return []
        return sorted(
            (SourceRouteTarget(item) for item in routing.confirmed_routes_json),
            key=lambda item: item.value,
        )

    @staticmethod
    def _allowed_claim_types(
        routing: SourceRoutingModel | None,
        dimensions: list[CompetitorResearchDimension],
    ) -> list[EvidenceClaimType]:
        if routing is None or routing.status != SourceRoutingStatus.CONFIRMED.value:
            return []
        allowed = {
            EvidenceClaimType(item)
            for item in routing.confirmed_claim_types_json
            if item != EvidenceClaimType.AGENT_INFERENCE.value
        }
        route_allowed: set[EvidenceClaimType] = set()
        for route_value in routing.confirmed_routes_json:
            route_allowed.update(ROUTE_ALLOWED_CLAIM_TYPES[SourceRouteTarget(route_value)])
        allowed &= route_allowed
        if dimensions:
            dimension_allowed: set[EvidenceClaimType] = set()
            for dimension in dimensions:
                dimension_allowed.update(ROUTE_ALLOWED_CLAIM_TYPES[SourceRouteTarget(dimension.value)])
            allowed &= dimension_allowed
        return sorted(allowed, key=lambda item: item.value)

    @staticmethod
    def _suggested_claim_type(
        dimensions: list[CompetitorResearchDimension],
        allowed: list[EvidenceClaimType],
    ) -> EvidenceClaimType | None:
        allowed_set = set(allowed)
        for dimension in dimensions:
            candidate = _SUGGESTED_CLAIM_TYPES[dimension]
            if candidate in allowed_set:
                return candidate
        return allowed[0] if allowed else None

    @staticmethod
    def _quality_prior(
        fragment: SourceFragmentModel,
        asset: SourceAssetModel,
        routes: list[SourceRouteTarget],
        domain_counts: dict[str, int],
    ) -> tuple[float, float, float, list[str]]:
        locator_kind = str(fragment.locator_json.get("kind") or "")
        is_media = locator_kind in {
            SourceLocatorKind.MEDIA_TIME.value,
            SourceLocatorKind.MEDIA_FRAME.value,
        }
        confidence = 0.85 if is_media else 0.95
        authority = max((_ROUTE_AUTHORITY[item] for item in routes), default=0.50)
        domain = (urlsplit(asset.source_url or "").hostname or "").casefold()
        domain_count = domain_counts.get(domain, 0) if domain else 0
        diversity = max(0.30, round(1.0 / (domain_count + 1), 2))
        reasons = [
            "verified source fragment with a persisted locator",
            "authority prior derived from confirmed source routing",
            f"project currently contains {domain_count} Evidence records from this domain",
        ]
        return confidence, authority, diversity, reasons

    @staticmethod
    def _recency_score(published_at: datetime | None, now: datetime) -> float:
        if published_at is None:
            return 0.50
        comparable = (
            published_at.replace(tzinfo=UTC)
            if published_at.tzinfo is None
            else published_at.astimezone(UTC)
        )
        age_days = max(0, (now - comparable).days)
        if age_days <= 366:
            return 0.90
        if age_days <= 366 * 2:
            return 0.75
        if age_days <= 366 * 5:
            return 0.60
        return 0.40

    @classmethod
    def _input_hash(
        cls,
        snapshot: _Snapshot,
        rows: list[FragmentEvidenceBatchItemModel],
    ) -> str:
        payload = {
            "policy_version": POLICY_VERSION,
            "fragment_overflow": snapshot.fragment_overflow,
            "items": [
                {
                    "source_asset_id": item.source_asset_id,
                    "source_fragment_id": item.source_fragment_id,
                    "eligibility": item.eligibility,
                    "block_reasons": item.block_reasons_json,
                    "routes": item.confirmed_routes_json,
                    "claim_types": item.allowed_claim_types_json,
                    "product": item.product_json,
                    "dimensions": item.dimensions_json,
                    "existing_evidence_id": item.existing_evidence_id,
                }
                for item in rows
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode()).hexdigest()

    async def _get_model(
        self, project_id: str, batch_id: str
    ) -> FragmentEvidenceBatchModel:
        async with self.database.session() as session:
            model = await FragmentEvidenceRepository(session).get_batch(project_id, batch_id)
        if model is None:
            raise self._batch_not_found(batch_id)
        return model

    async def _get_item(
        self, project_id: str, batch_id: str, item_id: str
    ) -> FragmentEvidenceBatchItemModel:
        batch = await self._get_model(project_id, batch_id)
        return self._item_by_id(batch, item_id)

    @staticmethod
    def _item_by_id(
        batch: FragmentEvidenceBatchModel, item_id: str
    ) -> FragmentEvidenceBatchItemModel:
        item = next(
            (
                candidate
                for candidate in batch.items
                if candidate.fragment_evidence_item_id == item_id
            ),
            None,
        )
        if item is None:
            raise AppError(
                code="FRAGMENT_EVIDENCE_ITEM_NOT_FOUND",
                message="Evidence Draft 项不存在。",
                status_code=404,
                details={"fragment_evidence_item_id": item_id},
            )
        return item

    @classmethod
    def _to_batch(cls, model: FragmentEvidenceBatchModel) -> FragmentEvidenceBatch:
        items = [
            cls._to_item(item)
            for item in sorted(
                model.items,
                key=lambda item: (
                    item.source_asset_id,
                    item.source_fragment.ordinal,
                    item.fragment_evidence_item_id,
                ),
            )
        ]
        decision = None
        if model.fragment_evidence_decision_id is not None:
            if model.decision_action is None:
                raise RuntimeError("fragment evidence decision action is missing")
            decision = FragmentEvidenceDecision(
                fragment_evidence_decision_id=model.fragment_evidence_decision_id,
                action=FragmentEvidenceDecisionAction(model.decision_action),
                selected_item_ids=model.selected_item_ids_json,
                actor=model.decided_by or "",
                reason=model.decision_reason or "",
                created_at=model.decided_at or model.updated_at,
            )
        return FragmentEvidenceBatch(
            fragment_evidence_batch_id=model.fragment_evidence_batch_id,
            project_id=model.project_id,
            status=FragmentEvidenceBatchStatus(model.status),
            source_asset_ids=model.source_asset_ids_json,
            policy_version=model.policy_version,
            input_hash=model.input_hash,
            items=items,
            eligible_count=sum(
                item.eligibility is FragmentEvidenceEligibility.ELIGIBLE for item in items
            ),
            blocked_count=sum(
                item.eligibility is FragmentEvidenceEligibility.BLOCKED for item in items
            ),
            already_promoted_count=sum(
                item.eligibility is FragmentEvidenceEligibility.ALREADY_PROMOTED for item in items
            ),
            promoted_count=sum(
                item.promotion_status is FragmentEvidencePromotionStatus.SUCCEEDED for item in items
            ),
            failed_count=sum(
                item.promotion_status is FragmentEvidencePromotionStatus.FAILED for item in items
            ),
            decision=decision,
            requested_by=model.requested_by,
            purpose=model.purpose,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_item(model: FragmentEvidenceBatchItemModel) -> FragmentEvidenceBatchItem:
        return FragmentEvidenceBatchItem(
            fragment_evidence_item_id=model.fragment_evidence_item_id,
            source_asset_id=model.source_asset_id,
            source_fragment=SourceFragment.model_validate(
                {
                    "source_fragment_id": model.source_fragment.source_fragment_id,
                    "parsed_artifact_id": model.source_fragment.parsed_artifact_id,
                    "project_id": model.source_fragment.project_id,
                    "source_asset_id": model.source_fragment.source_asset_id,
                    "ordinal": model.source_fragment.ordinal,
                    "locator": model.source_fragment.locator_json,
                    "original_excerpt": model.source_fragment.original_excerpt,
                    "excerpt_hash": model.source_fragment.excerpt_hash,
                    "verification_status": model.source_fragment.verification_status,
                    "created_at": model.source_fragment.created_at,
                }
            ),
            eligibility=FragmentEvidenceEligibility(model.eligibility),
            block_reasons=model.block_reasons_json,
            confirmed_routes=[SourceRouteTarget(item) for item in model.confirmed_routes_json],
            allowed_claim_types=[
                EvidenceClaimType(item) for item in model.allowed_claim_types_json
            ],
            suggested_claim_type=(
                EvidenceClaimType(model.suggested_claim_type)
                if model.suggested_claim_type
                else None
            ),
            product_role=ProductRole(model.product_role) if model.product_role else None,
            product=(
                ProductReference.model_validate(model.product_json)
                if model.product_json
                else None
            ),
            dimensions=[
                CompetitorResearchDimension(item) for item in model.dimensions_json
            ],
            region=model.region,
            quality_prior=FragmentEvidenceQualityPrior(
                policy_version=POLICY_VERSION,
                confidence=model.confidence,
                authority_score=model.authority_score,
                recency_score=model.recency_score,
                diversity_score=model.diversity_score,
                reasons=model.quality_reasons_json,
            ),
            existing_evidence_id=model.existing_evidence_id,
            selected=model.selected,
            selected_claim_type=(
                EvidenceClaimType(model.selected_claim_type)
                if model.selected_claim_type
                else None
            ),
            published_at=model.published_at,
            user_segment=model.user_segment,
            promotion_status=FragmentEvidencePromotionStatus(model.promotion_status),
            evidence=(
                SourceEvidencePromotionService._to_evidence(model.evidence)
                if model.evidence
                else None
            ),
            error_code=model.error_code,
        )

    @staticmethod
    def _assert_idempotent(
        batch: FragmentEvidenceBatchModel,
        payload: FragmentEvidenceDecisionCreate,
    ) -> None:
        def normalized_time(value: datetime | None) -> str | None:
            if value is None:
                return None
            comparable = (
                value.replace(tzinfo=UTC)
                if value.tzinfo is None
                else value.astimezone(UTC)
            )
            return comparable.isoformat()

        stored_items = {
            item.fragment_evidence_item_id: (
                item.selected_claim_type,
                normalized_time(item.published_at),
                item.user_segment,
            )
            for item in batch.items
            if item.selected
        }
        requested_items = {
            item.fragment_evidence_item_id: (
                item.claim_type.value,
                normalized_time(item.published_at),
                item.user_segment,
            )
            for item in payload.selections
        }
        if (
            batch.decision_action != payload.action.value
            or batch.decided_by != payload.actor
            or batch.decision_reason != payload.reason
            or stored_items != requested_items
        ):
            raise AppError(
                code="FRAGMENT_EVIDENCE_DECISION_CONFLICT",
                message="该 Evidence Draft 批次已经保存了不同的审核决定。",
                status_code=409,
            )

    async def _event(
        self,
        session: AsyncSession,
        project_id: str,
        event_type: str,
        data: dict[str, object],
        now: datetime,
    ) -> None:
        await ProjectRepository(session).add_event(
            ProjectEventModel(
                event_id=f"evt_{uuid4().hex[:16]}",
                project_id=project_id,
                sequence_number=0,
                event_type=event_type,
                data_json=data,
                trace_id=self.trace_id,
                created_at=now,
            )
        )

    @staticmethod
    def _product_label(product: ProductReference) -> str:
        return " ".join(filter(None, (product.brand, product.model, product.variant)))

    @staticmethod
    def _project_not_found(project_id: str) -> AppError:
        return AppError(
            code="PROJECT_NOT_FOUND",
            message="研究项目不存在。",
            status_code=404,
            details={"project_id": project_id},
        )

    @staticmethod
    def _batch_not_found(batch_id: str) -> AppError:
        return AppError(
            code="FRAGMENT_EVIDENCE_BATCH_NOT_FOUND",
            message="Fragment Evidence 审核批次不存在或不属于当前项目。",
            status_code=404,
            details={"fragment_evidence_batch_id": batch_id},
        )
