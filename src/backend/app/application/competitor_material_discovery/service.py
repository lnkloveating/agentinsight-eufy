"""按确认产品/维度发现真实材料，并在人工 Gate 后登记来源。"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.events import ProjectEventBroker
from app.application.source_discovery import SearchDiscoveryService
from app.core.errors import AppError
from app.infrastructure.database.competitor_material_discovery_repository import (
    CompetitorMaterialDiscoveryRepository,
)
from app.infrastructure.database.models import (
    CollectionJobModel,
    CompetitorMaterialDecisionModel,
    CompetitorMaterialDiscoveryItemModel,
    CompetitorMaterialDiscoveryModel,
    CompetitorMaterialSelectionModel,
    ProjectEventModel,
    SourceAssetModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.competitor_material_discovery import (
    CompetitorMaterialDecision,
    CompetitorMaterialDecisionAction,
    CompetitorMaterialDecisionCreate,
    CompetitorMaterialDecisionResult,
    CompetitorMaterialDiscovery,
    CompetitorMaterialDiscoveryCreate,
    CompetitorMaterialDiscoveryItem,
    CompetitorMaterialDiscoveryPage,
    CompetitorMaterialDiscoveryStatus,
    CompetitorMaterialProductSelection,
    CompetitorMaterialSelection,
)
from app.schemas.project import ResearchBrief
from app.schemas.search_discovery import (
    SearchDiscoveryCandidate,
    SearchDiscoveryCreate,
    SearchDiscoveryIntent,
    SearchDiscoveryRunStatus,
)
from app.schemas.source import (
    SourceAsset,
    SourceAssetKind,
    SourceAssetStatus,
    SourceAuthorizationBasis,
    SourceMediaCategory,
)
from app.schemas.source_processing import CollectionJobStatus
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    ProductReference,
    ProductRole,
)
from app.sources.validation import normalize_public_url, source_url_hash


@dataclass(frozen=True)
class _CandidateSelection:
    item: CompetitorMaterialDiscoveryItemModel
    candidate: SearchDiscoveryCandidate
    normalized_url: str


class CompetitorMaterialDiscoveryService:
    def __init__(
        self,
        database: Database,
        search_discovery_service: SearchDiscoveryService,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.search_discovery_service = search_discovery_service
        self.event_broker = event_broker
        self.trace_id = trace_id

    async def create(
        self, project_id: str, payload: CompetitorMaterialDiscoveryCreate
    ) -> CompetitorMaterialDiscovery:
        connector = self.search_discovery_service.registry.resolve(payload.provider_id)
        if connector is None:
            raise AppError(
                code="SEARCH_PROVIDER_NOT_FOUND",
                message="请求的搜索 Provider 未注册。",
                status_code=422,
                details={"provider_id": payload.provider_id},
            )
        products, dimensions, scope_hash, region = await self._resolve_plan(
            project_id, payload
        )
        now = datetime.now(UTC)
        discovery_id = f"material_discovery_{uuid4().hex[:12]}"
        discovery = CompetitorMaterialDiscoveryModel(
            material_discovery_id=discovery_id,
            project_id=project_id,
            status=CompetitorMaterialDiscoveryStatus.RUNNING.value,
            provider_id=payload.provider_id,
            max_results_per_query=payload.max_results_per_query,
            products_json=[item.model_dump(mode="json") for item in products],
            dimensions_json=[item.value for item in dimensions],
            scope_hash=scope_hash,
            requested_by=payload.requested_by,
            purpose=payload.purpose,
            created_at=now,
            completed_at=None,
        )
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            await repository.add(discovery)
            await self._event(
                session,
                project_id,
                "competitor_material_discovery_started",
                {
                    "material_discovery_id": discovery_id,
                    "item_count": len(products) * len(dimensions),
                },
                now,
            )
            await repository.commit()
        await self.event_broker.notify(project_id)

        runs = []
        for product in products:
            for dimension in dimensions:
                query = self.build_query(product.product, dimension, region)
                run = await self.search_discovery_service.create(
                    project_id,
                    SearchDiscoveryCreate(
                        query=query,
                        intent=SearchDiscoveryIntent(dimension.value),
                        provider_id=payload.provider_id,
                        max_results=payload.max_results_per_query,
                        include_domains=[],
                        exclude_domains=[],
                        requested_by=payload.requested_by,
                        purpose=(
                            f"{payload.purpose} Product: {self._product_label(product.product)}; "
                            f"dimension: {dimension.value}."
                        )[:500],
                    ),
                )
                runs.append(run)
                async with self.database.session() as session:
                    repository = CompetitorMaterialDiscoveryRepository(session)
                    await repository.add(
                        CompetitorMaterialDiscoveryItemModel(
                            material_discovery_item_id=f"material_item_{uuid4().hex[:12]}",
                            material_discovery_id=discovery_id,
                            project_id=project_id,
                            search_discovery_run_id=run.search_discovery_run_id,
                            product_role=product.product_role.value,
                            product_identity=self._identity_string(product.product),
                            product_json=product.product.model_dump(mode="json"),
                            dimension=dimension.value,
                            query=query,
                            created_at=datetime.now(UTC),
                        )
                    )
                    await repository.commit()

        succeeded = sum(run.status is SearchDiscoveryRunStatus.SUCCEEDED for run in runs)
        blocked = sum(run.status is SearchDiscoveryRunStatus.BLOCKED for run in runs)
        if succeeded == len(runs):
            final_status = CompetitorMaterialDiscoveryStatus.COMPLETED
        elif succeeded:
            final_status = CompetitorMaterialDiscoveryStatus.PARTIAL
        elif blocked == len(runs):
            final_status = CompetitorMaterialDiscoveryStatus.BLOCKED
        else:
            final_status = CompetitorMaterialDiscoveryStatus.FAILED
        completed_at = datetime.now(UTC)
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            saved = await repository.get_discovery(project_id, discovery_id)
            if saved is None:
                raise self._not_found(discovery_id)
            saved.status = final_status.value
            saved.completed_at = completed_at
            await self._event(
                session,
                project_id,
                "competitor_material_discovery_completed",
                {
                    "material_discovery_id": discovery_id,
                    "status": final_status.value,
                    "item_count": len(runs),
                    "completed_item_count": succeeded,
                    "candidate_count": sum(run.result_count for run in runs),
                },
                completed_at,
            )
            await repository.commit()
        await self.event_broker.notify(project_id)
        return await self.get(project_id, discovery_id)

    async def get(
        self, project_id: str, material_discovery_id: str
    ) -> CompetitorMaterialDiscovery:
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            if await repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            model = await repository.get_discovery(project_id, material_discovery_id)
        if model is None:
            raise self._not_found(material_discovery_id)
        return self._to_discovery(model)

    async def list_discoveries(
        self, project_id: str
    ) -> CompetitorMaterialDiscoveryPage:
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            if await repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            models = await repository.list_discoveries(project_id)
        return CompetitorMaterialDiscoveryPage(
            items=[self._to_discovery(item) for item in models], total=len(models)
        )

    async def decide(
        self,
        project_id: str,
        material_discovery_id: str,
        payload: CompetitorMaterialDecisionCreate,
    ) -> CompetitorMaterialDecisionResult:
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            discovery = await repository.get_discovery(project_id, material_discovery_id)
            if discovery is None:
                raise self._not_found(material_discovery_id)
            if discovery.decision is not None:
                self._assert_idempotent(discovery.decision, payload)
                return CompetitorMaterialDecisionResult(
                    decision=self._to_decision(discovery.decision), created=False
                )
        try:
            return await self._create_decision(project_id, material_discovery_id, payload)
        except IntegrityError:
            async with self.database.session() as session:
                discovery = await CompetitorMaterialDiscoveryRepository(session).get_discovery(
                    project_id, material_discovery_id
                )
            if discovery is None or discovery.decision is None:
                raise
            self._assert_idempotent(discovery.decision, payload)
            return CompetitorMaterialDecisionResult(
                decision=self._to_decision(discovery.decision), created=False
            )

    async def _create_decision(
        self,
        project_id: str,
        material_discovery_id: str,
        payload: CompetitorMaterialDecisionCreate,
    ) -> CompetitorMaterialDecisionResult:
        now = datetime.now(UTC)
        decision_id = f"material_decision_{uuid4().hex[:12]}"
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            discovery = await repository.get_discovery(project_id, material_discovery_id)
            if discovery is None:
                raise self._not_found(material_discovery_id)
            if discovery.status == CompetitorMaterialDiscoveryStatus.RUNNING.value:
                raise AppError(
                    code="COMPETITOR_MATERIAL_DISCOVERY_RUNNING",
                    message="资料发现仍在运行，暂不能提交 Gate 决定。",
                    status_code=409,
                )
            selections = self._resolve_candidates(discovery, payload.selected_candidate_ids)
            decision = CompetitorMaterialDecisionModel(
                material_decision_id=decision_id,
                material_discovery_id=material_discovery_id,
                project_id=project_id,
                action=payload.action.value,
                selected_candidate_ids_json=payload.selected_candidate_ids,
                authorization_basis=(
                    payload.authorization_basis.value if payload.authorization_basis else None
                ),
                authorization_confirmed=payload.authorization_confirmed,
                actor=payload.actor,
                reason=payload.reason,
                created_at=now,
            )
            await repository.add(decision)
            created_count = 0
            for selection in selections:
                source_asset, created, event_type = await self._source_asset(
                    repository,
                    project_id,
                    material_discovery_id,
                    payload,
                    selection,
                    now,
                )
                created_count += int(created)
                if event_type:
                    await self._event(
                        session,
                        project_id,
                        event_type,
                        {
                            "origin": "competitor_material_discovery",
                            "material_discovery_id": material_discovery_id,
                            "candidate_id": selection.candidate.candidate_id,
                            "source_asset_id": source_asset.source_asset_id,
                            "collection_job_id": source_asset.collection_job_id,
                        },
                        now,
                    )
                await repository.add(
                    CompetitorMaterialSelectionModel(
                        material_selection_id=f"material_selection_{uuid4().hex[:12]}",
                        material_decision_id=decision_id,
                        material_discovery_item_id=selection.item.material_discovery_item_id,
                        project_id=project_id,
                        search_discovery_run_id=selection.item.search_discovery_run_id,
                        candidate_id=selection.candidate.candidate_id,
                        source_asset_id=source_asset.source_asset_id,
                        product_role=selection.item.product_role,
                        product_json=selection.item.product_json,
                        dimension=selection.item.dimension,
                        candidate_json=selection.candidate.model_dump(mode="json"),
                        source_asset_created=created,
                        created_at=now,
                    )
                )
            await self._event(
                session,
                project_id,
                "competitor_material_decision_saved",
                {
                    "material_discovery_id": material_discovery_id,
                    "material_decision_id": decision_id,
                    "action": payload.action.value,
                    "selected_candidate_count": len(selections),
                    "created_source_asset_count": created_count,
                },
                now,
            )
            try:
                await repository.commit()
            except Exception:
                await repository.rollback()
                raise
        await self.event_broker.notify(project_id)
        discovery_schema = await self.get(project_id, material_discovery_id)
        if discovery_schema.decision is None:
            raise RuntimeError("competitor material decision was not persisted")
        return CompetitorMaterialDecisionResult(
            decision=discovery_schema.decision, created=True
        )

    async def _resolve_plan(
        self, project_id: str, payload: CompetitorMaterialDiscoveryCreate
    ) -> tuple[
        list[CompetitorMaterialProductSelection],
        list[CompetitorResearchDimension],
        str,
        str,
    ]:
        async with self.database.session() as session:
            repository = CompetitorMaterialDiscoveryRepository(session)
            project = await repository.get_project(project_id)
            if project is None:
                raise self._project_not_found(project_id)
            scope = await repository.get_scope(project_id)
        if scope is None:
            raise AppError(
                code="SOURCE_REQUIREMENT_SCOPE_REQUIRED",
                message="请先确认目标产品、竞品和研究维度。",
                status_code=409,
            )
        available = [
            CompetitorMaterialProductSelection(
                product_role=ProductRole.TARGET,
                product=ProductReference.model_validate(item),
            )
            for item in scope.target_products_json
        ] + [
            CompetitorMaterialProductSelection(
                product_role=ProductRole.COMPETITOR,
                product=ProductReference.model_validate(item),
            )
            for item in scope.competitors_json
        ]
        exact = [item for item in available if item.product.model]
        requested = payload.products or exact
        available_keys = {self._selection_identity(item) for item in exact}
        unsupported = [
            self._product_label(item.product)
            for item in requested
            if self._selection_identity(item) not in available_keys
        ]
        if unsupported:
            raise AppError(
                code="COMPETITOR_MATERIAL_PRODUCT_OUT_OF_SCOPE",
                message="只能搜索当前范围内具有准确型号的产品。",
                status_code=422,
                details={"unsupported_products": unsupported},
            )
        if not requested:
            raise AppError(
                code="COMPETITOR_MATERIAL_EXACT_PRODUCT_REQUIRED",
                message="当前范围没有可搜索的准确产品型号。",
                status_code=409,
            )
        available_dimensions = [CompetitorResearchDimension(item) for item in scope.dimensions_json]
        dimensions = payload.dimensions or available_dimensions
        unsupported_dimensions = sorted(set(dimensions) - set(available_dimensions))
        if unsupported_dimensions:
            raise AppError(
                code="COMPETITOR_MATERIAL_DIMENSION_OUT_OF_SCOPE",
                message="只能搜索当前范围已确认的研究维度。",
                status_code=422,
                details={"unsupported_dimensions": [item.value for item in unsupported_dimensions]},
            )
        canonical = {
            "products": [item.model_dump(mode="json") for item in requested],
            "dimensions": [item.value for item in dimensions],
            "scope_updated_at": scope.updated_at.isoformat(),
        }
        scope_hash = sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        region = ResearchBrief.model_validate(project.brief_json).primary_market
        return requested, dimensions, scope_hash, region

    @staticmethod
    def build_query(
        product: ProductReference,
        dimension: CompetitorResearchDimension,
        region: str,
    ) -> str:
        label = " ".join(filter(None, (product.brand, product.model, product.variant)))
        suffixes = {
            CompetitorResearchDimension.OFFICIAL_PRODUCT: (
                "official product specifications features compatibility manual"
            ),
            CompetitorResearchDimension.PRICE_CHANNEL: (
                f"price availability authorized retailer {region}"
            ),
            CompetitorResearchDimension.USER_REVIEW: (
                "user reviews owner feedback problems experience"
            ),
        }
        return f"{label} {suffixes[dimension]}"[:500]

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
    def _resolve_candidates(
        discovery: CompetitorMaterialDiscoveryModel,
        candidate_ids: list[str],
    ) -> list[_CandidateSelection]:
        candidates: dict[str, _CandidateSelection] = {}
        for item in discovery.items:
            for raw in item.search_run.candidates_json:
                candidate = SearchDiscoveryCandidate.model_validate(raw)
                normalized_url = normalize_public_url(str(candidate.normalized_source_url))
                hostname = (urlsplit(normalized_url).hostname or "").casefold()
                if hostname != candidate.source_domain.casefold():
                    raise AppError(
                        code="COMPETITOR_MATERIAL_CANDIDATE_INVALID",
                        message="搜索候选的域名与安全规范化 URL 不一致。",
                        status_code=409,
                        details={"candidate_id": candidate.candidate_id},
                    )
                candidates[candidate.candidate_id] = _CandidateSelection(
                    item=item, candidate=candidate, normalized_url=normalized_url
                )
        unsupported = sorted(set(candidate_ids) - set(candidates))
        if unsupported:
            raise AppError(
                code="COMPETITOR_MATERIAL_CANDIDATE_NOT_FOUND",
                message="只能选择当前资料发现批次中的候选来源。",
                status_code=422,
                details={"unsupported_candidate_ids": unsupported},
            )
        return [candidates[item] for item in candidate_ids]

    async def _source_asset(
        self,
        repository: CompetitorMaterialDiscoveryRepository,
        project_id: str,
        discovery_id: str,
        payload: CompetitorMaterialDecisionCreate,
        selection: _CandidateSelection,
        now: datetime,
    ) -> tuple[SourceAssetModel, bool, str | None]:
        content_hash = source_url_hash(selection.normalized_url)
        existing = await repository.get_source_by_hash(project_id, content_hash)
        if existing is not None and existing.status == SourceAssetStatus.READY.value:
            return existing, False, None
        source_asset_id = existing.source_asset_id if existing else f"source_{uuid4().hex[:16]}"
        collection_job_id = f"collect_{uuid4().hex[:16]}"
        product = ProductReference.model_validate(selection.item.product_json)
        job = CollectionJobModel(
            collection_job_id=collection_job_id,
            project_id=project_id,
            task_id="competitor_material_discovery",
            source_url=selection.normalized_url,
            source_type=SourceMediaCategory.WEBPAGE.value,
            status=CollectionJobStatus.QUEUED.value,
            attempt_count=0,
            result_json={
                "source_asset_id": source_asset_id,
                "material_discovery_id": discovery_id,
                "material_discovery_item_id": selection.item.material_discovery_item_id,
                "candidate_id": selection.candidate.candidate_id,
                "product_role": selection.item.product_role,
                "product": selection.item.product_json,
                "dimension": selection.item.dimension,
            },
            created_at=now,
            updated_at=now,
        )
        await repository.add_collection_job(job)
        display_name = f"{self._product_label(product)} — {selection.candidate.title}"[:255]
        purpose = (
            f"Competitor {selection.item.dimension} source for {self._product_label(product)}. "
            f"{payload.reason}"
        )[:500]
        if existing:
            existing.collection_job_id = collection_job_id
            existing.status = SourceAssetStatus.READY.value
            existing.display_name = display_name
            existing.source_url = selection.normalized_url
            existing.normalized_source_url = selection.normalized_url
            existing.authorization_basis = SourceAuthorizationBasis.PUBLICLY_AVAILABLE.value
            existing.authorization_confirmed_at = now
            existing.authorized_by = payload.actor
            existing.purpose = purpose
            existing.updated_at = now
            existing.deleted_at = None
            return existing, False, "source_asset_restored"
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
            authorization_basis=SourceAuthorizationBasis.PUBLICLY_AVAILABLE.value,
            authorization_confirmed_at=now,
            authorized_by=payload.actor,
            purpose=purpose,
            created_at=now,
            updated_at=now,
        )
        await repository.add_source_asset(source_asset)
        return source_asset, True, "source_asset_created"

    @classmethod
    def _to_discovery(
        cls, model: CompetitorMaterialDiscoveryModel
    ) -> CompetitorMaterialDiscovery:
        items = sorted(
            model.items,
            key=lambda item: (item.product_role, item.product_identity, item.dimension),
        )
        schemas = [
            CompetitorMaterialDiscoveryItem(
                material_discovery_item_id=item.material_discovery_item_id,
                product_role=ProductRole(item.product_role),
                product=ProductReference.model_validate(item.product_json),
                dimension=CompetitorResearchDimension(item.dimension),
                query=item.query,
                search_run=SearchDiscoveryService._to_schema(item.search_run),
            )
            for item in items
        ]
        return CompetitorMaterialDiscovery(
            material_discovery_id=model.material_discovery_id,
            project_id=model.project_id,
            status=CompetitorMaterialDiscoveryStatus(model.status),
            provider_id=model.provider_id,
            max_results_per_query=model.max_results_per_query,
            products=[
                CompetitorMaterialProductSelection.model_validate(item)
                for item in model.products_json
            ],
            dimensions=[CompetitorResearchDimension(item) for item in model.dimensions_json],
            scope_hash=model.scope_hash,
            item_count=len(schemas),
            completed_item_count=sum(
                item.search_run.status == SearchDiscoveryRunStatus.SUCCEEDED.value for item in items
            ),
            candidate_count=sum(item.search_run.result_count for item in items),
            items=schemas,
            decision=cls._to_decision(model.decision) if model.decision else None,
            requested_by=model.requested_by,
            purpose=model.purpose,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )

    @classmethod
    def _to_decision(cls, model: CompetitorMaterialDecisionModel) -> CompetitorMaterialDecision:
        return CompetitorMaterialDecision(
            material_decision_id=model.material_decision_id,
            project_id=model.project_id,
            material_discovery_id=model.material_discovery_id,
            action=CompetitorMaterialDecisionAction(model.action),
            selected_candidate_ids=model.selected_candidate_ids_json,
            authorization_basis=(
                SourceAuthorizationBasis.PUBLICLY_AVAILABLE if model.authorization_basis else None
            ),
            authorization_confirmed=model.authorization_confirmed,
            actor=model.actor,
            reason=model.reason,
            selections=[
                CompetitorMaterialSelection(
                    material_selection_id=item.material_selection_id,
                    material_discovery_item_id=item.material_discovery_item_id,
                    search_discovery_run_id=item.search_discovery_run_id,
                    candidate_id=item.candidate_id,
                    product_role=ProductRole(item.product_role),
                    product=ProductReference.model_validate(item.product_json),
                    dimension=CompetitorResearchDimension(item.dimension),
                    candidate=SearchDiscoveryCandidate.model_validate(item.candidate_json),
                    source_asset=cls._source_schema(item.source_asset),
                    source_asset_created=item.source_asset_created,
                )
                for item in sorted(model.selections, key=lambda item: item.candidate_id)
            ],
            created_at=model.created_at,
        )

    @staticmethod
    def _source_schema(model: SourceAssetModel) -> SourceAsset:
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
    def _assert_idempotent(
        model: CompetitorMaterialDecisionModel,
        payload: CompetitorMaterialDecisionCreate,
    ) -> None:
        if (
            model.action != payload.action.value
            or model.selected_candidate_ids_json != payload.selected_candidate_ids
            or model.actor != payload.actor
            or model.reason != payload.reason
        ):
            raise AppError(
                code="COMPETITOR_MATERIAL_DECISION_CONFLICT",
                message="该资料发现批次已经保存了不同的 Gate 决定。",
                status_code=409,
            )

    @staticmethod
    def _selection_identity(item: CompetitorMaterialProductSelection) -> tuple[str, str, str, str]:
        product = item.product
        return (
            item.product_role.value,
            product.brand.strip().casefold(),
            (product.model or "").strip().casefold(),
            (product.variant or "").strip().casefold(),
        )

    @staticmethod
    def _identity_string(product: ProductReference) -> str:
        return "|".join(
            (
                product.brand.strip().casefold(),
                (product.model or "").strip().casefold(),
                (product.variant or "").strip().casefold(),
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
    def _not_found(material_discovery_id: str) -> AppError:
        return AppError(
            code="COMPETITOR_MATERIAL_DISCOVERY_NOT_FOUND",
            message="竞品资料发现批次不存在或不属于当前项目。",
            status_code=404,
            details={"material_discovery_id": material_discovery_id},
        )
