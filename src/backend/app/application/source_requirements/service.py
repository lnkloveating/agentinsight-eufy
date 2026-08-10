"""不调用模型的资料范围保存与准备度评估服务。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.application.events import ProjectEventBroker
from app.core.errors import AppError
from app.infrastructure.database.models import (
    CollectionJobModel,
    CompetitorMaterialSelectionModel,
    CompetitorSourceOnboardingItemModel,
    EvidenceModel,
    ProjectEventModel,
    SourceAssetModel,
    SourceRequirementScopeModel,
    SourceRoutingModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.infrastructure.database.source_requirement_repository import (
    SourceRequirementRepository,
)
from app.schemas.evidence import EvidenceClaimType
from app.schemas.project import ResearchBrief
from app.schemas.source_requirements import (
    CompetitorResearchDimension,
    ProductReference,
    ProductRole,
    SourceReadinessStatus,
    SourceRequirementAssessment,
    SourceRequirementItem,
    SourceRequirementScope,
    SourceRequirementScopeUpdate,
    SourceRequirementSeverity,
    SourceRequirementStatus,
)
from app.schemas.source_routing import SourceRouteTarget


@dataclass(frozen=True)
class _MaterialSpec:
    dimension: CompetitorResearchDimension
    title: str
    routes: frozenset[SourceRouteTarget]
    claim_types: frozenset[EvidenceClaimType]
    minimum_independent_sources: int
    source_advice: str


@dataclass(frozen=True)
class _AssessmentSnapshot:
    brief_json: dict[str, object]
    scope: SourceRequirementScopeModel | None
    assets: tuple[SourceAssetModel, ...]
    routings: tuple[SourceRoutingModel, ...]
    evidence: tuple[EvidenceModel, ...]
    jobs: tuple[CollectionJobModel, ...]
    competitor_source_lineage: tuple[CompetitorSourceOnboardingItemModel, ...]
    competitor_material_lineage: tuple[CompetitorMaterialSelectionModel, ...]


_MATERIAL_SPECS = {
    CompetitorResearchDimension.OFFICIAL_PRODUCT: _MaterialSpec(
        dimension=CompetitorResearchDimension.OFFICIAL_PRODUCT,
        title="官方产品资料",
        routes=frozenset({SourceRouteTarget.OFFICIAL_PRODUCT}),
        claim_types=frozenset(
            {
                EvidenceClaimType.VENDOR_CLAIM,
                EvidenceClaimType.FACT,
                EvidenceClaimType.PRODUCT_IDENTITY,
                EvidenceClaimType.CAPABILITY,
                EvidenceClaimType.SPECIFICATION,
                EvidenceClaimType.COMPATIBILITY,
                EvidenceClaimType.LIMITATION,
            }
        ),
        minimum_independent_sources=1,
        source_advice="补充该型号的官方产品页、官方说明书或企业授权产品资料。",
    ),
    CompetitorResearchDimension.PRICE_CHANNEL: _MaterialSpec(
        dimension=CompetitorResearchDimension.PRICE_CHANNEL,
        title="价格渠道资料",
        routes=frozenset({SourceRouteTarget.PRICE_CHANNEL}),
        claim_types=frozenset(
            {
                EvidenceClaimType.PRICE_OBSERVATION,
                EvidenceClaimType.CHANNEL_AVAILABILITY,
                EvidenceClaimType.SELLER_INFORMATION,
                EvidenceClaimType.PROMOTION,
            }
        ),
        minimum_independent_sources=1,
        source_advice="补充目标地区的官方商城或授权零售页，并保留币种、型号和观察时间。",
    ),
    CompetitorResearchDimension.USER_REVIEW: _MaterialSpec(
        dimension=CompetitorResearchDimension.USER_REVIEW,
        title="用户评价资料",
        routes=frozenset(
            {
                SourceRouteTarget.USER_REVIEW,
                SourceRouteTarget.MEDIA_REVIEW,
            }
        ),
        claim_types=frozenset({EvidenceClaimType.USER_OPINION}),
        minimum_independent_sources=1,
        source_advice="补充带型号、评价时间和样本边界的授权评价页面或研究文件。",
    ),
}


class SourceRequirementService:
    def __init__(
        self,
        database: Database,
        event_broker: ProjectEventBroker,
        trace_id: str,
    ) -> None:
        self.database = database
        self.event_broker = event_broker
        self.trace_id = trace_id

    async def get(self, project_id: str) -> SourceRequirementAssessment:
        return self._evaluate(project_id, await self._load_snapshot(project_id))

    async def update_scope(
        self,
        project_id: str,
        payload: SourceRequirementScopeUpdate,
    ) -> SourceRequirementAssessment:
        now = datetime.now(UTC)
        async with self.database.session() as session:
            repository = SourceRequirementRepository(session)
            if await repository.get_project(project_id) is None:
                raise self._project_not_found(project_id)
            model = await repository.get_scope(project_id)
            if model is None:
                model = SourceRequirementScopeModel(
                    source_requirement_scope_id=f"requirement_scope_{uuid4().hex[:12]}",
                    project_id=project_id,
                    target_products_json=self._product_json(payload.target_products),
                    competitors_json=self._product_json(payload.competitors),
                    dimensions_json=[item.value for item in payload.dimensions],
                    updated_by=payload.actor,
                    update_reason=payload.reason,
                    created_at=now,
                    updated_at=now,
                )
                await repository.add_scope(model)
            else:
                model.target_products_json = self._product_json(payload.target_products)
                model.competitors_json = self._product_json(payload.competitors)
                model.dimensions_json = [item.value for item in payload.dimensions]
                model.updated_by = payload.actor
                model.update_reason = payload.reason
                model.updated_at = now
            await ProjectRepository(session).add_event(
                ProjectEventModel(
                    event_id=f"evt_{uuid4().hex[:16]}",
                    project_id=project_id,
                    sequence_number=0,
                    event_type="source_requirement_scope_updated",
                    data_json={
                        "target_product_count": len(payload.target_products),
                        "competitor_count": len(payload.competitors),
                        "dimensions": [item.value for item in payload.dimensions],
                        "actor": payload.actor,
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
        await self.event_broker.notify(project_id)
        return await self.get(project_id)

    async def _load_snapshot(self, project_id: str) -> _AssessmentSnapshot:
        async with self.database.session() as session:
            repository = SourceRequirementRepository(session)
            project = await repository.get_project(project_id)
            if project is None:
                raise self._project_not_found(project_id)
            return _AssessmentSnapshot(
                brief_json=dict(project.brief_json),
                scope=await repository.get_scope(project_id),
                assets=tuple(await repository.list_assets(project_id)),
                routings=tuple(await repository.list_routings(project_id)),
                evidence=tuple(await repository.list_eligible_evidence(project_id)),
                jobs=tuple(await repository.list_collection_jobs(project_id)),
                competitor_source_lineage=tuple(
                    await repository.list_competitor_source_lineage(project_id)
                ),
                competitor_material_lineage=tuple(
                    await repository.list_competitor_material_lineage(project_id)
                ),
            )

    def _evaluate(
        self,
        project_id: str,
        snapshot: _AssessmentSnapshot,
    ) -> SourceRequirementAssessment:
        scope = self._to_scope(snapshot.scope) if snapshot.scope is not None else None
        target_products = scope.target_products if scope is not None else []
        competitors = scope.competitors if scope is not None else []
        dimensions = scope.dimensions if scope is not None else []

        requirements = [
            self._scope_requirement(ProductRole.TARGET, target_products),
            self._scope_requirement(ProductRole.COMPETITOR, competitors),
        ]
        lineage_by_asset = self._lineage_products_by_asset(
            (*snapshot.competitor_source_lineage, *snapshot.competitor_material_lineage)
        )
        for role, products in (
            (ProductRole.TARGET, target_products),
            (ProductRole.COMPETITOR, competitors),
        ):
            for product in products:
                if product.model is None:
                    continue
                for dimension in dimensions:
                    requirements.append(
                        self._material_requirement(
                            role,
                            product,
                            _MATERIAL_SPECS[dimension],
                            snapshot,
                            lineage_by_asset,
                        )
                    )

        required = [
            item for item in requirements if item.severity is SourceRequirementSeverity.REQUIRED
        ]
        satisfied_count = sum(item.status is SourceRequirementStatus.SATISFIED for item in required)
        structural_ready = all(
            item.status is SourceRequirementStatus.SATISFIED for item in requirements[:2]
        )
        if not structural_ready:
            status = SourceReadinessStatus.BLOCKED
        elif satisfied_count == len(required):
            status = SourceReadinessStatus.READY
        else:
            status = SourceReadinessStatus.PARTIAL

        assigned_asset_ids = {
            source_asset_id
            for item in requirements
            for source_asset_id in item.matched_source_asset_ids
        }
        relevant_routes = {
            route.value for dimension in dimensions for route in _MATERIAL_SPECS[dimension].routes
        }
        routed_asset_ids = {
            routing.source_asset_id
            for routing in snapshot.routings
            if relevant_routes.intersection(routing.confirmed_routes_json)
        }
        missing_actions = self._unique(
            action
            for item in requirements
            if item.status is not SourceRequirementStatus.SATISFIED
            for action in item.recommended_actions
        )
        return SourceRequirementAssessment(
            project_id=project_id,
            status=status,
            region=ResearchBrief.model_validate(snapshot.brief_json).primary_market,
            scope=scope,
            requirements=requirements,
            required_count=len(required),
            satisfied_required_count=satisfied_count,
            missing_required_count=len(required) - satisfied_count,
            unassigned_source_asset_ids=sorted(routed_asset_ids - assigned_asset_ids),
            missing_actions=missing_actions,
            input_hash=self._input_hash(snapshot),
            evaluated_at=datetime.now(UTC),
        )

    def _scope_requirement(
        self,
        role: ProductRole,
        products: list[ProductReference],
    ) -> SourceRequirementItem:
        label = "目标产品" if role is ProductRole.TARGET else "竞品"
        missing_models = [product.brand for product in products if product.model is None]
        if not products:
            status = SourceRequirementStatus.MISSING
            reason = f"尚未确认{label}。"
            actions = [f"请确认至少一个{label}的品牌和准确型号。"]
        elif missing_models:
            status = SourceRequirementStatus.PARTIAL
            reason = f"以下{label}缺少准确型号：{'、'.join(missing_models)}。"
            actions = [f"请补充{'、'.join(missing_models)}的准确型号或代际。"]
        else:
            status = SourceRequirementStatus.SATISFIED
            reason = f"已确认 {len(products)} 个{label}及其准确型号。"
            actions = []
        return SourceRequirementItem(
            requirement_id=f"requirement_scope_{role.value}",
            requirement_key=f"scope.{role.value}_products",
            title=f"确认{label}范围",
            severity=SourceRequirementSeverity.REQUIRED,
            status=status,
            product_role=role,
            reason=reason,
            recommended_actions=actions,
        )

    def _material_requirement(
        self,
        role: ProductRole,
        product: ProductReference,
        spec: _MaterialSpec,
        snapshot: _AssessmentSnapshot,
        lineage_by_asset: dict[str, tuple[ProductReference, ...]],
    ) -> SourceRequirementItem:
        routed_by_asset = {
            routing.source_asset_id: set(routing.confirmed_routes_json)
            for routing in snapshot.routings
        }
        accepted_route_values = {route.value for route in spec.routes}
        accepted_claim_values = {claim.value for claim in spec.claim_types}
        matching_evidence = [
            evidence
            for evidence in snapshot.evidence
            if evidence.source_asset_id is not None
            and accepted_route_values.intersection(
                routed_by_asset.get(evidence.source_asset_id, set())
            )
            and evidence.claim_type in accepted_claim_values
            and self._evidence_matches_product(evidence, product)
            and self._evidence_matches_region(evidence, spec, snapshot.brief_json)
        ]
        matched_asset_ids = sorted(
            {
                evidence.source_asset_id
                for evidence in matching_evidence
                if evidence.source_asset_id is not None
            }
        )
        independent_sources = {
            (
                f"domain:{evidence.source_domain.casefold()}"
                if evidence.source_domain
                else f"asset:{evidence.source_asset_id}"
            )
            for evidence in matching_evidence
        }
        detected_assets = [
            asset
            for asset in snapshot.assets
            if self._asset_matches_product(asset, product, lineage_by_asset)
            and (
                accepted_route_values.intersection(
                    routed_by_asset.get(asset.source_asset_id, set())
                )
                or asset.source_asset_id not in routed_by_asset
            )
        ]
        detected_asset_ids = sorted({asset.source_asset_id for asset in detected_assets})
        jobs_by_id = {job.collection_job_id: job for job in snapshot.jobs}
        terminal_failures = {"blocked", "failed", "cancelled"}
        detected_jobs = [jobs_by_id.get(asset.collection_job_id) for asset in detected_assets]

        if len(independent_sources) >= spec.minimum_independent_sources:
            status = SourceRequirementStatus.SATISFIED
            reason = (
                f"已找到 {len(matching_evidence)} 条合格 Evidence，覆盖 "
                f"{len(independent_sources)} 个独立来源。"
            )
            actions: list[str] = []
        elif detected_jobs and all(
            job is not None and job.status in terminal_failures for job in detected_jobs
        ):
            status = SourceRequirementStatus.BLOCKED
            reason = "已提交的相关资料均处理失败或被阻止，当前不能形成合格 Evidence。"
            actions = ["请查看资料处理错误并重试，或替换为可访问且已授权的资料。"]
        elif matching_evidence or detected_asset_ids:
            status = SourceRequirementStatus.PARTIAL
            reason = "已检测到相关资料，但路由确认、Evidence 审核或来源覆盖尚未完成。"
            actions = ["请完成资料解析、路由确认，并将可复核片段审核为对应产品的 Evidence。"]
        else:
            status = SourceRequirementStatus.MISSING
            reason = "没有找到与该准确型号关联的已授权资料或合格 Evidence。"
            actions = [spec.source_advice]

        requirement_key = f"material.{spec.dimension.value}.{role.value}"
        identity = self._product_key(product)
        return SourceRequirementItem(
            requirement_id=f"requirement_{hashlib.sha256(f'{requirement_key}:{identity}'.encode()).hexdigest()[:16]}",
            requirement_key=requirement_key,
            title=f"{self._product_label(product)}：{spec.title}",
            severity=SourceRequirementSeverity.REQUIRED,
            status=status,
            product_role=role,
            product=product,
            dimension=spec.dimension,
            accepted_routes=sorted(spec.routes, key=lambda item: item.value),
            accepted_claim_types=sorted(spec.claim_types, key=lambda item: item.value),
            minimum_independent_sources=spec.minimum_independent_sources,
            detected_source_asset_ids=detected_asset_ids,
            matched_source_asset_ids=matched_asset_ids,
            matched_evidence_ids=[item.evidence_id for item in matching_evidence],
            reason=reason,
            recommended_actions=actions,
        )

    @staticmethod
    def _evidence_matches_product(
        evidence: EvidenceModel,
        product: ProductReference,
    ) -> bool:
        if not evidence.product:
            return False
        normalized = SourceRequirementService._normalize(evidence.product)
        aliases = {
            SourceRequirementService._normalize(product.model or ""),
            SourceRequirementService._normalize(
                " ".join(filter(None, (product.model, product.variant)))
            ),
            SourceRequirementService._normalize(
                " ".join(filter(None, (product.brand, product.model, product.variant)))
            ),
        }
        aliases.discard("")
        return normalized in aliases

    @classmethod
    def _asset_matches_product(
        cls,
        asset: SourceAssetModel,
        product: ProductReference,
        lineage_by_asset: dict[str, tuple[ProductReference, ...]],
    ) -> bool:
        if product.model is None:
            return False
        lineage_products = lineage_by_asset.get(asset.source_asset_id)
        if lineage_products is not None:
            expected_identity = cls._product_key(product)
            return any(cls._product_key(item) == expected_identity for item in lineage_products)
        haystack = cls._normalize(
            " ".join(filter(None, (asset.display_name, asset.purpose, asset.source_url or "")))
        )
        return (
            cls._normalize(product.brand) in haystack
            and cls._normalize(product.model) in haystack
        )

    @staticmethod
    def _lineage_products_by_asset(
        lineages: Iterable[
            CompetitorSourceOnboardingItemModel | CompetitorMaterialSelectionModel
        ],
    ) -> dict[str, tuple[ProductReference, ...]]:
        products: dict[str, list[ProductReference]] = {}
        for lineage in lineages:
            bucket = products.setdefault(lineage.source_asset_id, [])
            try:
                product = ProductReference.model_validate(lineage.product_json)
            except ValueError:
                # 有血缘但记录无效时保持“不匹配”，不能回退到模糊文本并错误归属。
                continue
            if product not in bucket:
                bucket.append(product)
        return {source_asset_id: tuple(items) for source_asset_id, items in products.items()}

    @staticmethod
    def _evidence_matches_region(
        evidence: EvidenceModel,
        spec: _MaterialSpec,
        brief_json: dict[str, object],
    ) -> bool:
        if spec.dimension is not CompetitorResearchDimension.PRICE_CHANNEL:
            return True
        region = ResearchBrief.model_validate(brief_json).primary_market
        if not evidence.region:
            return False
        return SourceRequirementService._normalize(evidence.region) == (
            SourceRequirementService._normalize(region)
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^\w]+", " ", value.casefold(), flags=re.UNICODE).strip()

    @staticmethod
    def _product_label(product: ProductReference) -> str:
        return " ".join(filter(None, (product.brand, product.model, product.variant)))

    @classmethod
    def _product_key(cls, product: ProductReference) -> str:
        return cls._normalize(cls._product_label(product))

    @staticmethod
    def _product_json(products: list[ProductReference]) -> list[dict[str, str | None]]:
        return [product.model_dump(mode="json") for product in products]

    @staticmethod
    def _to_scope(model: SourceRequirementScopeModel) -> SourceRequirementScope:
        return SourceRequirementScope(
            target_products=[
                ProductReference.model_validate(item) for item in model.target_products_json
            ],
            competitors=[ProductReference.model_validate(item) for item in model.competitors_json],
            dimensions=[CompetitorResearchDimension(item) for item in model.dimensions_json],
            updated_by=model.updated_by,
            update_reason=model.update_reason,
            updated_at=model.updated_at,
        )

    @classmethod
    def _input_hash(cls, snapshot: _AssessmentSnapshot) -> str:
        payload = {
            "brief": snapshot.brief_json,
            "scope": (
                {
                    "target_products": snapshot.scope.target_products_json,
                    "competitors": snapshot.scope.competitors_json,
                    "dimensions": snapshot.scope.dimensions_json,
                    "updated_at": snapshot.scope.updated_at.isoformat(),
                }
                if snapshot.scope is not None
                else None
            ),
            "assets": [
                {
                    "id": item.source_asset_id,
                    "status": item.status,
                    "hash": item.content_hash,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in snapshot.assets
            ],
            "routings": [
                {
                    "source_asset_id": item.source_asset_id,
                    "routes": item.confirmed_routes_json,
                    "claim_types": item.confirmed_claim_types_json,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in snapshot.routings
            ],
            "evidence": [
                {
                    "id": item.evidence_id,
                    "source_asset_id": item.source_asset_id,
                    "claim_type": item.claim_type,
                    "product": item.product,
                    "region": item.region,
                    "status": item.status,
                    "content_hash": item.content_hash,
                }
                for item in snapshot.evidence
            ],
            "jobs": [
                {
                    "id": item.collection_job_id,
                    "status": item.status,
                    "attempt_count": item.attempt_count,
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in snapshot.jobs
            ],
            "competitor_lineage": [
                {
                    "source_asset_id": item.source_asset_id,
                    "product": item.product_json,
                }
                for item in snapshot.competitor_source_lineage
            ]
            + [
                {
                    "source_asset_id": item.source_asset_id,
                    "product": item.product_json,
                }
                for item in snapshot.competitor_material_lineage
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))

    @staticmethod
    def _project_not_found(project_id: str) -> AppError:
        return AppError(
            code="PROJECT_NOT_FOUND",
            message="研究项目不存在。",
            status_code=404,
            details={"project_id": project_id},
        )
