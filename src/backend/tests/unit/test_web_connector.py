import asyncio

import httpx
import pytest

from app.sources.web_connector import SafeHttpWebConnector, WebConnectorError


class Resolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]] | None = None) -> None:
        self.addresses = addresses or {}

    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        del port
        return self.addresses.get(hostname, ("93.184.216.34",))


def _connector(
    handler: httpx.MockTransport,
    *,
    resolver: Resolver | None = None,
    max_response_bytes: int = 4096,
    max_redirects: int = 2,
    allowed_domains: tuple[str, ...] = (),
) -> SafeHttpWebConnector:
    return SafeHttpWebConnector(
        user_agent="AgentInsightResearchBot/0.1",
        timeout_seconds=2,
        max_response_bytes=max_response_bytes,
        max_redirects=max_redirects,
        respect_robots_txt=True,
        allowed_domains=allowed_domains,
        resolver=resolver or Resolver(),
        transport=handler,
    )


def test_fetches_public_html_after_robots_check_and_normalizes_encoding() -> None:
    requested_paths: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200,
            headers={
                "content-type": "text/html; charset=gb18030",
                "etag": '"capture-v1"',
            },
            content="<html><body>包裹已送达</body></html>".encode("gb18030"),
        )

    result = asyncio.run(
        _connector(httpx.MockTransport(handle)).fetch(
            "https://example.com/product?utm_source=test"
        )
    )

    assert requested_paths == ["/robots.txt", "/product"]
    assert result.requested_url == "https://example.com/product"
    assert result.final_url == "https://example.com/product"
    assert result.body_utf8.decode() == "<html><body>包裹已送达</body></html>"
    assert result.etag == '"capture-v1"'


def test_follows_public_robots_and_page_redirects_without_bypassing_policy() -> None:
    requested: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == "http://public.example/robots.txt":
            return httpx.Response(301, headers={"location": "https://public.example/robots.txt"})
        if str(request.url) == "https://public.example/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if str(request.url) == "http://public.example/product":
            return httpx.Response(301, headers={"location": "https://public.example/product"})
        return httpx.Response(
            200,
            text="<html><body>Public product page</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    result = asyncio.run(
        _connector(httpx.MockTransport(handle)).fetch("http://public.example/product")
    )

    assert result.final_url == "https://public.example/product"
    assert requested == [
        "http://public.example/robots.txt",
        "https://public.example/robots.txt",
        "http://public.example/product",
        "https://public.example/robots.txt",
        "https://public.example/product",
    ]


def test_robots_disallow_blocks_page_fetch() -> None:
    requested_paths: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")

    with pytest.raises(WebConnectorError) as error:
        asyncio.run(
            _connector(httpx.MockTransport(handle)).fetch(
                "https://example.com/private/research"
            )
        )

    assert error.value.code == "WEB_ROBOTS_DISALLOWED"
    assert error.value.blocked is True
    assert requested_paths == ["/robots.txt"]


def test_redirect_destination_is_revalidated_before_request() -> None:
    requested_hosts: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(302, headers={"location": "http://internal.test/secret"})

    resolver = Resolver(
        {
            "example.com": ("93.184.216.34",),
            "internal.test": ("127.0.0.1",),
        }
    )
    with pytest.raises(WebConnectorError) as error:
        asyncio.run(
            _connector(httpx.MockTransport(handle), resolver=resolver).fetch(
                "https://example.com/start"
            )
        )

    assert error.value.code == "WEB_PRIVATE_NETWORK_FORBIDDEN"
    assert requested_hosts == ["example.com", "example.com"]


@pytest.mark.parametrize(
    ("page_response", "expected_code", "blocked", "retryable"),
    [
        (
            httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf"),
            "WEB_CONTENT_TYPE_UNSUPPORTED",
            True,
            False,
        ),
        (httpx.Response(429), "WEB_FETCH_RETRYABLE_STATUS", False, True),
        (
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text='<form><input type="password"></form>',
            ),
            "WEB_AUTHENTICATION_REQUIRED",
            True,
            False,
        ),
    ],
)
def test_rejects_unsupported_or_unavailable_pages(
    page_response: httpx.Response,
    expected_code: str,
    blocked: bool,
    retryable: bool,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return page_response

    with pytest.raises(WebConnectorError) as error:
        asyncio.run(
            _connector(httpx.MockTransport(handle)).fetch("https://example.com/page")
        )

    assert error.value.code == expected_code
    assert error.value.blocked is blocked
    assert error.value.retryable is retryable


def test_rejects_decompressed_response_over_limit() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"x" * 129,
        )

    with pytest.raises(WebConnectorError) as error:
        asyncio.run(
            _connector(
                httpx.MockTransport(handle), max_response_bytes=128
            ).fetch("https://example.com/page")
        )

    assert error.value.code == "WEB_RESPONSE_TOO_LARGE"


def test_optional_domain_allowlist_is_enforced_before_network() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404)

    with pytest.raises(WebConnectorError) as error:
        asyncio.run(
            _connector(
                httpx.MockTransport(handle), allowed_domains=("eufy.com",)
            ).fetch("https://example.com/page")
        )

    assert error.value.code == "WEB_DOMAIN_NOT_ALLOWED"
    assert requests == []
