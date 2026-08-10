"""Pre-project multi-turn Research Brief clarification orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.brief_clarification.prompt import BRIEF_CLARIFIER_PROMPT_KEY
from app.application.model_gateway import (
    ModelCatalog,
    ModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelRequest,
    PromptRegistry,
)
from app.core.errors import AppError
from app.infrastructure.database.brief_clarification_repository import (
    BriefClarificationRepository,
)
from app.infrastructure.database.models import BriefClarificationSessionModel
from app.schemas.brief_clarification import (
    BriefClarificationAnswer,
    BriefClarificationSession,
    BriefClarificationStart,
    BriefClarifierModelOutput,
    ClarificationMessage,
    ClarificationQuestion,
    ClarificationRole,
    ClarificationStatus,
    ResearchBriefDraft,
)
from app.schemas.project import ResearchBrief

REQUIRED_FIELD_PATHS = (
    "question",
    "research_scope",
    "safety_domains",
    "target_ecosystems",
    "comparison_ecosystems",
    "target_users",
    "markets",
    "time_horizon",
    "safety_goals",
    "risk_scenarios",
    "authorized_signal_types",
    "privacy_boundary.raw_media_allowed",
    "privacy_boundary.restricted_zones",
    "privacy_boundary.retention_policy",
    "privacy_boundary.external_sharing_allowed",
    "intervention_boundary.allowed_interventions",
    "intervention_boundary.prohibited_actions",
    "intervention_boundary.high_impact_action_requires_human_approval",
    "forbidden_inferences",
    "evaluation_dimensions",
    "validation_expectations",
    "source_permissions.public_sources",
    "source_permissions.user_uploaded_materials",
    "source_permissions.enterprise_internal_materials",
    "source_permissions.authorized_household_events",
    "deliverables",
)

_FIELD_LABELS = {
    "research_scope": "研究单一设备还是整个家庭安防生态",
    "safety_domains": "需要保护的安全领域",
    "target_ecosystems": "目标生态",
    "target_users": "目标用户或家庭类型",
    "markets": "目标市场或地区",
    "risk_scenarios": "重点风险场景",
    "authorized_signal_types": "允许使用的设备事件和上下文信号",
    "privacy_boundary.raw_media_allowed": "是否允许使用原始音视频",
    "privacy_boundary.restricted_zones": "禁止使用摄像头或采集信号的区域",
    "intervention_boundary.allowed_interventions": "风险上升时允许系统执行的动作",
    "source_permissions.authorized_household_events": "是否允许使用授权家庭事件",
    "deliverables": "最终需要报告、策略验证还是试点建议",
}

_SENSITIVE_FIELD_PREFIXES = (
    "authorized_signal_types",
    "privacy_boundary",
    "intervention_boundary",
    "forbidden_inferences",
    "source_permissions",
)


class BriefClarificationService:
    def __init__(
        self,
        session: AsyncSession,
        model_gateway: ModelGateway,
        prompt_registry: PromptRegistry,
        model_catalog: ModelCatalog,
        trace_id: str,
        *,
        model_timeout_seconds: float = 120,
    ) -> None:
        self.session = session
        self.repository = BriefClarificationRepository(session)
        self.model_gateway = model_gateway
        self.prompt_registry = prompt_registry
        self.model_catalog = model_catalog
        self.trace_id = trace_id
        self.model_timeout_seconds = model_timeout_seconds

    async def start(self, payload: BriefClarificationStart) -> BriefClarificationSession:
        model_id = self._resolve_model_id(payload.model_id)
        now = datetime.now(UTC)
        initial = ClarificationMessage(
            message_id=f"msg_{uuid4().hex[:16]}",
            role=ClarificationRole.USER,
            content=payload.initial_question.strip(),
            created_at=now,
        )
        model = BriefClarificationSessionModel(
            session_id=f"brief_session_{uuid4().hex[:16]}",
            status=ClarificationStatus.AWAITING_USER,
            model_id=model_id,
            messages_json=[initial.model_dump(mode="json")],
            draft_json={},
            missing_fields_json=list(REQUIRED_FIELD_PATHS),
            validation_issues_json=[],
            questions_json=[],
            version=1,
            created_at=now,
            updated_at=now,
        )
        try:
            await self.repository.add(model)
            await self.repository.commit()
        except Exception:
            await self.repository.rollback()
            raise
        return await self._run_clarifier(model)

    async def get(self, session_id: str) -> BriefClarificationSession:
        return self._to_schema(await self._require(session_id))

    async def answer(
        self, session_id: str, payload: BriefClarificationAnswer
    ) -> BriefClarificationSession:
        model = await self._require(session_id)
        if model.version != payload.expected_version:
            raise AppError(
                code="BRIEF_CLARIFICATION_VERSION_CONFLICT",
                message="追问会话已被更新，请刷新后再提交。",
                status_code=409,
                details={"expected_version": model.version},
            )
        if model.status == ClarificationStatus.FAILED:
            raise AppError(
                code="BRIEF_CLARIFICATION_FAILED",
                message="该追问会话已失败，请重新创建会话。",
                status_code=409,
                details={"session_id": session_id},
            )
        messages = list(model.messages_json)
        messages.append(
            ClarificationMessage(
                message_id=f"msg_{uuid4().hex[:16]}",
                role=ClarificationRole.USER,
                content=payload.message.strip(),
                created_at=datetime.now(UTC),
            ).model_dump(mode="json")
        )
        model.messages_json = messages
        model.updated_at = datetime.now(UTC)
        await self.repository.commit()
        return await self._run_clarifier(model, increment_version=True)

    async def _run_clarifier(
        self,
        model: BriefClarificationSessionModel,
        *,
        increment_version: bool = False,
    ) -> BriefClarificationSession:
        prompt = self.prompt_registry.resolve(BRIEF_CLARIFIER_PROMPT_KEY)
        rendered = prompt.render(
            {
                "conversation_json": json.dumps(
                    model.messages_json, ensure_ascii=False, sort_keys=True
                ),
                "current_draft_json": json.dumps(
                    model.draft_json, ensure_ascii=False, sort_keys=True
                ),
                "missing_fields_json": json.dumps(
                    model.missing_fields_json, ensure_ascii=False
                ),
                "allowed_field_paths_json": json.dumps(
                    REQUIRED_FIELD_PATHS, ensure_ascii=False
                ),
            }
        )
        try:
            result = await self.model_gateway.generate(
                ModelRequest(
                    project_id=None,
                    agent_run_id=None,
                    clarification_session_id=model.session_id,
                    trace_id=self.trace_id,
                    model_id=model.model_id,
                    prompt_key=prompt.prompt_key,
                    prompt_version=prompt.version,
                    messages=(
                        ModelMessage(role="system", content=rendered.system),
                        ModelMessage(role="user", content=rendered.user),
                    ),
                    response_model=BriefClarifierModelOutput,
                    timeout_seconds=self.model_timeout_seconds,
                    max_output_tokens=4_000,
                    provider_options={
                        "temperature": 0.1,
                        "thinking": {"type": "disabled"},
                    },
                )
            )
        except ModelGatewayError as exc:
            model.status = ClarificationStatus.FAILED
            model.error_code = exc.code
            model.updated_at = datetime.now(UTC)
            await self.repository.commit()
            raise AppError(
                code="BRIEF_CLARIFIER_MODEL_FAILED",
                message="Research Brief 追问模型调用失败。",
                status_code=502,
                details={
                    "session_id": model.session_id,
                    "model_error": exc.code,
                    "retryable": exc.retryable,
                },
            ) from exc

        output = BriefClarifierModelOutput.model_validate(result.output)
        patch = output.draft_patch.model_dump(mode="json", exclude_none=True)
        accepted_patch = self._filter_supported_patch(
            patch, output, model.messages_json, model.questions_json
        )
        draft = self._deep_merge(model.draft_json, accepted_patch)
        missing = self._missing_fields(draft)
        completed, issues = self._validate_completed(draft, missing)
        questions = self._filter_questions(output.questions, missing)
        if completed is None and not questions:
            questions = [self._fallback_question(missing, issues)]

        assistant_content = output.assistant_message.strip()
        if completed is not None:
            assistant_content = "Research Brief 的必填范围已经补齐，请检查并确认后创建项目。"
            questions = []
        messages = list(model.messages_json)
        messages.append(
            ClarificationMessage(
                message_id=f"msg_{uuid4().hex[:16]}",
                role=ClarificationRole.ASSISTANT,
                content=assistant_content,
                created_at=datetime.now(UTC),
            ).model_dump(mode="json")
        )
        await self.session.refresh(model)
        model.messages_json = messages
        model.draft_json = draft
        model.missing_fields_json = missing
        model.validation_issues_json = issues
        model.questions_json = [item.model_dump(mode="json") for item in questions]
        model.status = (
            ClarificationStatus.READY_FOR_CONFIRMATION
            if completed is not None
            else ClarificationStatus.AWAITING_USER
        )
        model.error_code = None
        if increment_version:
            model.version += 1
        model.updated_at = datetime.now(UTC)
        await self.repository.commit()
        return self._to_schema(model)

    def _resolve_model_id(self, requested: str | None) -> str:
        model_id = requested.strip().lower() if requested else self.model_catalog.default_model_id
        if model_id is None:
            raise AppError(
                code="BRIEF_CLARIFIER_MODEL_REQUIRED",
                message="请先选择一个可用模型。",
                status_code=422,
            )
        try:
            self.model_catalog.require_enabled(model_id)
        except ValueError as exc:
            raise AppError(
                code="BRIEF_CLARIFIER_MODEL_INVALID",
                message="所选模型不存在或未启用。",
                status_code=422,
                details={"model_id": model_id},
            ) from exc
        return model_id

    async def _require(self, session_id: str) -> BriefClarificationSessionModel:
        model = await self.repository.get(session_id)
        if model is None:
            raise AppError(
                code="BRIEF_CLARIFICATION_NOT_FOUND",
                message="Research Brief 追问会话不存在。",
                status_code=404,
                details={"session_id": session_id},
            )
        return model

    @staticmethod
    def _filter_supported_patch(
        patch: dict[str, Any],
        output: BriefClarifierModelOutput,
        messages: list[dict[str, Any]],
        previous_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        user_ids = {
            str(item["message_id"])
            for item in messages
            if item.get("role") == ClarificationRole.USER
        }
        evidence = {
            item.field_path: set(item.message_ids) for item in output.field_evidence
        }
        asked_paths = {
            str(path)
            for question in previous_questions
            for path in question.get("field_paths", [])
        }

        accepted: dict[str, Any] = {}
        for leaf_path, value in BriefClarificationService._flatten(patch):
            cited = set()
            for path, message_ids in evidence.items():
                if leaf_path == path or leaf_path.startswith(f"{path}."):
                    cited.update(message_ids)
            sensitive = any(
                leaf_path == prefix or leaf_path.startswith(f"{prefix}.")
                for prefix in _SENSITIVE_FIELD_PREFIXES
            )
            explicitly_asked = any(
                leaf_path == path
                or leaf_path.startswith(f"{path}.")
                or path.startswith(f"{leaf_path}.")
                for path in asked_paths
            )
            if cited and cited <= user_ids and (not sensitive or explicitly_asked):
                BriefClarificationService._set_path(accepted, leaf_path, value)
        return accepted

    @staticmethod
    def _missing_fields(draft: dict[str, Any]) -> list[str]:
        missing = []
        for path in REQUIRED_FIELD_PATHS:
            value: Any = draft
            for segment in path.split("."):
                if not isinstance(value, dict) or segment not in value:
                    value = None
                    break
                value = value[segment]
            if value is None:
                missing.append(path)
        return missing

    @staticmethod
    def _validate_completed(
        draft: dict[str, Any], missing: list[str]
    ) -> tuple[ResearchBrief | None, list[str]]:
        if missing:
            return None, []
        try:
            return ResearchBrief.model_validate(draft), []
        except ValidationError as exc:
            issues = []
            for error in exc.errors():
                location = ".".join(str(item) for item in error["loc"])
                issues.append(f"{location}: {error['msg']}")
            return None, issues

    @staticmethod
    def _filter_questions(
        questions: list[ClarificationQuestion], missing: list[str]
    ) -> list[ClarificationQuestion]:
        result = []
        seen: set[str] = set()
        for question in questions:
            relevant = [
                path
                for path in question.field_paths
                if any(
                    path == missing_path
                    or missing_path.startswith(f"{path}.")
                    or path.startswith(f"{missing_path}.")
                    for missing_path in missing
                )
            ]
            if relevant and question.question_id not in seen:
                result.append(question.model_copy(update={"field_paths": relevant}))
                seen.add(question.question_id)
        return result[:6]

    @staticmethod
    def _fallback_question(
        missing: list[str], issues: list[str]
    ) -> ClarificationQuestion:
        path = missing[0] if missing else "research_scope"
        label = _FIELD_LABELS.get(path, path)
        prompt = f"为了完成 Research Brief，请补充：{label}。"
        if issues:
            prompt = f"当前 Brief 仍有冲突，请修正：{issues[0]}"
        return ClarificationQuestion(
            question_id=f"clarify_{path.replace('.', '_')}",
            field_paths=[path],
            prompt=prompt,
        )

    def _to_schema(self, model: BriefClarificationSessionModel) -> BriefClarificationSession:
        missing = list(model.missing_fields_json)
        completed, _ = self._validate_completed(dict(model.draft_json), missing)
        return BriefClarificationSession(
            session_id=model.session_id,
            status=ClarificationStatus(model.status),
            version=model.version,
            model_id=model.model_id,
            messages=[ClarificationMessage.model_validate(item) for item in model.messages_json],
            draft=ResearchBriefDraft.model_validate(model.draft_json),
            missing_fields=missing,
            validation_issues=list(model.validation_issues_json),
            questions=[ClarificationQuestion.model_validate(item) for item in model.questions_json],
            completed_brief=completed,
            input_tokens=model.input_tokens,
            output_tokens=model.output_tokens,
            estimated_cost_microusd=model.estimated_cost_microusd,
            created_at=self._as_utc(model.created_at),
            updated_at=self._as_utc(model.updated_at),
        )

    @staticmethod
    def _deep_merge(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current)
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = BriefClarificationService._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _flatten(payload: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
        result: list[tuple[str, Any]] = []
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.extend(BriefClarificationService._flatten(value, path))
            else:
                result.append((path, value))
        return result

    @staticmethod
    def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
        cursor = payload
        parts = path.split(".")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = value

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
