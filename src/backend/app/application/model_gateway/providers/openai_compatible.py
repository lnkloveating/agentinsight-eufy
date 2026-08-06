"""OpenAI-compatible Chat Completions Provider。"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from app.application.model_gateway.contracts import (
    ModelErrorCode,
    ModelProviderError,
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)

_FORWARDED_OPTIONS = {
    "temperature",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
    "seed",
    "stop",
}


class OpenAICompatibleProviderConfig(BaseModel):
    provider_id: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=8, max_length=500)

    @field_validator("provider_id")
    @classmethod
    def normalize_provider_id(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("https://", "http://")):
            raise ValueError("base_url must be HTTP or HTTPS")
        return normalized


def parse_openai_compatible_provider_configs(
    raw_config: str,
) -> list[OpenAICompatibleProviderConfig]:
    try:
        payload = json.loads(raw_config or "[]")
        return TypeAdapter(list[OpenAICompatibleProviderConfig]).validate_python(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("OPENAI_COMPATIBLE_PROVIDERS_JSON is invalid") from exc


class OpenAICompatibleProvider:
    def __init__(
        self,
        provider_id: str,
        base_url: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        config = OpenAICompatibleProviderConfig(
            provider_id=provider_id, base_url=base_url
        )
        self._provider_id = config.provider_id
        self.base_url = config.base_url
        self._client = client

    @property
    def provider_id(self) -> str:
        return self._provider_id

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        payload = self._payload(request)
        headers = {
            "Authorization": f"Bearer {request.credential}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=request.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=request.timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise ModelProviderError(
                ModelErrorCode.TIMEOUT,
                "OpenAI-compatible request timed out",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise ModelProviderError(
                ModelErrorCode.PROVIDER_FAILED,
                "OpenAI-compatible network request failed",
                retryable=True,
            ) from exc

        provider_request_id = response.headers.get("x-request-id")
        if response.status_code in {401, 403}:
            raise ModelProviderError(
                ModelErrorCode.AUTHENTICATION_FAILED,
                "OpenAI-compatible authentication failed",
                retryable=False,
                provider_request_id=provider_request_id,
            )
        if response.status_code == 429:
            raise ModelProviderError(
                ModelErrorCode.RATE_LIMITED,
                "OpenAI-compatible provider rate limited the request",
                retryable=True,
                provider_request_id=provider_request_id,
            )
        if response.status_code >= 500:
            raise ModelProviderError(
                ModelErrorCode.PROVIDER_FAILED,
                "OpenAI-compatible provider is unavailable",
                retryable=True,
                provider_request_id=provider_request_id,
            )
        if response.status_code >= 400:
            raise ModelProviderError(
                ModelErrorCode.PROVIDER_FAILED,
                "OpenAI-compatible provider rejected the request",
                retryable=False,
                provider_request_id=provider_request_id,
            )

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            usage_payload = body.get("usage") or {}
            usage = ModelUsage(
                input_tokens=int(usage_payload.get("prompt_tokens", 0)),
                output_tokens=int(usage_payload.get("completion_tokens", 0)),
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelProviderError(
                ModelErrorCode.PROVIDER_FAILED,
                "OpenAI-compatible response shape is invalid",
                retryable=False,
                provider_request_id=provider_request_id,
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderError(
                ModelErrorCode.PROVIDER_FAILED,
                "OpenAI-compatible response content is empty",
                retryable=False,
                provider_request_id=provider_request_id,
            )
        return ProviderModelResult(
            output=self._strip_markdown_fence(content),
            usage=usage,
            provider_request_id=str(body.get("id") or provider_request_id or "") or None,
        )

    @staticmethod
    def _payload(request: ProviderModelRequest) -> dict[str, Any]:
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ]
        structured_output_mode = str(
            request.options.get("structured_output_mode", "json_schema")
        )
        payload: dict[str, Any] = {
            "model": request.provider_model,
            "messages": messages,
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        for key in _FORWARDED_OPTIONS:
            if key in request.options:
                payload[key] = request.options[key]
        if structured_output_mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        elif structured_output_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        elif structured_output_mode == "prompt":
            payload["messages"] = [
                *messages,
                {
                    "role": "system",
                    "content": (
                        "Return only one JSON object matching this JSON Schema: "
                        + json.dumps(
                            request.response_schema, ensure_ascii=False, sort_keys=True
                        )
                    ),
                },
            ]
        else:
            raise ModelProviderError(
                ModelErrorCode.PROVIDER_FAILED,
                "unsupported structured output mode",
                retryable=False,
            )
        return payload

    @staticmethod
    def _strip_markdown_fence(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```json") and stripped.endswith("```"):
            return stripped[7:-3].strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            return stripped[3:-3].strip()
        return stripped
