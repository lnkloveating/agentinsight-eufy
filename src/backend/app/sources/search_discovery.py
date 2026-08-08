"""可替换的搜索 Provider 契约与 Tavily 实现。"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class SearchDiscoveryProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        blocked: bool,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.blocked = blocked
        self.retryable = retryable


@dataclass(frozen=True)
class SearchDiscoveryProviderRequest:
    query: str
    max_results: int
    include_domains: tuple[str, ...] = ()
    exclude_domains: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchDiscoveryProviderCandidate:
    title: str
    source_url: str
    snippet: str
    score: float | None = None


@dataclass(frozen=True)
class SearchDiscoveryProviderResponse:
    candidates: tuple[SearchDiscoveryProviderCandidate, ...]
    provider_request_id: str | None = None


class SearchDiscoveryConnector(Protocol):
    provider_id: str

    @property
    def available(self) -> bool: ...

    @property
    def unavailable_reason(self) -> str | None: ...

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse: ...


class SearchDiscoveryRegistry:
    """只解析显式注册的搜索 Provider，不接受任意 URL 或执行器。"""

    def __init__(self, connectors: tuple[SearchDiscoveryConnector, ...] = ()) -> None:
        self._connectors: dict[str, SearchDiscoveryConnector] = {}
        for connector in connectors:
            self.register(connector)

    def register(self, connector: SearchDiscoveryConnector) -> None:
        if connector.provider_id in self._connectors:
            raise ValueError(f"duplicate search discovery provider: {connector.provider_id}")
        self._connectors[connector.provider_id] = connector

    def resolve(self, provider_id: str) -> SearchDiscoveryConnector | None:
        return self._connectors.get(provider_id)


class TavilySearchDiscoveryConnector:
    """通过 Tavily Search API 发现候选 URL，不调用 Extract 或 Crawl。"""

    provider_id = "tavily"

    def __init__(
        self,
        api_key: str | None,
        *,
        enabled: bool = True,
        base_url: str = "https://api.tavily.com",
        timeout_seconds: float = 20,
        max_response_bytes: int = 1_048_576,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key else None
        self._enabled = enabled
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    @property
    def available(self) -> bool:
        return self._enabled and self._api_key is not None

    @property
    def unavailable_reason(self) -> str | None:
        if not self._enabled:
            return "SEARCH_PROVIDER_DISABLED"
        if self._api_key is None:
            return "SEARCH_CREDENTIAL_MISSING"
        return None

    async def search(
        self, request: SearchDiscoveryProviderRequest
    ) -> SearchDiscoveryProviderResponse:
        if not self.available:
            raise SearchDiscoveryProviderError(
                self.unavailable_reason or "SEARCH_PROVIDER_UNAVAILABLE",
                "搜索 Provider 未启用或缺少本地凭据。",
                blocked=True,
            )
        payload: dict[str, Any] = {
            "query": request.query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": request.max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }
        if request.include_domains:
            payload["include_domains"] = list(request.include_domains)
        if request.exclude_domains:
            payload["exclude_domains"] = list(request.exclude_domains)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout_seconds),
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/search",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise SearchDiscoveryProviderError(
                "SEARCH_PROVIDER_TIMEOUT",
                "搜索 Provider 请求超时。",
                blocked=False,
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise SearchDiscoveryProviderError(
                "SEARCH_PROVIDER_NETWORK_ERROR",
                "搜索 Provider 网络请求失败。",
                blocked=False,
                retryable=True,
            ) from exc
        if len(response.content) > self._max_response_bytes:
            raise SearchDiscoveryProviderError(
                "SEARCH_RESPONSE_TOO_LARGE",
                "搜索 Provider 响应超过安全大小限制。",
                blocked=True,
            )
        self._raise_for_status(response.status_code)
        try:
            body = response.json()
        except ValueError as exc:
            raise SearchDiscoveryProviderError(
                "SEARCH_RESPONSE_INVALID",
                "搜索 Provider 返回了无效 JSON。",
                blocked=False,
            ) from exc
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise SearchDiscoveryProviderError(
                "SEARCH_RESPONSE_INVALID",
                "搜索 Provider 响应缺少 results 数组。",
                blocked=False,
            )
        candidates: list[SearchDiscoveryProviderCandidate] = []
        for item in body["results"][: request.max_results]:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            source_url = item.get("url")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(source_url, str) or not source_url.strip():
                continue
            content = item.get("content")
            score_value = item.get("score")
            score = (
                float(score_value)
                if isinstance(score_value, int | float) and 0 <= float(score_value) <= 1
                else None
            )
            candidates.append(
                SearchDiscoveryProviderCandidate(
                    title=title.strip(),
                    source_url=source_url.strip(),
                    snippet=content.strip() if isinstance(content, str) else "",
                    score=score,
                )
            )
        request_id = body.get("request_id")
        return SearchDiscoveryProviderResponse(
            candidates=tuple(candidates),
            provider_request_id=request_id if isinstance(request_id, str) else None,
        )

    @staticmethod
    def _raise_for_status(status_code: int) -> None:
        if status_code < 400:
            return
        if status_code in {401, 403}:
            raise SearchDiscoveryProviderError(
                "SEARCH_AUTHENTICATION_FAILED",
                "搜索 Provider 拒绝了本地凭据。",
                blocked=True,
            )
        if status_code == 429:
            raise SearchDiscoveryProviderError(
                "SEARCH_RATE_LIMITED",
                "搜索 Provider 已达到速率或额度限制。",
                blocked=False,
                retryable=True,
            )
        if status_code >= 500:
            raise SearchDiscoveryProviderError(
                "SEARCH_PROVIDER_UNAVAILABLE",
                "搜索 Provider 暂时不可用。",
                blocked=False,
                retryable=True,
            )
        raise SearchDiscoveryProviderError(
            "SEARCH_REQUEST_REJECTED",
            "搜索 Provider 拒绝了请求参数。",
            blocked=True,
        )
