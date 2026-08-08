"""竞品专家并行执行、审计和失败恢复网关。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import ValidationError

from app.application.events import ProjectEventBroker
from app.application.runtime import (
    CancellationToken,
    RuntimeCancellationError,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.infrastructure.database.a2a_repository import A2ATaskRepository
from app.infrastructure.database.models import A2ATaskModel, ProjectEventModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.integrations.a2a.contracts import (
    A2AErrorCode,
    A2AGatewayError,
    A2ASpecialistInvocation,
    A2ATaskStatus,
    CompetitorA2ABatchError,
    CompetitorSpecialistArtifact,
    CompetitorSpecialistType,
    EvidenceRequest,
    SpecialistTaskResult,
)
from app.integrations.a2a.registry import A2ASpecialistRegistry, SpecialistBinding
from app.workflows.contracts import AgentContext, ResearchTaskStatus


@dataclass(frozen=True)
class _PreparedTask:
    a2a_task_id: str
    attempt_number: int
    artifact: CompetitorSpecialistArtifact | None
    reused: bool


class CompetitorA2AGateway:
    """并行执行三类专家；成功结果可跨主管重试复用。"""

    def __init__(
        self,
        database: Database,
        registry: A2ASpecialistRegistry,
        event_broker: ProjectEventBroker,
        *,
        specialist_timeout_seconds: float = 120,
    ) -> None:
        if specialist_timeout_seconds <= 0:
            raise ValueError("specialist_timeout_seconds must be positive")
        self.database = database
        self.registry = registry
        self.event_broker = event_broker
        self.specialist_timeout_seconds = specialist_timeout_seconds
        self._event_lock = asyncio.Lock()

    async def execute_all(
        self,
        *,
        parent_agent_run_id: str,
        trace_id: str,
        requests: list[EvidenceRequest],
        context: AgentContext,
        cancellation_token: CancellationToken,
    ) -> list[SpecialistTaskResult]:
        self._validate_batch(requests, context)
        tasks = [
            asyncio.create_task(
                self._execute_one(
                    parent_agent_run_id=parent_agent_run_id,
                    trace_id=trace_id,
                    request=request,
                    context=context,
                    cancellation_token=cancellation_token,
                )
            )
            for request in requests
        ]
        try:
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            cancellation_token.cancel()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        failures = [result for result in raw_results if isinstance(result, A2AGatewayError)]
        unexpected = [
            result
            for result in raw_results
            if isinstance(result, BaseException)
            and not isinstance(result, A2AGatewayError)
        ]
        if unexpected:
            raise RuntimeError("unexpected competitor A2A task failure") from unexpected[0]
        if failures:
            raise CompetitorA2ABatchError(failures)
        return [result for result in raw_results if isinstance(result, SpecialistTaskResult)]

    async def _execute_one(
        self,
        *,
        parent_agent_run_id: str,
        trace_id: str,
        request: EvidenceRequest,
        context: AgentContext,
        cancellation_token: CancellationToken,
    ) -> SpecialistTaskResult:
        binding = self.registry.resolve(request.specialist_type)
        input_hash = self._input_hash(request, context)
        prepared = await self._prepare_task(
            parent_agent_run_id=parent_agent_run_id,
            trace_id=trace_id,
            request=request,
            input_hash=input_hash,
            binding=binding,
        )
        if prepared.reused and prepared.artifact is not None:
            return SpecialistTaskResult(
                a2a_task_id=prepared.a2a_task_id,
                request=request,
                status=A2ATaskStatus(prepared.artifact.status),
                artifact=prepared.artifact,
                reused=True,
                attempt_number=prepared.attempt_number,
            )
        if binding is None:
            return SpecialistTaskResult(
                a2a_task_id=prepared.a2a_task_id,
                request=request,
                status=A2ATaskStatus.BLOCKED,
                attempt_number=prepared.attempt_number,
                error_code=A2AErrorCode.SPECIALIST_NOT_BOUND,
                error_message="No executable specialist adapter is bound.",
            )

        invocation = A2ASpecialistInvocation(
            a2a_task_id=prepared.a2a_task_id,
            parent_agent_run_id=parent_agent_run_id,
            trace_id=trace_id,
            attempt_number=prepared.attempt_number,
            request=request,
            context=context,
            cancellation_token=cancellation_token,
        )
        try:
            cancellation_token.raise_if_cancelled()
            async with asyncio.timeout(self.specialist_timeout_seconds):
                raw_artifact = await binding.adapter.execute(invocation)
            cancellation_token.raise_if_cancelled()
            artifact = CompetitorSpecialistArtifact.model_validate(raw_artifact)
            self._validate_artifact(invocation, artifact)
        except TimeoutError as exc:
            error = self._error(
                A2AErrorCode.TIMEOUT,
                prepared.a2a_task_id,
                request.specialist_type,
                "Competitor specialist execution timed out.",
                retryable=True,
            )
            await self._fail_task(request.project_id, prepared.a2a_task_id, trace_id, error)
            raise error from exc
        except (asyncio.CancelledError, RuntimeCancellationError) as exc:
            error = self._error(
                A2AErrorCode.CANCELLED,
                prepared.a2a_task_id,
                request.specialist_type,
                "Competitor specialist execution was cancelled.",
                retryable=False,
            )
            await self._fail_task(request.project_id, prepared.a2a_task_id, trace_id, error)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise error from exc
        except (ValidationError, ValueError) as exc:
            error = self._error(
                A2AErrorCode.ARTIFACT_INVALID,
                prepared.a2a_task_id,
                request.specialist_type,
                "Competitor specialist returned an invalid evidence artifact.",
                retryable=False,
            )
            await self._fail_task(request.project_id, prepared.a2a_task_id, trace_id, error)
            raise error from exc
        except A2AGatewayError:
            raise
        except RuntimeGatewayError as exc:
            code = {
                RuntimeErrorCode.TIMEOUT: A2AErrorCode.TIMEOUT,
                RuntimeErrorCode.CANCELLED: A2AErrorCode.CANCELLED,
                RuntimeErrorCode.DEPENDENCY_MISSING: A2AErrorCode.DEPENDENCY_MISSING,
                RuntimeErrorCode.SCHEMA_INVALID: A2AErrorCode.ARTIFACT_INVALID,
                RuntimeErrorCode.ARTIFACT_INVALID: A2AErrorCode.ARTIFACT_INVALID,
            }.get(exc.code, A2AErrorCode.ADAPTER_FAILED)
            error = self._error(
                code,
                prepared.a2a_task_id,
                request.specialist_type,
                "Competitor specialist runtime failed.",
                retryable=exc.retryable,
            )
            await self._fail_task(request.project_id, prepared.a2a_task_id, trace_id, error)
            raise error from exc
        except Exception as exc:
            error = self._error(
                A2AErrorCode.ADAPTER_FAILED,
                prepared.a2a_task_id,
                request.specialist_type,
                "Competitor specialist adapter failed.",
                retryable=True,
            )
            await self._fail_task(request.project_id, prepared.a2a_task_id, trace_id, error)
            raise error from exc

        await self._complete_task(request.project_id, trace_id, artifact)
        return SpecialistTaskResult(
            a2a_task_id=prepared.a2a_task_id,
            request=request,
            status=A2ATaskStatus(artifact.status),
            artifact=artifact,
            attempt_number=prepared.attempt_number,
        )

    async def _prepare_task(
        self,
        *,
        parent_agent_run_id: str,
        trace_id: str,
        request: EvidenceRequest,
        input_hash: str,
        binding: SpecialistBinding | None,
    ) -> _PreparedTask:
        async with self._event_lock:
            async with self.database.session() as session:
                repository = A2ATaskRepository(session)
                projects = ProjectRepository(session)
                existing = await repository.get_by_identity(
                    request.project_id,
                    request.parent_task_id,
                    request.specialist_type,
                )
                if (
                    existing is not None
                    and existing.input_hash == input_hash
                    and existing.output_json is not None
                    and existing.status
                    in {
                        A2ATaskStatus.COMPLETED,
                        A2ATaskStatus.PARTIAL,
                        A2ATaskStatus.BLOCKED,
                    }
                ):
                    artifact = CompetitorSpecialistArtifact.model_validate(
                        existing.output_json
                    )
                    await projects.add_event(
                        self._event(
                            request.project_id,
                            trace_id,
                            "a2a_task_reused",
                            {
                                "a2a_task_id": existing.a2a_task_id,
                                "parent_task_id": request.parent_task_id,
                                "specialist_type": request.specialist_type,
                                "attempt_number": existing.attempt_count,
                            },
                        )
                    )
                    await repository.commit()
                    await self.event_broker.notify(request.project_id)
                    return _PreparedTask(
                        a2a_task_id=existing.a2a_task_id,
                        attempt_number=existing.attempt_count,
                        artifact=artifact,
                        reused=True,
                    )

                now = datetime.now(UTC)
                adapter_type = binding.adapter_type if binding is not None else "unbound"
                status = (
                    A2ATaskStatus.RUNNING
                    if binding is not None
                    else A2ATaskStatus.BLOCKED
                )
                event_type = (
                    "a2a_task_started" if binding is not None else "a2a_task_blocked"
                )
                if existing is None:
                    task = A2ATaskModel(
                        a2a_task_id=self._task_id(request),
                        project_id=request.project_id,
                        parent_agent_run_id=parent_agent_run_id,
                        parent_task_id=request.parent_task_id,
                        specialist_type=request.specialist_type,
                        adapter_type=adapter_type,
                        status=status,
                        attempt_count=1 if binding is not None else 0,
                        input_hash=input_hash,
                        request_json=request.model_dump(mode="json"),
                        output_json=None,
                        evidence_ids_json=[],
                        trace_id=trace_id,
                        error_code=(
                            None
                            if binding is not None
                            else A2AErrorCode.SPECIALIST_NOT_BOUND
                        ),
                        error_message=(
                            None
                            if binding is not None
                            else "No executable specialist adapter is bound."
                        ),
                        started_at=now if binding is not None else None,
                        completed_at=now if binding is None else None,
                        created_at=now,
                        updated_at=now,
                    )
                    await repository.add(task)
                else:
                    task = existing
                    task.parent_agent_run_id = parent_agent_run_id
                    task.adapter_type = adapter_type
                    task.status = status
                    if binding is not None:
                        task.attempt_count += 1
                    task.input_hash = input_hash
                    task.request_json = request.model_dump(mode="json")
                    task.output_json = None
                    task.evidence_ids_json = []
                    task.trace_id = trace_id
                    task.error_code = (
                        None if binding is not None else A2AErrorCode.SPECIALIST_NOT_BOUND
                    )
                    task.error_message = (
                        None
                        if binding is not None
                        else "No executable specialist adapter is bound."
                    )
                    task.started_at = now if binding is not None else None
                    task.completed_at = now if binding is None else None
                    task.updated_at = now
                await projects.add_event(
                    self._event(
                        request.project_id,
                        trace_id,
                        event_type,
                        {
                            "a2a_task_id": task.a2a_task_id,
                            "parent_agent_run_id": parent_agent_run_id,
                            "parent_task_id": request.parent_task_id,
                            "specialist_type": request.specialist_type,
                            "adapter_type": adapter_type,
                            "attempt_number": task.attempt_count,
                            "error_code": task.error_code,
                        },
                    )
                )
                await repository.commit()
        await self.event_broker.notify(request.project_id)
        return _PreparedTask(
            a2a_task_id=task.a2a_task_id,
            attempt_number=task.attempt_count,
            artifact=None,
            reused=False,
        )

    async def _complete_task(
        self,
        project_id: str,
        trace_id: str,
        artifact: CompetitorSpecialistArtifact,
    ) -> None:
        async with self._event_lock:
            async with self.database.session() as session:
                repository = A2ATaskRepository(session)
                projects = ProjectRepository(session)
                task = await repository.get(artifact.a2a_task_id)
                if task is None:
                    raise RuntimeError("A2A task disappeared before completion")
                now = datetime.now(UTC)
                task.status = A2ATaskStatus(artifact.status)
                task.output_json = artifact.model_dump(mode="json")
                task.evidence_ids_json = artifact.evidence_ids
                task.error_code = None
                task.error_message = None
                task.completed_at = now
                task.updated_at = now
                await projects.add_event(
                    self._event(
                        project_id,
                        trace_id,
                        "a2a_task_completed",
                        {
                            "a2a_task_id": task.a2a_task_id,
                            "parent_task_id": task.parent_task_id,
                            "specialist_type": task.specialist_type,
                            "status": task.status,
                            "attempt_number": task.attempt_count,
                            "evidence_count": len(task.evidence_ids_json),
                        },
                    )
                )
                await repository.commit()
        await self.event_broker.notify(project_id)

    async def _fail_task(
        self,
        project_id: str,
        a2a_task_id: str,
        trace_id: str,
        error: A2AGatewayError,
    ) -> None:
        async with self._event_lock:
            async with self.database.session() as session:
                repository = A2ATaskRepository(session)
                projects = ProjectRepository(session)
                task = await repository.get(a2a_task_id)
                if task is None:
                    return
                now = datetime.now(UTC)
                task.status = (
                    A2ATaskStatus.CANCELLED
                    if error.code is A2AErrorCode.CANCELLED
                    else A2ATaskStatus.FAILED
                )
                task.output_json = None
                task.evidence_ids_json = []
                task.error_code = error.code
                task.error_message = str(error)
                task.completed_at = now
                task.updated_at = now
                await projects.add_event(
                    self._event(
                        project_id,
                        trace_id,
                        "a2a_task_failed",
                        {
                            "a2a_task_id": task.a2a_task_id,
                            "parent_task_id": task.parent_task_id,
                            "specialist_type": task.specialist_type,
                            "status": task.status,
                            "attempt_number": task.attempt_count,
                            "error_code": error.code,
                            "retryable": error.retryable,
                        },
                    )
                )
                await repository.commit()
        await self.event_broker.notify(project_id)

    @staticmethod
    def _validate_batch(requests: list[EvidenceRequest], context: AgentContext) -> None:
        if not requests:
            raise ValueError("competitor A2A batch cannot be empty")
        if any(request.project_id != context.project_id for request in requests):
            raise ValueError("A2A request and context project ids do not match")
        specialist_types = [request.specialist_type for request in requests]
        if len(specialist_types) != len(set(specialist_types)):
            raise ValueError("A2A batch cannot contain duplicate specialist types")

    @staticmethod
    def _validate_artifact(
        invocation: A2ASpecialistInvocation,
        artifact: CompetitorSpecialistArtifact,
    ) -> None:
        if artifact.a2a_task_id != invocation.a2a_task_id:
            raise ValueError("specialist artifact a2a_task_id does not match invocation")
        if artifact.request_id != invocation.request.request_id:
            raise ValueError("specialist artifact request_id does not match invocation")
        if artifact.specialist_type is not invocation.request.specialist_type:
            raise ValueError("specialist artifact type does not match invocation")
        if artifact.status is ResearchTaskStatus.COMPLETED and not artifact.evidence_ids:
            raise ValueError("completed specialist artifact must cite evidence")
        evidence_context = invocation.context.evidence_context
        available = {
            item.evidence_id: item
            for item in (evidence_context.items if evidence_context is not None else [])
        }
        missing = sorted(set(artifact.evidence_ids) - set(available))
        if missing:
            raise ValueError(f"specialist artifact cites unavailable evidence: {missing}")
        disallowed = sorted(
            evidence_id
            for evidence_id in artifact.evidence_ids
            if available[evidence_id].claim_type
            not in invocation.request.allowed_claim_types
        )
        if disallowed:
            raise ValueError(f"specialist artifact cites disallowed evidence: {disallowed}")

    @staticmethod
    def _input_hash(request: EvidenceRequest, context: AgentContext) -> str:
        content = {
            "request": request.model_dump(mode="json"),
            "evidence_context_hash": (
                context.evidence_context.context_hash
                if context.evidence_context is not None
                else None
            ),
            "upstream_artifact_ids": sorted(
                artifact.artifact_id for artifact in context.upstream_artifacts.values()
            ),
        }
        canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _task_id(request: EvidenceRequest) -> str:
        identity = f"{request.project_id}:{request.parent_task_id}:{request.specialist_type}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"a2a_{digest[:24]}"

    @staticmethod
    def _error(
        code: A2AErrorCode,
        a2a_task_id: str,
        specialist_type: CompetitorSpecialistType,
        message: str,
        *,
        retryable: bool,
    ) -> A2AGatewayError:
        return A2AGatewayError(
            code,
            message,
            a2a_task_id=a2a_task_id,
            specialist_type=specialist_type,
            retryable=retryable,
        )

    @staticmethod
    def _event(
        project_id: str,
        trace_id: str,
        event_type: str,
        data: dict[str, object],
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type=event_type,
            data_json=data,
            trace_id=trace_id,
            created_at=datetime.now(UTC),
        )
