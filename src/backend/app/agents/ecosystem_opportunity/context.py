"""Build the evidence and Device Capability Graph context for ecosystem opportunities."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from app.application.evidence import EvidenceRetrievalService
from app.infrastructure.database.device_capability_repository import (
    DeviceCapabilityRepository,
)
from app.infrastructure.database.session import Database
from app.schemas.evidence import EvidenceStatus
from app.schemas.evidence_retrieval import EvidenceRetrievalQuery
from app.workflows.contracts import AgentEvidenceContext, ResearchHandoff

_ELIGIBLE_EVIDENCE_STATUSES = {
    EvidenceStatus.VERIFIED.value,
    EvidenceStatus.PARTIALLY_VERIFIED.value,
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceCapabilityFact(StrictModel):
    """One currently citable capability claim; it is not a proposed capability."""

    catalog_device_id: str = Field(min_length=1, max_length=80)
    manufacturer: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    lifecycle_status: str = Field(min_length=1, max_length=40)
    capability_key: str = Field(min_length=1, max_length=80)
    capability_name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=40)
    assertion: str = Field(min_length=1, max_length=40)
    availability: str = Field(min_length=1, max_length=40)
    confidence: float = Field(ge=0, le=1)
    data_scope: str = Field(min_length=1, max_length=40)
    authorization_required: bool
    offline_support: str = Field(min_length=1, max_length=40)
    fallback: str | None = Field(default=None, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=60)


class DeviceCapabilityGraphContext(StrictModel):
    """Read-only projection of verified catalog claims available to this model call."""

    facts: list[DeviceCapabilityFact] = Field(default_factory=list, max_length=300)
    included_device_count: int = Field(ge=0)
    included_claim_count: int = Field(ge=0)
    omitted_claim_count: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list, max_length=500)
    issues: list[str] = Field(default_factory=list, max_length=100)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class EcosystemOpportunityContextBundle(StrictModel):
    evidence_context: AgentEvidenceContext
    capability_graph: DeviceCapabilityGraphContext


class EcosystemOpportunityContextBuilder:
    def __init__(
        self,
        database: Database,
        *,
        max_items: int,
        max_excerpt_chars: int,
        max_total_chars: int,
    ) -> None:
        if max_items <= 0 or max_excerpt_chars <= 0 or max_total_chars <= 0:
            raise ValueError("ecosystem opportunity evidence limits must be positive")
        self.database = database
        self.retrieval = EvidenceRetrievalService(database)
        self.max_items = max_items
        self.max_excerpt_chars = max_excerpt_chars
        self.max_total_chars = max_total_chars

    async def build(
        self, project_id: str, handoff: ResearchHandoff
    ) -> EcosystemOpportunityContextBundle:
        raw_facts, raw_omitted, graph_issues = await self._load_graph(project_id)
        graph_evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for fact in raw_facts
                for evidence_id in fact.evidence_ids
            )
        )
        requested = list(
            dict.fromkeys(
                [
                    *handoff.merged_evidence_ids,
                    *handoff.supplemental_evidence_ids,
                    *graph_evidence_ids,
                ]
            )
        )[:500]
        if requested:
            result = await self.retrieval.retrieve(
                project_id,
                EvidenceRetrievalQuery(
                    consumer="ecosystem_opportunity",
                    evidence_ids=requested,
                    max_items=min(self.max_items, len(requested)),
                    max_excerpt_chars=self.max_excerpt_chars,
                    max_total_chars=self.max_total_chars,
                    candidate_limit=max(self.max_items, len(requested)),
                    diversify_sources=False,
                    preserve_evidence_order=True,
                ),
            )
            evidence_context = result.context
        else:
            evidence_context = self.retrieval.empty_context()

        included_ids = {item.evidence_id for item in evidence_context.items}
        facts = [
            fact for fact in raw_facts if set(fact.evidence_ids).issubset(included_ids)
        ]
        omitted = raw_omitted + len(raw_facts) - len(facts)
        if raw_facts and not facts:
            graph_issues.append("capability_graph_excluded_by_evidence_budget")
        graph = self._graph_context(facts, omitted, graph_issues)
        return EcosystemOpportunityContextBundle(
            evidence_context=evidence_context,
            capability_graph=graph,
        )

    async def _load_graph(
        self, project_id: str
    ) -> tuple[list[DeviceCapabilityFact], int, list[str]]:
        async with self.database.session() as session:
            repository = DeviceCapabilityRepository(session)
            devices = await repository.list_catalog_devices(project_id)
            referenced_ids = {
                evidence_id
                for device in devices
                for evidence_id in (
                    list(device.identity_evidence_ids_json)
                    + [
                        claim_evidence_id
                        for claim in device.capability_claims
                        for claim_evidence_id in claim.evidence_ids_json
                    ]
                )
            }
            evidence = await repository.get_evidence_by_ids(project_id, referenced_ids)
        eligible_ids = {
            item.evidence_id
            for item in evidence
            if item.status in _ELIGIBLE_EVIDENCE_STATUSES
        }
        facts: list[DeviceCapabilityFact] = []
        omitted = 0
        issues: list[str] = []
        for device in devices:
            identity_ids = list(device.identity_evidence_ids_json)
            identity_is_current = bool(identity_ids) and set(identity_ids).issubset(eligible_ids)
            for claim in device.capability_claims:
                evidence_ids = list(dict.fromkeys([*identity_ids, *claim.evidence_ids_json]))
                if not identity_is_current or not set(evidence_ids).issubset(eligible_ids):
                    omitted += 1
                    continue
                if len(facts) >= 300:
                    omitted += 1
                    continue
                facts.append(
                    DeviceCapabilityFact(
                        catalog_device_id=device.catalog_device_id,
                        manufacturer=device.manufacturer,
                        product_name=device.product_name,
                        model=device.model,
                        category=device.category,
                        lifecycle_status=device.lifecycle_status,
                        capability_key=claim.capability_key,
                        capability_name=claim.capability_name,
                        kind=claim.kind,
                        assertion=claim.assertion,
                        availability=claim.availability,
                        confidence=claim.confidence,
                        data_scope=claim.data_scope,
                        authorization_required=claim.authorization_required,
                        offline_support=claim.offline_support,
                        fallback=claim.fallback,
                        evidence_ids=evidence_ids,
                    )
                )
        if not devices:
            issues.append("device_capability_graph_empty")
        elif not facts:
            issues.append("device_capability_graph_has_no_citable_claims")
        if omitted:
            issues.append("device_capability_claims_omitted")
        return facts, omitted, issues

    @staticmethod
    def _graph_context(
        facts: list[DeviceCapabilityFact], omitted: int, issues: list[str]
    ) -> DeviceCapabilityGraphContext:
        evidence_ids = list(
            dict.fromkeys(
                evidence_id for fact in facts for evidence_id in fact.evidence_ids
            )
        )
        canonical = json.dumps(
            [fact.model_dump(mode="json") for fact in facts],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return DeviceCapabilityGraphContext(
            facts=facts,
            included_device_count=len({fact.catalog_device_id for fact in facts}),
            included_claim_count=len(facts),
            omitted_claim_count=omitted,
            evidence_ids=evidence_ids,
            issues=list(dict.fromkeys(issues)),
            context_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
