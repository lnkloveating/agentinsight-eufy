import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.schemas.search_discovery import SearchDiscoveryCreate
from app.sources.search_discovery import (
    SearchDiscoveryProviderError,
    SearchDiscoveryProviderRequest,
    TavilySearchDiscoveryConnector,
)


def test_tavily_connector_sends_bounded_search_request_and_parses_candidates() -> None:
    captured: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "request_id": "tavily-request-1",
                "results": [
                    {
                        "title": "eufy E340 official page",
                        "url": "https://www.eufy.com/products/e340",
                        "content": "Official product page candidate.",
                        "score": 0.91,
                    },
                    {"title": "missing URL"},
                ],
            },
        )

    connector = TavilySearchDiscoveryConnector(
        "tvly-secret",
        transport=httpx.MockTransport(handle),
    )
    response = asyncio.run(
        connector.search(
            SearchDiscoveryProviderRequest(
                query="eufy E340 official product page",
                max_results=5,
                include_domains=("eufy.com",),
                exclude_domains=("support.eufy.com",),
            )
        )
    )

    assert connector.available is True
    assert connector.unavailable_reason is None
    assert response.provider_request_id == "tavily-request-1"
    assert len(response.candidates) == 1
    assert response.candidates[0].score == 0.91
    assert len(captured) == 1
    assert captured[0].url == "https://api.tavily.com/search"
    assert captured[0].headers["authorization"] == "Bearer tvly-secret"
    payload = json.loads(captured[0].content)
    assert payload == {
        "query": "eufy E340 official product page",
        "search_depth": "basic",
        "topic": "general",
        "max_results": 5,
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_domains": ["eufy.com"],
        "exclude_domains": ["support.eufy.com"],
    }


@pytest.mark.parametrize(
    ("status_code", "expected_code", "blocked", "retryable"),
    [
        (401, "SEARCH_AUTHENTICATION_FAILED", True, False),
        (429, "SEARCH_RATE_LIMITED", False, True),
        (503, "SEARCH_PROVIDER_UNAVAILABLE", False, True),
        (400, "SEARCH_REQUEST_REJECTED", True, False),
    ],
)
def test_tavily_connector_classifies_provider_failures(
    status_code: int,
    expected_code: str,
    blocked: bool,
    retryable: bool,
) -> None:
    connector = TavilySearchDiscoveryConnector(
        "tvly-secret",
        transport=httpx.MockTransport(lambda request: httpx.Response(status_code)),
    )

    with pytest.raises(SearchDiscoveryProviderError) as error:
        asyncio.run(
            connector.search(
                SearchDiscoveryProviderRequest(query="smart doorbell", max_results=3)
            )
        )

    assert error.value.code == expected_code
    assert error.value.blocked is blocked
    assert error.value.retryable is retryable


def test_tavily_connector_requires_local_credential_without_exposing_it() -> None:
    connector = TavilySearchDiscoveryConnector(None)

    assert connector.available is False
    assert connector.unavailable_reason == "SEARCH_CREDENTIAL_MISSING"
    with pytest.raises(SearchDiscoveryProviderError) as error:
        asyncio.run(
            connector.search(
                SearchDiscoveryProviderRequest(query="smart doorbell", max_results=3)
            )
        )
    assert error.value.code == "SEARCH_CREDENTIAL_MISSING"
    assert error.value.blocked is True


def test_tavily_connector_rejects_response_over_streaming_limit() -> None:
    connector = TavilySearchDiscoveryConnector(
        "tvly-secret",
        max_response_bytes=32,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 33)
        ),
    )

    with pytest.raises(SearchDiscoveryProviderError) as error:
        asyncio.run(
            connector.search(
                SearchDiscoveryProviderRequest(query="smart doorbell", max_results=3)
            )
        )

    assert error.value.code == "SEARCH_RESPONSE_TOO_LARGE"
    assert error.value.blocked is True


@pytest.mark.parametrize(
    "payload",
    [
        {"include_domains": ["https://eufy.com"]},
        {"include_domains": ["127.0.0.1"]},
        {"include_domains": ["bad host.com"]},
        {"include_domains": ["eufy.com", "EUFY.com"]},
        {"include_domains": ["eufy.com"], "exclude_domains": ["eufy.com"]},
    ],
)
def test_search_request_rejects_unsafe_or_conflicting_domain_filters(
    payload: dict[str, list[str]],
) -> None:
    with pytest.raises(ValidationError):
        SearchDiscoveryCreate.model_validate(
            {
                "query": "eufy smart doorbell competitors",
                "intent": "competitor_candidate",
                "requested_by": "researcher",
                "purpose": "Discover candidate sources only.",
                **payload,
            }
        )
