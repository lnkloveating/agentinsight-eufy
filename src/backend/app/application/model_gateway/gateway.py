"""统一模型调用、结构化校验、有限重试与审计持久化。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.application.model_gateway.catalog import ModelCatalog, ModelCatalogError
from app.application.model_gateway.contracts import (
    CredentialResolver,
    ModelErrorCode,
    ModelGatewayError,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.application.model_gateway.registry import ModelProviderRegistry
from app.infrastructure.database.model_call_repository import ModelCallRepository
from app.infrastructure.database.models import ModelCallModel
from app.infrastructure.database.session import Database
from app.schemas.model import ModelCapability

SleepFunction = Callable[[float], Awaitable[None]]


class ModelGateway:
    def __init__(
        self,
        database: Database,
        catalog: ModelCatalog,
        credentials: CredentialResolver,
        providers: ModelProviderRegistry,
        *,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
        sleep: SleepFunction = asyncio.sleep,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_base_seconds < 0:
            raise ValueError("retry_base_seconds cannot be negative")
        self.database = database
        self.catalog = catalog
        self.credentials = credentials
        self.providers = providers
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.sleep = sleep

    async def generate(self, request: ModelRequest) -> ModelResult:
        if request.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        project_scoped = bool(request.project_id and request.agent_run_id)
        clarification_scoped = bool(request.clarification_session_id)
        if project_scoped == clarification_scoped:
            raise ValueError(
                "model request must target either an agent run or a clarification session"
            )
        if clarification_scoped and (
            request.project_id is not None or request.agent_run_id is not None
        ):
            raise ValueError("clarification model request cannot target a project or agent run")
        try:
            definition = self.catalog.require_enabled(request.model_id)
        except ModelCatalogError as exc:
            code = (
                ModelErrorCode.MODEL_DISABLED
                if exc.code == "MODEL_DISABLED"
                else ModelErrorCode.MODEL_NOT_FOUND
            )
            raise ModelGatewayError(code, str(exc), retryable=False) from exc
        if ModelCapability.STRUCTURED_OUTPUT not in definition.capabilities:
            raise ModelGatewayError(
                ModelErrorCode.CAPABILITY_MISSING,
                "所选模型未声明结构化输出能力。",
                retryable=False,
            )

        credential = self.credentials.resolve(definition.credential_env)
        provider = self.providers.resolve(definition.provider)
        if credential is None:
            return await self._fail_without_invocation(
                request,
                definition.provider,
                definition.provider_model,
                ModelErrorCode.CREDENTIAL_MISSING,
                "模型凭据未配置。",
            )
        if provider is None:
            return await self._fail_without_invocation(
                request,
                definition.provider,
                definition.provider_model,
                ModelErrorCode.PROVIDER_NOT_BOUND,
                "模型 Provider 未绑定。",
            )

        provider_request = ProviderModelRequest(
            provider_model=definition.provider_model,
            credential=credential,
            messages=request.messages,
            response_schema=request.response_model.model_json_schema(),
            timeout_seconds=request.timeout_seconds,
            max_output_tokens=request.max_output_tokens,
            options={**definition.provider_options, **request.provider_options},
        )
        last_error: ModelGatewayError | None = None
        total_attempts = self.max_retries + 1
        for attempt_number in range(1, total_attempts + 1):
            call = await self._start_call(
                request,
                definition.provider,
                definition.provider_model,
                attempt_number,
            )
            started = perf_counter()
            try:
                async with asyncio.timeout(request.timeout_seconds):
                    provider_result = await provider.generate(provider_request)
                output = self._validate_output(request.response_model, provider_result)
                cost = self._estimate_cost(
                    provider_result.usage,
                    definition.input_cost_microusd_per_million_tokens,
                    definition.output_cost_microusd_per_million_tokens,
                )
                latency_ms = max(0, int((perf_counter() - started) * 1000))
                await self._complete_call(
                    call.model_call_id,
                    request.agent_run_id,
                    request,
                    provider_result,
                    cost,
                    latency_ms,
                )
                return ModelResult(
                    output=output,
                    model_id=definition.model_id,
                    provider=definition.provider,
                    usage=provider_result.usage,
                    estimated_cost_microusd=cost,
                    model_call_id=call.model_call_id,
                    attempt_count=attempt_number,
                )
            except TimeoutError as exc:
                last_error = ModelGatewayError(
                    ModelErrorCode.TIMEOUT,
                    "模型调用超过允许时间。",
                    retryable=True,
                    model_call_id=call.model_call_id,
                )
                await self._fail_call(call.model_call_id, last_error, started)
                if attempt_number >= total_attempts:
                    raise last_error from exc
            except ModelProviderError as exc:
                last_error = ModelGatewayError(
                    exc.code,
                    "模型 Provider 调用失败。",
                    retryable=exc.retryable,
                    model_call_id=call.model_call_id,
                )
                await self._fail_call(
                    call.model_call_id,
                    last_error,
                    started,
                    provider_request_id=exc.provider_request_id,
                )
                if not exc.retryable or attempt_number >= total_attempts:
                    raise last_error from exc
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                last_error = ModelGatewayError(
                    ModelErrorCode.STRUCTURED_OUTPUT_INVALID,
                    "模型输出无法通过结构化 Schema 校验。",
                    retryable=False,
                    model_call_id=call.model_call_id,
                )
                await self._fail_call(call.model_call_id, last_error, started)
                raise last_error from exc
            except asyncio.CancelledError as exc:
                last_error = ModelGatewayError(
                    ModelErrorCode.CANCELLED,
                    "模型调用已取消。",
                    retryable=False,
                    model_call_id=call.model_call_id,
                )
                await self._fail_call(call.model_call_id, last_error, started)
                raise last_error from exc
            except ModelGatewayError:
                raise
            except Exception as exc:
                last_error = ModelGatewayError(
                    ModelErrorCode.PROVIDER_FAILED,
                    "模型 Provider 调用失败。",
                    retryable=True,
                    model_call_id=call.model_call_id,
                )
                await self._fail_call(call.model_call_id, last_error, started)
                if attempt_number >= total_attempts:
                    raise last_error from exc

            await self.sleep(self.retry_base_seconds * (2 ** (attempt_number - 1)))

        if last_error is None:  # pragma: no cover - loop always produces a result or error
            raise RuntimeError("model gateway completed without a result")
        raise last_error

    async def _fail_without_invocation(
        self,
        request: ModelRequest,
        provider: str,
        provider_model: str,
        code: ModelErrorCode,
        message: str,
    ) -> ModelResult:
        call = await self._start_call(request, provider, provider_model, 1)
        error = ModelGatewayError(
            code,
            message,
            retryable=False,
            model_call_id=call.model_call_id,
        )
        await self._fail_call(call.model_call_id, error, perf_counter())
        raise error

    async def _start_call(
        self,
        request: ModelRequest,
        provider: str,
        provider_model: str,
        attempt_number: int,
    ) -> ModelCallModel:
        model = ModelCallModel(
            model_call_id=f"model_call_{uuid4().hex[:16]}",
            project_id=request.project_id,
            agent_run_id=request.agent_run_id,
            clarification_session_id=request.clarification_session_id,
            trace_id=request.trace_id,
            provider=provider,
            model_id=request.model_id,
            provider_model=provider_model,
            prompt_key=request.prompt_key,
            prompt_version=request.prompt_version,
            attempt_number=attempt_number,
            status="running",
            created_at=datetime.now(UTC),
        )
        async with self.database.session() as session:
            repository = ModelCallRepository(session)
            if request.agent_run_id is not None:
                await repository.require_run(request.agent_run_id)
            elif request.clarification_session_id is not None:
                await repository.require_clarification_session(
                    request.clarification_session_id
                )
            await repository.add(model)
            await repository.commit()
        return model

    async def _complete_call(
        self,
        model_call_id: str,
        agent_run_id: str | None,
        request: ModelRequest,
        result: ProviderModelResult,
        cost: int,
        latency_ms: int,
    ) -> None:
        async with self.database.session() as session:
            repository = ModelCallRepository(session)
            model = await repository.get(model_call_id)
            if model is None:
                raise RuntimeError("model call audit row is missing")
            model.status = "completed"
            model.input_tokens = result.usage.input_tokens
            model.output_tokens = result.usage.output_tokens
            model.estimated_cost_microusd = cost
            model.latency_ms = latency_ms
            model.provider_request_id = result.provider_request_id
            model.completed_at = datetime.now(UTC)
            if agent_run_id is not None:
                run = await repository.require_run(agent_run_id)
                run.model_id = model.model_id
                run.model_provider = model.provider
                run.prompt_key = request.prompt_key
                run.prompt_version = request.prompt_version
                run.input_tokens += result.usage.input_tokens
                run.output_tokens += result.usage.output_tokens
                run.estimated_cost_microusd += cost
            elif request.clarification_session_id is not None:
                clarification = await repository.require_clarification_session(
                    request.clarification_session_id
                )
                clarification.input_tokens += result.usage.input_tokens
                clarification.output_tokens += result.usage.output_tokens
                clarification.estimated_cost_microusd += cost
            await repository.commit()

    async def _fail_call(
        self,
        model_call_id: str,
        error: ModelGatewayError,
        started: float,
        *,
        provider_request_id: str | None = None,
    ) -> None:
        async with self.database.session() as session:
            repository = ModelCallRepository(session)
            model = await repository.get(model_call_id)
            if model is None:
                raise RuntimeError("model call audit row is missing")
            model.status = "failed"
            model.error_code = error.code
            model.error_message = str(error)
            model.retryable = error.retryable
            model.provider_request_id = provider_request_id
            model.latency_ms = max(0, int((perf_counter() - started) * 1000))
            model.completed_at = datetime.now(UTC)
            await repository.commit()

    @staticmethod
    def _validate_output(response_model: type[BaseModel], result: ProviderModelResult) -> BaseModel:
        payload = result.output
        if isinstance(payload, str):
            payload = json.loads(payload)
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        return response_model.model_validate(payload)

    @staticmethod
    def _estimate_cost(
        usage: ModelUsage,
        input_rate: int | None,
        output_rate: int | None,
    ) -> int:
        def calculate(tokens: int, rate: int | None) -> int:
            if rate is None or tokens == 0:
                return 0
            return (tokens * rate + 999_999) // 1_000_000

        return calculate(usage.input_tokens, input_rate) + calculate(
            usage.output_tokens, output_rate
        )
