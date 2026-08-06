import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.application.model_gateway import (
    EnvironmentCredentialResolver,
    ModelCatalog,
    ModelErrorCode,
    ModelGateway,
    ModelGatewayError,
    ModelMessage,
    ModelProviderError,
    ModelProviderRegistry,
    ModelRequest,
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.infrastructure.database import Database
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.models import AgentRunModel, ProjectModel
from app.schemas.project import AgentRunStatus, ProjectStatus


class StructuredOutput(BaseModel):
    answer: str


class ScriptedProvider:
    provider_id = "test"

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            result = outcome(request)
            if asyncio.iscoroutine(result):
                return await result
            return result
        assert isinstance(outcome, ProviderModelResult)
        return outcome


def _catalog() -> ModelCatalog:
    return ModelCatalog.from_json(
        json.dumps(
            [
                {
                    "model_id": "test:model-a",
                    "provider": "test",
                    "provider_model": "provider-model-a",
                    "display_name": "Test Model A",
                    "credential_env": "TEST_MODEL_KEY",
                    "capabilities": ["text", "structured_output"],
                    "input_cost_microusd_per_million_tokens": 1000000,
                    "output_cost_microusd_per_million_tokens": 2000000,
                }
            ]
        )
    )


async def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'gateway.db'}")
    await database.create_schema()
    now = datetime.now(UTC)
    async with database.session() as session:
        session.add(
            ProjectModel(
                project_id="proj_model",
                status=ProjectStatus.RESEARCHING,
                current_stage="model_test",
                progress=10,
                brief_json={
                    "question": "Which event needs research?",
                    "category": "security",
                    "target_user": "home users",
                    "region": "US",
                },
                created_at=now,
                updated_at=now,
            )
        )
        for run_id in ("run_success", "run_invalid", "run_missing", "run_timeout"):
            session.add(
                AgentRunModel(
                    agent_run_id=run_id,
                    project_id="proj_model",
                    agent_type="test",
                    agent_name="Test Agent",
                    status=AgentRunStatus.RUNNING,
                    progress=10,
                    message="test",
                )
            )
        await session.commit()
    return database


def _request(run_id: str, *, timeout_seconds: float = 1) -> ModelRequest:
    return ModelRequest(
        project_id="proj_model",
        agent_run_id=run_id,
        trace_id="trace_model",
        model_id="test:model-a",
        prompt_key="agent:test",
        prompt_version="1",
        messages=(ModelMessage(role="user", content="Return structured test output."),),
        response_model=StructuredOutput,
        timeout_seconds=timeout_seconds,
    )


@pytest.mark.asyncio
async def test_gateway_retries_rate_limit_and_persists_usage_without_secret(
    tmp_path: Path,
) -> None:
    database = await _database(tmp_path)
    provider = ScriptedProvider(
        [
            ModelProviderError(
                ModelErrorCode.RATE_LIMITED,
                "raw provider detail must not be persisted",
                retryable=True,
                provider_request_id="provider-failed-request",
            ),
            ProviderModelResult(
                output='{"answer":"ok"}',
                usage=ModelUsage(input_tokens=10, output_tokens=5),
                provider_request_id="provider-success-request",
            ),
        ]
    )
    registry = ModelProviderRegistry()
    registry.register(provider)
    delays: list[float] = []

    async def record_delay(seconds: float) -> None:
        delays.append(seconds)

    gateway = ModelGateway(
        database,
        _catalog(),
        EnvironmentCredentialResolver({"TEST_MODEL_KEY": "unit-test-credential"}),
        registry,
        max_retries=2,
        retry_base_seconds=0.1,
        sleep=record_delay,
    )
    try:
        result = await gateway.generate(_request("run_success"))

        assert result.output == StructuredOutput(answer="ok")
        assert result.attempt_count == 2
        assert result.estimated_cost_microusd == 20
        assert delays == [0.1]
        assert len(provider.requests) == 2
        assert provider.requests[0].credential == "unit-test-credential"
        async with database.session() as session:
            repository = ModelCallRepository(session)
            calls = await repository.list_for_run("run_success")
            run = await repository.require_run("run_success")
        assert [call.status for call in calls] == ["failed", "completed"]
        assert calls[0].error_code == ModelErrorCode.RATE_LIMITED
        assert calls[0].error_message == "模型 Provider 调用失败。"
        assert run.model_id == "test:model-a"
        assert run.prompt_version == "1"
        assert run.input_tokens == 10
        assert run.output_tokens == 5
        assert run.estimated_cost_microusd == 20
        audit_payload = json.dumps(
            [
                {
                    key: value
                    for key, value in vars(call).items()
                    if not key.startswith("_")
                }
                for call in calls
            ],
            default=str,
        )
        assert "unit-test-credential" not in audit_payload
        assert "raw provider detail" not in audit_payload
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_gateway_rejects_invalid_schema_and_missing_credential(
    tmp_path: Path,
) -> None:
    database = await _database(tmp_path)
    provider = ScriptedProvider([ProviderModelResult(output={"unexpected": True})])
    registry = ModelProviderRegistry()
    registry.register(provider)
    gateway = ModelGateway(
        database,
        _catalog(),
        EnvironmentCredentialResolver({"TEST_MODEL_KEY": "unit-test-credential"}),
        registry,
        max_retries=2,
        retry_base_seconds=0,
    )
    missing_gateway = ModelGateway(
        database,
        _catalog(),
        EnvironmentCredentialResolver({}),
        registry,
    )
    try:
        with pytest.raises(ModelGatewayError) as invalid_error:
            await gateway.generate(_request("run_invalid"))
        with pytest.raises(ModelGatewayError) as missing_error:
            await missing_gateway.generate(_request("run_missing"))

        assert invalid_error.value.code is ModelErrorCode.STRUCTURED_OUTPUT_INVALID
        assert invalid_error.value.retryable is False
        assert missing_error.value.code is ModelErrorCode.CREDENTIAL_MISSING
        async with database.session() as session:
            repository = ModelCallRepository(session)
            invalid_calls = await repository.list_for_run("run_invalid")
            missing_calls = await repository.list_for_run("run_missing")
        assert len(invalid_calls) == 1
        assert len(missing_calls) == 1
        assert missing_calls[0].error_code == ModelErrorCode.CREDENTIAL_MISSING
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_gateway_times_out_without_creating_success_usage(tmp_path: Path) -> None:
    database = await _database(tmp_path)

    async def slow_result(request: ProviderModelRequest) -> ProviderModelResult:
        await asyncio.sleep(0.05)
        return ProviderModelResult(output={"answer": request.provider_model})

    provider = ScriptedProvider([slow_result])
    registry = ModelProviderRegistry()
    registry.register(provider)
    gateway = ModelGateway(
        database,
        _catalog(),
        EnvironmentCredentialResolver({"TEST_MODEL_KEY": "unit-test-credential"}),
        registry,
        max_retries=0,
    )
    try:
        with pytest.raises(ModelGatewayError) as timeout_error:
            await gateway.generate(_request("run_timeout", timeout_seconds=0.001))
        assert timeout_error.value.code is ModelErrorCode.TIMEOUT
        async with database.session() as session:
            repository = ModelCallRepository(session)
            calls = await repository.list_for_run("run_timeout")
            run = await repository.require_run("run_timeout")
        assert len(calls) == 1
        assert calls[0].status == "failed"
        assert run.input_tokens == 0
        assert run.estimated_cost_microusd == 0
    finally:
        await database.dispose()
