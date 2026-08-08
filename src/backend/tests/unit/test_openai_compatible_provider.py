import json

import httpx
import pytest

from app.application.model_gateway import (
    ModelErrorCode,
    ModelMessage,
    ModelProviderError,
    OpenAICompatibleProvider,
    ProviderModelRequest,
    parse_openai_compatible_provider_configs,
)


def _request() -> ProviderModelRequest:
    return ProviderModelRequest(
        provider_model="provider/model-a",
        credential="unit-test-credential",
        messages=(ModelMessage(role="user", content="Return JSON."),),
        response_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
        timeout_seconds=1,
        max_output_tokens=128,
        options={
            "structured_output_mode": "prompt",
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "reasoning_effort": "none",
        },
    )


@pytest.mark.asyncio
async def test_openai_compatible_provider_builds_safe_request_and_parses_usage() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "provider-request",
                "choices": [
                    {
                        "message": {
                            "content": "```json\n{\"answer\":\"ok\"}\n```"
                        }
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            "test-router", "https://router.example.com/", client=client
        )
        result = await provider.generate(_request())

    assert captured["url"] == "https://router.example.com/chat/completions"
    assert captured["authorization"] == "Bearer unit-test-credential"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "provider/model-a"
    assert payload["max_tokens"] == 128
    assert payload["temperature"] == 0
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["reasoning_effort"] == "none"
    assert "JSON Schema" in payload["messages"][-1]["content"]
    assert result.output == '{"answer":"ok"}'
    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (401, ModelErrorCode.AUTHENTICATION_FAILED, False),
        (429, ModelErrorCode.RATE_LIMITED, True),
        (503, ModelErrorCode.PROVIDER_FAILED, True),
    ],
)
async def test_openai_compatible_provider_classifies_http_errors(
    status_code: int,
    expected_code: ModelErrorCode,
    retryable: bool,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "must not be persisted"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            "test-router", "https://router.example.com", client=client
        )
        with pytest.raises(ModelProviderError) as error:
            await provider.generate(_request())

    assert error.value.code is expected_code
    assert error.value.retryable is retryable
    assert "must not be persisted" not in str(error.value)


def test_parse_openai_compatible_provider_configs() -> None:
    configs = parse_openai_compatible_provider_configs(
        '[{"provider_id":"Anker-Router","base_url":"https://router.example.com/"}]'
    )

    assert configs[0].provider_id == "anker-router"
    assert configs[0].base_url == "https://router.example.com"
    with pytest.raises(ValueError, match="OPENAI_COMPATIBLE_PROVIDERS_JSON"):
        parse_openai_compatible_provider_configs("not-json")


@pytest.mark.asyncio
async def test_empty_provider_content_is_retryable() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"id": "empty-request", "choices": [{"message": {"content": ""}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            "test-router", "https://router.example.com", client=client
        )
        with pytest.raises(ModelProviderError) as error:
            await provider.generate(_request())

    assert error.value.code is ModelErrorCode.PROVIDER_FAILED
    assert error.value.retryable is True
