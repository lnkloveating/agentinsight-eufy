"""统一执行内部模型、外部 Runtime 和 A2A Adapter 的运行核心。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.application.events import ProjectEventBroker
from app.application.runtime.contracts import (
    AgentInvocation,
    CancellationToken,
    RuntimeCancellationError,
    RuntimeErrorCode,
    RuntimeGatewayError,
)
from app.application.runtime.registry import AgentRegistry
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.models import (
    AgentArtifactModel,
    AgentRunModel,
    ProjectEventModel,
)
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.runtime_repository import AgentRuntimeRepository
from app.infrastructure.database.session import Database
from app.schemas.evidence import EvidenceStatus
from app.schemas.project import AgentRunStatus
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
    WorkflowContractError,
)

AGENT_NAMES: dict[ResearchAgentType, str] = {
    ResearchAgentType.RESEARCH_MANAGER: "调研总管 Agent",
    ResearchAgentType.USER_RESEARCH: "用户研究 Agent",
    ResearchAgentType.COMPETITOR_RESEARCH: "竞品研究 Agent",
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY: "生态机会 Agent",
    ResearchAgentType.TECHNICAL_FEASIBILITY: "技术可行性 Agent",
    ResearchAgentType.SECURITY_POLICY: "安全策略编译 Agent",
    ResearchAgentType.COMMERCIAL_EVALUATION: "商业分析 Agent",
    ResearchAgentType.RED_TEAM: "红队 Agent",
    ResearchAgentType.CANDIDATE_SYNTHESIS: "候选综合 Agent",
    ResearchAgentType.VALIDATION: "验证分发 Agent",
    ResearchAgentType.FINAL_SYNTHESIS: "最终综合 Agent",
}


@dataclass
class _ActiveInvocation:
    token: CancellationToken
    task: asyncio.Task[object]


class AgentRuntimeGateway:
    """实现 LangGraph 的 AgentRuntime Protocol，并保存完整运行审计。"""

    def __init__(
        self,
        database: Database,
        registry: AgentRegistry,
        event_broker: ProjectEventBroker,
        trace_id: str,
        *,
        max_timeout_seconds: float | None = None,
    ) -> None:
        if max_timeout_seconds is not None and max_timeout_seconds <= 0:
            raise ValueError("max_timeout_seconds must be positive")
        self.database = database
        self.registry = registry
        self.event_broker = event_broker
        self.trace_id = trace_id
        self.max_timeout_seconds = max_timeout_seconds
        self._project_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._active: dict[str, _ActiveInvocation] = {}
        self._active_lock = asyncio.Lock()

    async def execute(
        self,
        task: ResearchTask,
        context: AgentContext,
    ) -> ResearchArtifact:
        if context.project_id != task.project_id:
            raise WorkflowContractError("task and context project ids do not match")

        binding = self.registry.resolve(task.agent_type)
        input_artifact_ids = tuple(
            sorted({artifact.artifact_id for artifact in context.upstream_artifacts.values()})
        )
        timeout_seconds = self._timeout_seconds(task)
        run = await self._create_run(
            task,
            binding.adapter_type if binding is not None else "unbound",
            input_artifact_ids,
            timeout_seconds,
        )

        if binding is None:
            error = RuntimeGatewayError(
                RuntimeErrorCode.RUNTIME_NOT_BOUND,
                "没有为该 Agent 绑定可执行 Runtime。",
                agent_run_id=run.agent_run_id,
                retryable=False,
                details={"agent_type": task.agent_type},
            )
            await self._fail_run(task.project_id, run.agent_run_id, error)
            raise error

        try:
            await self._validate_input_artifacts(task.project_id, input_artifact_ids)
        except RuntimeGatewayError as input_error:
            input_error.agent_run_id = run.agent_run_id
            await self._fail_run(task.project_id, run.agent_run_id, input_error)
            raise

        token = CancellationToken()
        invocation = AgentInvocation(
            agent_run_id=run.agent_run_id,
            trace_id=self.trace_id,
            attempt_number=run.attempt_number,
            workspace_key=str(run.workspace_key),
            input_artifact_ids=input_artifact_ids,
            task=task,
            context=context,
            cancellation_token=token,
        )
        adapter_task = asyncio.create_task(binding.adapter.execute(invocation))
        async with self._active_lock:
            self._active[run.agent_run_id] = _ActiveInvocation(token, adapter_task)

        try:
            async with asyncio.timeout(timeout_seconds):
                raw_artifact = await adapter_task
            token.raise_if_cancelled()
            try:
                artifact = ResearchArtifact.model_validate(raw_artifact)
            except ValidationError as exc:
                raise RuntimeGatewayError(
                    RuntimeErrorCode.SCHEMA_INVALID,
                    "Agent 输出不符合 ResearchArtifact Schema。",
                    agent_run_id=run.agent_run_id,
                    retryable=False,
                ) from exc
            await self._validate_output(task, artifact)
            return await self._complete_run(run, task, artifact, input_artifact_ids)
        except TimeoutError as exc:
            timeout_error = RuntimeGatewayError(
                RuntimeErrorCode.TIMEOUT,
                "Agent 执行超过允许时间。",
                agent_run_id=run.agent_run_id,
                retryable=True,
                details={"timeout_seconds": timeout_seconds},
            )
            await self._fail_run(task.project_id, run.agent_run_id, timeout_error)
            raise timeout_error from exc
        except (asyncio.CancelledError, RuntimeCancellationError) as exc:
            cancellation_error = RuntimeGatewayError(
                RuntimeErrorCode.CANCELLED,
                "Agent 执行已取消。",
                agent_run_id=run.agent_run_id,
                retryable=False,
            )
            await self._fail_run(task.project_id, run.agent_run_id, cancellation_error)
            raise cancellation_error from exc
        except RuntimeGatewayError as gateway_error:
            gateway_error.agent_run_id = run.agent_run_id
            await self._fail_run(task.project_id, run.agent_run_id, gateway_error)
            raise
        except PermissionError as exc:
            permission_error = RuntimeGatewayError(
                RuntimeErrorCode.PERMISSION_DENIED,
                "Agent Adapter 拒绝了当前调用。",
                agent_run_id=run.agent_run_id,
                retryable=False,
            )
            await self._fail_run(task.project_id, run.agent_run_id, permission_error)
            raise permission_error from exc
        except Exception as exc:
            adapter_error = RuntimeGatewayError(
                RuntimeErrorCode.ADAPTER_FAILED,
                "Agent Adapter 执行失败。",
                agent_run_id=run.agent_run_id,
                retryable=True,
            )
            await self._fail_run(task.project_id, run.agent_run_id, adapter_error)
            raise adapter_error from exc
        finally:
            async with self._active_lock:
                self._active.pop(run.agent_run_id, None)

    async def cancel(self, agent_run_id: str) -> bool:
        async with self._active_lock:
            active = self._active.get(agent_run_id)
        if active is None:
            return False
        active.token.cancel()
        await self._mark_cancellation_requested(agent_run_id)
        active.task.cancel()
        return True

    async def active_run_ids(self) -> tuple[str, ...]:
        async with self._active_lock:
            return tuple(self._active)

    def _timeout_seconds(self, task: ResearchTask) -> float:
        configured = float(task.budget.deadline_seconds)
        if self.max_timeout_seconds is None:
            return configured
        return min(configured, self.max_timeout_seconds)

    async def _create_run(
        self,
        task: ResearchTask,
        adapter_type: str,
        input_artifact_ids: tuple[str, ...],
        timeout_seconds: float,
    ) -> AgentRunModel:
        async with self._project_locks[task.project_id]:
            async with self.database.session() as session:
                runtime_repository = AgentRuntimeRepository(session)
                project_repository = ProjectRepository(session)
                if not await runtime_repository.project_exists(task.project_id):
                    raise RuntimeGatewayError(
                        RuntimeErrorCode.DEPENDENCY_MISSING,
                        "研究项目不存在。",
                        agent_run_id="run_unpersisted",
                        retryable=False,
                    )
                attempt = await runtime_repository.next_attempt_number(
                    task.project_id, task.task_id
                )
                now = datetime.now(UTC)
                run = AgentRunModel(
                    agent_run_id=f"run_{uuid4().hex[:16]}",
                    project_id=task.project_id,
                    task_id=task.task_id,
                    agent_type=task.agent_type,
                    agent_name=AGENT_NAMES[task.agent_type],
                    adapter_type=adapter_type,
                    attempt_number=attempt,
                    workspace_key=f"{task.project_id}/{task.task_id}/attempt-{attempt}",
                    trace_id=self.trace_id,
                    timeout_seconds=timeout_seconds,
                    input_artifact_ids_json=list(input_artifact_ids),
                    status=AgentRunStatus.RUNNING,
                    progress=5,
                    quality_score=0,
                    evidence_ids_json=[],
                    unknowns_json=[],
                    message="Agent Runtime 已开始执行任务。",
                    started_at=now,
                )
                created = self._event(
                    task.project_id,
                    "agent_run_created",
                    {
                        "agent_run_id": run.agent_run_id,
                        "task_id": task.task_id,
                        "agent_type": task.agent_type,
                        "adapter_type": adapter_type,
                        "attempt_number": attempt,
                    },
                    now,
                )
                started = self._event(
                    task.project_id,
                    "agent_started",
                    {
                        "agent_run_id": run.agent_run_id,
                        "task_id": task.task_id,
                        "agent_type": task.agent_type,
                        "status": AgentRunStatus.RUNNING,
                    },
                    now,
                )
                try:
                    await runtime_repository.add_run(run)
                    await project_repository.add_event(created)
                    await project_repository.add_event(started)
                    await runtime_repository.commit()
                except Exception:
                    await runtime_repository.rollback()
                    raise
        await self.event_broker.notify(task.project_id)
        return run

    async def _validate_input_artifacts(
        self,
        project_id: str,
        artifact_ids: tuple[str, ...],
    ) -> None:
        if not artifact_ids:
            return
        async with self.database.session() as session:
            models = await AgentRuntimeRepository(session).get_artifacts_by_ids(set(artifact_ids))
        found_ids = {model.artifact_id for model in models}
        missing = sorted(set(artifact_ids) - found_ids)
        if missing:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "上游 Artifact 不存在。",
                agent_run_id="run_pending",
                retryable=True,
                details={"missing_artifact_ids": missing},
            )
        cross_project = sorted(
            model.artifact_id for model in models if model.project_id != project_id
        )
        if cross_project:
            raise RuntimeGatewayError(
                RuntimeErrorCode.PERMISSION_DENIED,
                "禁止读取其他项目的 Artifact。",
                agent_run_id="run_pending",
                retryable=False,
                details={"artifact_ids": cross_project},
            )

    async def _validate_output(
        self,
        task: ResearchTask,
        artifact: ResearchArtifact,
    ) -> None:
        if artifact.task_id != task.task_id:
            raise self._artifact_error("Artifact task_id 与当前任务不一致。")
        if artifact.artifact_type != task.agent_type:
            raise self._artifact_error("Artifact 类型与当前 Agent 不一致。")
        allowed_statuses = {
            ResearchTaskStatus.COMPLETED,
            ResearchTaskStatus.PARTIAL,
            ResearchTaskStatus.BLOCKED,
            ResearchTaskStatus.NEEDS_REVISION,
        }
        if artifact.status not in allowed_statuses:
            raise self._artifact_error("Artifact 状态不能作为结构化交付保存。")
        if (
            artifact.status is ResearchTaskStatus.COMPLETED
            and task.evidence_rules.citation_required
            and task.agent_type is not ResearchAgentType.RESEARCH_MANAGER
            and not artifact.evidence_ids
        ):
            raise self._artifact_error("完成状态的事实性 Artifact 缺少 Evidence ID。")
        await self._validate_evidence(task.project_id, artifact.evidence_ids)

    async def _validate_evidence(self, project_id: str, evidence_ids: list[str]) -> None:
        if not evidence_ids:
            return
        requested = set(evidence_ids)
        async with self.database.session() as session:
            models = await EvidenceRepository(session).get_evidence_by_ids(requested)
        by_id = {model.evidence_id: model for model in models}
        rejected: dict[str, str] = {}
        for evidence_id in requested:
            model = by_id.get(evidence_id)
            if model is None:
                rejected[evidence_id] = "not_found"
            elif model.project_id != project_id:
                rejected[evidence_id] = "cross_project"
            elif model.status not in {
                EvidenceStatus.VERIFIED,
                EvidenceStatus.PARTIALLY_VERIFIED,
            }:
                rejected[evidence_id] = f"status:{model.status}"
        if rejected:
            raise self._artifact_error(
                "Artifact 引用了无效、Mock 或跨项目 Evidence。",
                {"rejected_evidence_ids": rejected},
            )

    async def _complete_run(
        self,
        run: AgentRunModel,
        task: ResearchTask,
        artifact: ResearchArtifact,
        input_artifact_ids: tuple[str, ...],
    ) -> ResearchArtifact:
        async with self._project_locks[task.project_id]:
            async with self.database.session() as session:
                runtime_repository = AgentRuntimeRepository(session)
                project_repository = ProjectRepository(session)
                persisted_run = await runtime_repository.get_run(run.agent_run_id)
                if persisted_run is None:
                    raise RuntimeError("agent run disappeared before completion")
                version = await runtime_repository.next_artifact_version(
                    task.project_id, task.task_id, artifact.artifact_type
                )
                persisted_artifact = artifact.model_copy(
                    update={"artifact_id": f"artifact_{uuid4().hex[:16]}"}
                )
                content_hash = self._artifact_hash(persisted_artifact, input_artifact_ids)
                now = datetime.now(UTC)
                artifact_model = AgentArtifactModel(
                    artifact_id=persisted_artifact.artifact_id,
                    project_id=task.project_id,
                    agent_run_id=run.agent_run_id,
                    task_id=task.task_id,
                    artifact_type=persisted_artifact.artifact_type,
                    schema_version=persisted_artifact.schema_version,
                    version=version,
                    status=persisted_artifact.status,
                    payload_json=persisted_artifact.payload,
                    evidence_ids_json=persisted_artifact.evidence_ids,
                    contradictions_json=persisted_artifact.contradictions,
                    unknowns_json=persisted_artifact.unknowns,
                    quality_score=persisted_artifact.quality_score,
                    errors_json=persisted_artifact.errors,
                    input_artifact_ids_json=list(input_artifact_ids),
                    content_hash=content_hash,
                    created_at=now,
                )
                persisted_run.output_artifact_id = persisted_artifact.artifact_id
                persisted_run.status = self._run_status(persisted_artifact.status)
                persisted_run.progress = 100
                persisted_run.quality_score = persisted_artifact.quality_score
                persisted_run.evidence_ids_json = persisted_artifact.evidence_ids
                persisted_run.unknowns_json = persisted_artifact.unknowns
                persisted_run.message = "Agent 已完成并保存结构化 Artifact。"
                persisted_run.completed_at = now
                artifact_event = self._event(
                    task.project_id,
                    "artifact_created",
                    {
                        "artifact_id": persisted_artifact.artifact_id,
                        "agent_run_id": run.agent_run_id,
                        "task_id": task.task_id,
                        "artifact_type": persisted_artifact.artifact_type,
                        "version": version,
                        "input_artifact_ids": list(input_artifact_ids),
                    },
                    now,
                )
                completed_event = self._event(
                    task.project_id,
                    "agent_completed",
                    {
                        "agent_run_id": run.agent_run_id,
                        "task_id": task.task_id,
                        "status": persisted_run.status,
                        "artifact_id": persisted_artifact.artifact_id,
                        "quality_score": persisted_artifact.quality_score,
                    },
                    now,
                )
                try:
                    await runtime_repository.add_artifact(artifact_model)
                    await project_repository.add_event(artifact_event)
                    await project_repository.add_event(completed_event)
                    await runtime_repository.commit()
                except Exception:
                    await runtime_repository.rollback()
                    raise
        await self.event_broker.notify(task.project_id)
        return persisted_artifact

    async def _fail_run(
        self,
        project_id: str,
        agent_run_id: str,
        error: RuntimeGatewayError,
    ) -> None:
        async with self._project_locks[project_id]:
            async with self.database.session() as session:
                runtime_repository = AgentRuntimeRepository(session)
                project_repository = ProjectRepository(session)
                run = await runtime_repository.get_run(agent_run_id)
                if run is None:
                    return
                now = datetime.now(UTC)
                run.status = (
                    AgentRunStatus.CANCELLED
                    if error.code is RuntimeErrorCode.CANCELLED
                    else AgentRunStatus.FAILED
                )
                run.progress = 100
                run.error_code = error.code
                run.error_message = str(error)
                run.message = str(error)
                run.completed_at = now
                event_type = {
                    RuntimeErrorCode.TIMEOUT: "agent_timed_out",
                    RuntimeErrorCode.CANCELLED: "agent_cancelled",
                }.get(error.code, "agent_failed")
                event = self._event(
                    project_id,
                    event_type,
                    {
                        "agent_run_id": agent_run_id,
                        "task_id": run.task_id,
                        "status": run.status,
                        "error_code": error.code,
                        "retryable": error.retryable,
                    },
                    now,
                )
                try:
                    await project_repository.add_event(event)
                    await runtime_repository.commit()
                except Exception:
                    await runtime_repository.rollback()
                    raise
        await self.event_broker.notify(project_id)

    async def _mark_cancellation_requested(self, agent_run_id: str) -> None:
        async with self.database.session() as session:
            runtime_repository = AgentRuntimeRepository(session)
            run = await runtime_repository.get_run(agent_run_id)
            if run is None:
                return
            project_id = run.project_id
        async with self._project_locks[project_id]:
            async with self.database.session() as session:
                runtime_repository = AgentRuntimeRepository(session)
                project_repository = ProjectRepository(session)
                run = await runtime_repository.get_run(agent_run_id)
                if run is None:
                    return
                now = datetime.now(UTC)
                run.cancellation_requested_at = now
                event = self._event(
                    project_id,
                    "agent_cancel_requested",
                    {"agent_run_id": agent_run_id, "task_id": run.task_id},
                    now,
                )
                try:
                    await project_repository.add_event(event)
                    await runtime_repository.commit()
                except Exception:
                    await runtime_repository.rollback()
                    raise
        await self.event_broker.notify(project_id)

    def _artifact_error(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> RuntimeGatewayError:
        return RuntimeGatewayError(
            RuntimeErrorCode.ARTIFACT_INVALID,
            message,
            agent_run_id="run_pending",
            retryable=False,
            details=details,
        )

    def _event(
        self,
        project_id: str,
        event_type: str,
        data: dict[str, Any],
        created_at: datetime,
    ) -> ProjectEventModel:
        return ProjectEventModel(
            event_id=f"evt_{uuid4().hex[:16]}",
            project_id=project_id,
            sequence_number=0,
            event_type=event_type,
            data_json=data,
            trace_id=self.trace_id,
            created_at=created_at,
        )

    @staticmethod
    def _run_status(status: ResearchTaskStatus) -> AgentRunStatus:
        mapping = {
            ResearchTaskStatus.COMPLETED: AgentRunStatus.COMPLETED,
            ResearchTaskStatus.PARTIAL: AgentRunStatus.PARTIAL,
            ResearchTaskStatus.BLOCKED: AgentRunStatus.BLOCKED,
            ResearchTaskStatus.NEEDS_REVISION: AgentRunStatus.NEEDS_REVISION,
        }
        return mapping[status]

    @staticmethod
    def _artifact_hash(
        artifact: ResearchArtifact,
        input_artifact_ids: tuple[str, ...],
    ) -> str:
        content = {
            "artifact": artifact.model_dump(mode="json", exclude={"artifact_id"}),
            "input_artifact_ids": input_artifact_ids,
        }
        canonical = json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
