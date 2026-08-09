"""竞品研究主管：拆分三类 A2A 证据任务并确定性聚合专家交付物。"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from app.application.runtime import AgentInvocation, RuntimeErrorCode, RuntimeGatewayError
from app.integrations.a2a import (
    A2ATaskStatus,
    CompetitorA2ABatchError,
    CompetitorA2AGateway,
    CompetitorSpecialistType,
    EvidenceRequest,
    SpecialistTaskResult,
)
from app.workflows.contracts import (
    ResearchAgentType,
    ResearchArtifact,
    ResearchTaskStatus,
)


class CompetitorA2ASupervisorAdapter:
    """不调用模型、不生成事实，只负责拆分、分发和聚合。"""

    adapter_type = "competitor-a2a-supervisor"

    def __init__(self, gateway: CompetitorA2AGateway) -> None:
        self.gateway = gateway

    async def execute(self, invocation: AgentInvocation) -> ResearchArtifact:
        if invocation.task.agent_type is not ResearchAgentType.COMPETITOR_RESEARCH:
            raise ValueError("competitor supervisor received an incompatible task")
        requests = build_competitor_evidence_requests(invocation)
        try:
            results = await self.gateway.execute_all(
                parent_agent_run_id=invocation.agent_run_id,
                trace_id=invocation.trace_id,
                requests=requests,
                context=invocation.context,
                cancellation_token=invocation.cancellation_token,
            )
        except CompetitorA2ABatchError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ADAPTER_FAILED,
                "One or more competitor specialists failed; successful tasks are reusable.",
                agent_run_id=invocation.agent_run_id,
                retryable=any(failure.retryable for failure in exc.failures),
                details={
                    "a2a_failures": [
                        {
                            "a2a_task_id": failure.a2a_task_id,
                            "specialist_type": failure.specialist_type,
                            "error_code": failure.code,
                            "retryable": failure.retryable,
                        }
                        for failure in exc.failures
                    ]
                },
            ) from exc
        return _aggregate_results(invocation, results)


def build_competitor_evidence_requests(
    invocation: AgentInvocation,
) -> list[EvidenceRequest]:
    """把主管任务稳定拆成三个检索方向，不在这里植入业务结论。"""

    task = invocation.task
    brief = invocation.context.brief
    product_scope = _product_scope(task.scope, brief.category)
    definitions = (
        (
            CompetitorSpecialistType.OFFICIAL_PRODUCT,
            [
                "Identify in-scope product capabilities and specifications supported by "
                "authorized official sources.",
                "Record unknown specifications instead of inferring them.",
            ],
            ["official_product_page", "official_document"],
            ["vendor_claim", "fact"],
            1,
        ),
        (
            CompetitorSpecialistType.PRICE_CHANNEL,
            [
                "Identify prices, availability and channel facts supported by authorized "
                "store or channel sources.",
                "Keep region, timestamp and product variant boundaries explicit.",
            ],
            ["official_store_page", "authorized_channel_page"],
            [
                "price_observation",
                "channel_availability",
                "seller_information",
                "promotion",
            ],
            task.evidence_rules.minimum_independent_domains,
        ),
        (
            CompetitorSpecialistType.USER_REVIEW,
            [
                "Identify recurring user opinions in the authorized review evidence.",
                "Keep sample limitations and contradictory opinions explicit.",
            ],
            ["authorized_user_review", "authorized_research_file"],
            ["user_opinion"],
            task.evidence_rules.minimum_independent_domains,
        ),
    )
    return [
        EvidenceRequest(
            request_id=_request_id(task.task_id, specialist_type),
            project_id=task.project_id,
            parent_task_id=task.task_id,
            specialist_type=specialist_type,
            research_questions=questions,
            product_scope=product_scope,
            region=brief.region,
            evidence_types=evidence_types,
            allowed_claim_types=claim_types,
            minimum_independent_domains=minimum_independent_domains,
            max_evidence_items=min(task.budget.max_pages or 30, 200),
        )
        for (
            specialist_type,
            questions,
            evidence_types,
            claim_types,
            minimum_independent_domains,
        ) in definitions
    ]


def _aggregate_results(
    invocation: AgentInvocation,
    results: list[SpecialistTaskResult],
) -> ResearchArtifact:
    artifacts = [result.artifact for result in results if result.artifact is not None]
    blocked = [result for result in results if result.status is A2ATaskStatus.BLOCKED]
    if results and all(result.status is A2ATaskStatus.BLOCKED for result in results):
        status = ResearchTaskStatus.BLOCKED
    elif blocked or any(artifact.status is ResearchTaskStatus.PARTIAL for artifact in artifacts):
        status = ResearchTaskStatus.PARTIAL
    else:
        status = ResearchTaskStatus.COMPLETED

    evidence_ids = sorted(
        {evidence_id for artifact in artifacts for evidence_id in artifact.evidence_ids}
    )
    unknowns = _unique(
        [unknown for artifact in artifacts for unknown in artifact.unknowns]
        + [f"{result.request.specialist_type.value} specialist is not bound" for result in blocked]
    )
    errors = _unique(
        [error for artifact in artifacts for error in artifact.errors]
        + [result.error_message for result in blocked if result.error_message]
    )
    quality_score = (
        round(sum(artifact.quality_score for artifact in artifacts) / len(artifacts), 2)
        if artifacts
        else 0
    )
    return ResearchArtifact(
        artifact_id=f"artifact_pending_{invocation.agent_run_id}",
        task_id=invocation.task.task_id,
        artifact_type=ResearchAgentType.COMPETITOR_RESEARCH,
        schema_version="1.0",
        status=status,
        payload={
            "schema_name": "competitor_a2a_foundation",
            "supervisor_mode": "deterministic_dispatch_and_aggregation",
            "evidence_requests": [result.request.model_dump(mode="json") for result in results],
            "specialist_tasks": [
                {
                    "a2a_task_id": result.a2a_task_id,
                    "specialist_type": result.request.specialist_type,
                    "status": result.status,
                    "attempt_number": result.attempt_number,
                    "reused": result.reused,
                    "error_code": result.error_code,
                }
                for result in results
            ],
            "specialist_outputs": [artifact.model_dump(mode="json") for artifact in artifacts],
            "synthesis_status": "not_implemented_in_foundation",
        },
        evidence_ids=evidence_ids,
        unknowns=unknowns,
        quality_score=quality_score,
        errors=errors,
    )


def _product_scope(scope: dict[str, object], fallback_category: str) -> list[str]:
    values: list[str] = []
    for key in (
        "target_product",
        "target_products",
        "competitors",
        "products",
        "product_scope",
        "selected_products",
    ):
        raw = scope.get(key)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    model = item.get("model")
                    if isinstance(model, str) and model.strip():
                        values.append(model.strip())
    return _unique(values) or [fallback_category]


def _request_id(task_id: str, specialist_type: CompetitorSpecialistType) -> str:
    content = f"{task_id}:{specialist_type}"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"request_{specialist_type.value}_{digest[:16]}"


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
