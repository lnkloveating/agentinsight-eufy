"""将已确认竞品候选原子登记为授权 Source Asset，并保留完整血缘。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.agents.competitor.discovery_contracts import (
    CompetitorCandidateDecisionAction,
    CompetitorDiscoveryCandidateReference,
    CompetitorDiscoveryPayload,
    CompetitorDiscoveryProposal,
)
from app.application.competitor_discovery.service import COMPETITOR_DISCOVERY_TASK_ID
from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.competitor_source_onboarding_repository import (
    CompetitorSourceOnboardingRepository,
)
from app.infrastructure.database.models import (
    CollectionJobModel,
    CompetitorSourceOnboardingItemModel,
    CompetitorSourceOnboardingModel,
    ProjectEventModel,
    SourceAssetModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.competitor_source_onboarding import (
    CompetitorSourceOnboarding,
    CompetitorSourceOnboardingCreate,
    CompetitorSourceOnboardingItem,
    CompetitorSourceOnboardingPage,
    CompetitorSourceOnboardingResult,
)
from app.schemas.source import (
    SourceAsset,
    SourceAssetKind,
    SourceAssetStatus,
    SourceAuthorizationBasis,
    SourceMediaCategory,
)
from app.schemas.source_processing import CollectionJobStatus
from app.schemas.source_requirements import ProductReference
from app.sources.validation import normalize_public_url, source_url_hash


@dataclass(frozen=True)
class _SelectedCandidate:
    proposal: CompetitorDiscoveryProposal
    candidate: CompetitorDiscoveryCandidateReference
    product: ProductReference
    normalized_url: str


class CompetitorSourceOnboardingService:
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
        self,
        project_id: str,
        payload: CompetitorSourceOnboardingCreate,
    ) -> CompetitorSourceOnboardingResult:
        existing = await self._get_by_artifact(project_id, payload.artifact_id)
        if existing is not None:
            return CompetitorSourceOnboardingResult(
                onboarding=self._to_schema(existing), created=False
            )

        for attempt in range(2):
            try:
                onboarding_id = await self._create_once(project_id, payload)
            except IntegrityError as exc:
                existing = await self._get_by_artifact(project_id, payload.artifact_id)
                if existing is not None:
                    return CompetitorSourceOnboardingResult(
                        onboarding=self._to_schema(existing), created=False
                    )
                if attempt == 0:
                    continue
                raise AppError(
                    code="COMPETITOR_SOURCE_ONBOARDING_CONFLICT",
                    message="竞品来源接入发生并发冲突，请安全重试。",
                    status_code=409,
                    details={"artifact_id": payload.artifact_id, "retryable": True},
                ) from exc
            onboarding = await self._get_by_artifact(project_id, payload.artifact_id)
            if onboarding is None or onboarding.onboarding_id != onboarding_id:
                raise AppError(
                    code="COMPETITOR_SOURCE_ONBOARDING_NOT_FOUND",
                    message="竞品来源接入记录保存失败。",
                    status_code=500,
                )
            await self.event_broker.notify(project_id)
            return CompetitorSourceOnboardingResult(
                onboarding=self._to_schema(onboarding), created=True
            )
        raise RuntimeError("competitor source onboarding retry loop exhausted")

    async def list_onboardings(
        self, project_id: str
    ) -> CompetitorSourceOnboardingPage:
        async with self.database.session() as session:
            repository = CompetitorSourceOnboardingRepository(session)
            if await repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            models = await repository.list_onboardings(project_id)
        return CompetitorSourceOnboardingPage(
            items=[self._to_schema(item) for item in models],
            total=len(models),
        )

    async def _create_once(
        self,
        project_id: str,
        payload: CompetitorSourceOnboardingCreate,
    ) -> str:
        now = datetime.now(UTC)
        onboarding_id = f"source_onboarding_{uuid4().hex[:12]}"
        async with self.database.session() as session:
            repository = CompetitorSourceOnboardingRepository(session)
            project = await repository.get_project(project_id)
            if project is None:
                raise self._project_not_found(project_id)
            artifact = await repository.get_artifact(project_id, payload.artifact_id)
            if artifact is None or artifact.task_id != COMPETITOR_DISCOVERY_TASK_ID:
                raise self._artifact_not_found(payload.artifact_id)
            decision = await repository.get_decision(project_id, payload.artifact_id)
            if (
                decision is None
                or decision.action != CompetitorCandidateDecisionAction.CONFIRM.value
            ):
                raise AppError(
                    code="COMPETITOR_SOURCE_ONBOARDING_CONFIRM_REQUIRED",
                    message="只有已通过 Candidate Gate 确认的竞品 Artifact 才能接入来源。",
                    status_code=409,
                    details={"artifact_id": payload.artifact_id},
                )
            try:
                artifact_payload = CompetitorDiscoveryPayload.model_validate(
                    artifact.payload_json
                )
            except ValueError as exc:
                raise AppError(
                    code="COMPETITOR_SOURCE_ONBOARDING_ARTIFACT_INVALID",
                    message="竞品候选 Artifact 无法通过接入前结构校验。",
                    status_code=409,
                ) from exc
            selections = self._selected_candidates(
                artifact_payload,
                decision.selected_proposal_ids_json,
            )
            scope = await repository.get_scope(project_id)
            if scope is None or not self._scope_contains(
                scope.competitors_json,
                [item.product for item in selections],
            ):
                raise AppError(
                    code="COMPETITOR_SOURCE_ONBOARDING_SCOPE_STALE",
                    message="正式竞品范围已变化，请重新完成 Candidate Gate 后再接入来源。",
                    status_code=409,
                    details={"artifact_id": payload.artifact_id},
                )

            onboarding = CompetitorSourceOnboardingModel(
                onboarding_id=onboarding_id,
                project_id=project_id,
                artifact_id=payload.artifact_id,
                decision_id=decision.decision_id,
                status="completed",
                authorization_basis=payload.authorization_basis.value,
                authorized_by=payload.authorized_by,
                purpose=payload.purpose,
                created_at=now,
            )
            await repository.add_onboarding(onboarding)
            project_repository = ProjectRepository(session)
            created_count = 0
            source_asset_ids: set[str] = set()
            for selection in selections:
                source_asset, created, event_type = await self._source_asset(
                    repository,
                    project_id,
                    onboarding_id,
                    payload,
                    selection,
                    now,
                )
                created_count += int(created)
                source_asset_ids.add(source_asset.source_asset_id)
                if event_type is not None:
                    await project_repository.add_event(
                        self._source_event(
                            source_asset,
                            event_type,
                            onboarding_id,
                            selection,
                            now,
                        )
                    )
                await repository.add_item(
                    CompetitorSourceOnboardingItemModel(
                        onboarding_item_id=f"onboarding_item_{uuid4().hex[:12]}",
                        onboarding_id=onboarding_id,
                        project_id=project_id,
                        proposal_id=selection.proposal.proposal_id,
                        candidate_id=selection.candidate.candidate_id,
                        source_asset_id=source_asset.source_asset_id,
                        product_json=selection.product.model_dump(mode="json"),
                        source_asset_created=created,
                        created_at=now,
                    )
                )
            await project_repository.add_event(
                ProjectEventModel(
                    event_id=f"evt_{uuid4().hex[:16]}",
                    project_id=project_id,
                    sequence_number=0,
                    event_type="competitor_source_onboarding_completed",
                    data_json={
                        "onboarding_id": onboarding_id,
                        "artifact_id": payload.artifact_id,
                        "decision_id": decision.decision_id,
                        "item_count": len(selections),
                        "unique_source_asset_count": len(source_asset_ids),
                        "created_source_asset_count": created_count,
                        "authorized_by": payload.authorized_by,
                    },
                    trace_id=self.trace_id,
                    created_at=now,
                )
            )
            try:
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise
        return onboarding_id

    async def _source_asset(
        self,
        repository: CompetitorSourceOnboardingRepository,
        project_id: str,
        onboarding_id: str,
        payload: CompetitorSourceOnboardingCreate,
        selection: _SelectedCandidate,
        now: datetime,
    ) -> tuple[SourceAssetModel, bool, str | None]:
        content_hash = source_url_hash(selection.normalized_url)
        existing = await repository.get_source_by_hash(project_id, content_hash)
        if existing is not None and existing.status == SourceAssetStatus.READY.value:
            return existing, False, None

        display_name = self._display_name(selection)
        purpose = self._source_purpose(payload.purpose, selection.product)
        if existing is not None:
            collection_job_id = f"collect_{uuid4().hex[:16]}"
            await repository.add_collection_job(
                self._collection_job(
                    collection_job_id,
                    project_id,
                    existing.source_asset_id,
                    selection.normalized_url,
                    onboarding_id,
                    selection,
                    now,
                )
            )
            existing.collection_job_id = collection_job_id
            existing.status = SourceAssetStatus.READY.value
            existing.display_name = display_name
            existing.source_url = selection.normalized_url
            existing.normalized_source_url = selection.normalized_url
            existing.authorization_basis = payload.authorization_basis.value
            existing.authorization_confirmed_at = now
            existing.authorized_by = payload.authorized_by
            existing.purpose = purpose
            existing.updated_at = now
            existing.deleted_at = None
            return existing, False, "source_asset_restored"

        source_asset_id = f"source_{uuid4().hex[:16]}"
        collection_job_id = f"collect_{uuid4().hex[:16]}"
        await repository.add_collection_job(
            self._collection_job(
                collection_job_id,
                project_id,
                source_asset_id,
                selection.normalized_url,
                onboarding_id,
                selection,
                now,
            )
        )
        source_asset = SourceAssetModel(
            source_asset_id=source_asset_id,
            project_id=project_id,
            collection_job_id=collection_job_id,
            kind=SourceAssetKind.LINK.value,
            status=SourceAssetStatus.READY.value,
            display_name=display_name,
            original_filename=None,
            source_url=selection.normalized_url,
            normalized_source_url=selection.normalized_url,
            storage_key=None,
            media_type="text/html",
            media_category=SourceMediaCategory.WEBPAGE.value,
            content_hash=content_hash,
            byte_size=0,
            authorization_basis=payload.authorization_basis.value,
            authorization_confirmed_at=now,
            authorized_by=payload.authorized_by,
            purpose=purpose,
            created_at=now,
            updated_at=now,
        )
        await repository.add_source_asset(source_asset)
        return source_asset, True, "source_asset_created"

    @staticmethod
    def _collection_job(
        collection_job_id: str,
        project_id: str,
        source_asset_id: str,
        source_url: str,
        onboarding_id: str,
        selection: _SelectedCandidate,
        now: datetime,
    ) -> CollectionJobModel:
        return CollectionJobModel(
            collection_job_id=collection_job_id,
            project_id=project_id,
            task_id="competitor_source_onboarding",
            source_url=source_url,
            source_type=SourceMediaCategory.WEBPAGE.value,
            status=CollectionJobStatus.QUEUED.value,
            attempt_count=0,
            result_json={
                "source_asset_id": source_asset_id,
                "onboarding_id": onboarding_id,
                "proposal_id": selection.proposal.proposal_id,
                "candidate_id": selection.candidate.candidate_id,
                "product": selection.product.model_dump(mode="json"),
            },
            created_at=now,
            updated_at=now,
        )

    def _source_event(
        self,
        source_asset: SourceAssetModel,
        event_type: str,
        onboarding_id: str,
        selection: _SelectedCandidate,
        now: datetime,
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=source_asset.project_id,
            sequence_number=0,
            event_type=event_type,
            data_json={
                "source_asset_id": source_asset.source_asset_id,
                "collection_job_id": source_asset.collection_job_id,
                "kind": source_asset.kind,
                "media_category": source_asset.media_category,
                "status": source_asset.status,
                "origin": "competitor_source_onboarding",
                "onboarding_id": onboarding_id,
                "proposal_id": selection.proposal.proposal_id,
                "candidate_id": selection.candidate.candidate_id,
            },
            trace_id=self.trace_id,
            created_at=now,
        )

    @staticmethod
    def _selected_candidates(
        payload: CompetitorDiscoveryPayload,
        selected_proposal_ids: list[str],
    ) -> list[_SelectedCandidate]:
        proposals = {item.proposal_id: item for item in payload.proposals}
        candidates = {item.candidate_id: item for item in payload.input_candidates}
        unsupported_proposals = sorted(set(selected_proposal_ids) - set(proposals))
        if unsupported_proposals:
            raise AppError(
                code="COMPETITOR_SOURCE_ONBOARDING_ARTIFACT_INVALID",
                message="Candidate Gate 引用了 Artifact 中不存在的竞品 proposal。",
                status_code=409,
                details={"unsupported_proposal_ids": unsupported_proposals},
            )
        selections: list[_SelectedCandidate] = []
        for proposal_id in selected_proposal_ids:
            proposal = proposals[proposal_id]
            product = ProductReference(
                brand=proposal.brand,
                model=proposal.model,
                variant=proposal.variant,
            )
            for candidate_id in proposal.candidate_ids:
                candidate = candidates.get(candidate_id)
                if candidate is None:
                    raise AppError(
                        code="COMPETITOR_SOURCE_ONBOARDING_ARTIFACT_INVALID",
                        message="竞品 proposal 引用了 Artifact 中不存在的来源候选。",
                        status_code=409,
                        details={"candidate_id": candidate_id},
                    )
                normalized_url = normalize_public_url(str(candidate.source_url))
                hostname = (urlsplit(normalized_url).hostname or "").casefold()
                if hostname != candidate.source_domain.casefold():
                    raise AppError(
                        code="COMPETITOR_SOURCE_ONBOARDING_ARTIFACT_INVALID",
                        message="候选来源域名与安全规范化 URL 不一致。",
                        status_code=409,
                        details={"candidate_id": candidate_id},
                    )
                selections.append(
                    _SelectedCandidate(
                        proposal=proposal,
                        candidate=candidate,
                        product=product,
                        normalized_url=normalized_url,
                    )
                )
        if not selections:
            raise AppError(
                code="COMPETITOR_SOURCE_ONBOARDING_CANDIDATES_REQUIRED",
                message="已确认的竞品 proposal 没有可接入的候选 URL。",
                status_code=409,
            )
        return selections

    @classmethod
    def _scope_contains(
        cls,
        scope_products: list[dict[str, object]],
        selected_products: list[ProductReference],
    ) -> bool:
        scope_identities = {
            cls._product_identity(ProductReference.model_validate(item))
            for item in scope_products
        }
        return all(
            cls._product_identity(product) in scope_identities
            for product in selected_products
        )

    @staticmethod
    def _product_identity(product: ProductReference) -> tuple[str, str, str]:
        return (
            product.brand.strip().casefold(),
            (product.model or "").strip().casefold(),
            (product.variant or "").strip().casefold(),
        )

    @staticmethod
    def _product_label(product: ProductReference) -> str:
        return " ".join(filter(None, (product.brand, product.model, product.variant)))

    @classmethod
    def _display_name(cls, selection: _SelectedCandidate) -> str:
        return f"{cls._product_label(selection.product)} — {selection.candidate.title}"[:255]

    @classmethod
    def _source_purpose(cls, purpose: str, product: ProductReference) -> str:
        return f"Competitor source for {cls._product_label(product)}. {purpose}"[:500]

    async def _get_by_artifact(
        self, project_id: str, artifact_id: str
    ) -> CompetitorSourceOnboardingModel | None:
        async with self.database.session() as session:
            return await CompetitorSourceOnboardingRepository(
                session
            ).get_onboarding_by_artifact(project_id, artifact_id)

    @classmethod
    def _to_schema(
        cls, model: CompetitorSourceOnboardingModel
    ) -> CompetitorSourceOnboarding:
        sorted_items = sorted(
            model.items,
            key=lambda item: (item.proposal_id, item.candidate_id),
        )
        items = [
            CompetitorSourceOnboardingItem(
                onboarding_item_id=item.onboarding_item_id,
                proposal_id=item.proposal_id,
                candidate_id=item.candidate_id,
                product=ProductReference.model_validate(item.product_json),
                source_asset=cls._source_asset_schema(item.source_asset),
                source_asset_created=item.source_asset_created,
            )
            for item in sorted_items
        ]
        created_count = sum(item.source_asset_created for item in sorted_items)
        unique_asset_count = len({item.source_asset_id for item in sorted_items})
        return CompetitorSourceOnboarding(
            onboarding_id=model.onboarding_id,
            project_id=model.project_id,
            artifact_id=model.artifact_id,
            decision_id=model.decision_id,
            status="completed",
            authorization_basis=SourceAuthorizationBasis.PUBLICLY_AVAILABLE,
            authorized_by=model.authorized_by,
            purpose=model.purpose,
            total_item_count=len(items),
            unique_source_asset_count=unique_asset_count,
            created_source_asset_count=created_count,
            reused_source_asset_count=len(items) - created_count,
            items=items,
            created_at=model.created_at,
        )

    @staticmethod
    def _source_asset_schema(model: SourceAssetModel) -> SourceAsset:
        return SourceAsset.model_validate(
            {
                "source_asset_id": model.source_asset_id,
                "project_id": model.project_id,
                "kind": model.kind,
                "status": model.status,
                "display_name": model.display_name,
                "original_filename": model.original_filename,
                "source_url": model.source_url,
                "media_type": model.media_type,
                "media_category": model.media_category,
                "content_hash": model.content_hash,
                "byte_size": model.byte_size,
                "authorization_basis": model.authorization_basis,
                "authorization_confirmed_at": model.authorization_confirmed_at,
                "authorized_by": model.authorized_by,
                "purpose": model.purpose,
                "collection_job_id": model.collection_job_id,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
                "deleted_at": model.deleted_at,
            }
        )

    @staticmethod
    def _artifact_not_found(artifact_id: str) -> AppError:
        return AppError(
            code="COMPETITOR_DISCOVERY_ARTIFACT_NOT_FOUND",
            message="竞品候选 Artifact 不存在或不属于当前项目。",
            status_code=404,
            details={"artifact_id": artifact_id},
        )

    @staticmethod
    def _project_not_found(project_id: str) -> AppError:
        return AppError(
            code="PROJECT_NOT_FOUND",
            message="研究项目不存在。",
            status_code=404,
            details={"project_id": project_id},
        )
