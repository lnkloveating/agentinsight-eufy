import asyncio
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from ipaddress import ip_address
from typing import Protocol, cast
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.core.errors import AppError
from app.sources.validation import normalize_public_url

_HTML_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_CHARSET_PATTERN = re.compile(rb"charset\s*=\s*[\"']?([a-zA-Z0-9._-]+)", re.I)
_PASSWORD_INPUT_PATTERN = re.compile(r"<input\b[^>]*\btype\s*=\s*['\"]?password\b", re.I)


class WebConnectorError(Exception):
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
class WebFetchResult:
    requested_url: str
    final_url: str
    media_type: str
    status_code: int
    body_utf8: bytes
    fetched_at: datetime
    etag: str | None = None
    last_modified: str | None = None


class WebConnector(Protocol):
    async def fetch(self, source_url: str) -> WebFetchResult: ...


class HostResolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]: ...


class SystemHostResolver:
    async def resolve(self, hostname: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        try:
            records = await loop.getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise WebConnectorError(
                "WEB_DNS_RESOLUTION_FAILED",
                "The webpage hostname could not be resolved.",
                blocked=False,
                retryable=True,
            ) from exc
        addresses = tuple(sorted({str(record[4][0]) for record in records}))
        if not addresses:
            raise WebConnectorError(
                "WEB_DNS_RESOLUTION_FAILED",
                "The webpage hostname did not resolve to an address.",
                blocked=False,
                retryable=True,
            )
        return addresses


@dataclass(frozen=True)
class _HttpSnapshot:
    status_code: int
    headers: httpx.Headers
    body: bytes


class SafeHttpWebConnector:
    """Fetches one authorized public page without browser or anti-bot bypass."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float,
        max_response_bytes: int,
        max_redirects: int,
        respect_robots_txt: bool,
        allowed_domains: tuple[str, ...] = (),
        resolver: HostResolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.respect_robots_txt = respect_robots_txt
        self.allowed_domains = tuple(
            domain.strip().rstrip(".").lower() for domain in allowed_domains if domain.strip()
        )
        self.resolver = resolver or SystemHostResolver()
        self.transport = transport

    async def fetch(self, source_url: str) -> WebFetchResult:
        requested_url = self._normalize_url(source_url)
        current_url = requested_url
        checked_robot_origins: set[str] = set()
        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                for redirect_count in range(self.max_redirects + 1):
                    await self._validate_destination(current_url)
                    origin = self._origin(current_url)
                    if self.respect_robots_txt and origin not in checked_robot_origins:
                        await self._check_robots(client, current_url)
                        checked_robot_origins.add(origin)
                    snapshot = await self._get_bounded(client, current_url, self.max_response_bytes)
                    if snapshot.status_code in _REDIRECT_STATUSES:
                        if redirect_count >= self.max_redirects:
                            raise WebConnectorError(
                                "WEB_REDIRECT_LIMIT_EXCEEDED",
                                "The webpage exceeded the allowed redirect limit.",
                                blocked=True,
                            )
                        location = snapshot.headers.get("location")
                        if not location:
                            raise WebConnectorError(
                                "WEB_REDIRECT_INVALID",
                                "The webpage returned a redirect without a location.",
                                blocked=True,
                            )
                        current_url = self._normalize_url(urljoin(current_url, location))
                        continue
                    self._validate_status(snapshot.status_code)
                    media_type = self._media_type(snapshot.headers)
                    if media_type not in _HTML_MEDIA_TYPES:
                        raise WebConnectorError(
                            "WEB_CONTENT_TYPE_UNSUPPORTED",
                            "The URL did not return an HTML document.",
                            blocked=True,
                        )
                    body_utf8 = self._normalize_html(snapshot.body, snapshot.headers)
                    if self._looks_like_login_page(body_utf8):
                        raise WebConnectorError(
                            "WEB_AUTHENTICATION_REQUIRED",
                            "The URL returned a login page instead of public research content.",
                            blocked=True,
                        )
                    if not body_utf8.strip():
                        raise WebConnectorError(
                            "WEB_CONTENT_EMPTY",
                            "The webpage response was empty.",
                            blocked=True,
                        )
                    return WebFetchResult(
                        requested_url=requested_url,
                        final_url=current_url,
                        media_type="text/html",
                        status_code=snapshot.status_code,
                        body_utf8=body_utf8,
                        fetched_at=datetime.now(UTC),
                        etag=snapshot.headers.get("etag"),
                        last_modified=snapshot.headers.get("last-modified"),
                    )
                raise WebConnectorError(
                    "WEB_REDIRECT_LIMIT_EXCEEDED",
                    "The webpage exceeded the allowed redirect limit.",
                    blocked=True,
                )
        except WebConnectorError:
            raise
        except httpx.TimeoutException as exc:
            raise WebConnectorError(
                "WEB_FETCH_TIMEOUT",
                "The webpage fetch timed out.",
                blocked=False,
                retryable=True,
            ) from exc
        except httpx.TransportError as exc:
            raise WebConnectorError(
                "WEB_FETCH_TRANSPORT_ERROR",
                "The webpage could not be fetched.",
                blocked=False,
                retryable=True,
            ) from exc

    async def _check_robots(self, client: httpx.AsyncClient, target_url: str) -> None:
        robots_url = f"{self._origin(target_url)}/robots.txt"
        current_url = robots_url
        for redirect_count in range(self.max_redirects + 1):
            await self._validate_destination(current_url)
            snapshot = await self._get_bounded(
                client, current_url, min(self.max_response_bytes, 524_288)
            )
            if snapshot.status_code in _REDIRECT_STATUSES:
                if redirect_count >= self.max_redirects:
                    raise WebConnectorError(
                        "WEB_ROBOTS_CHECK_FAILED",
                        "The website robots policy exceeded the allowed redirect limit.",
                        blocked=True,
                    )
                location = snapshot.headers.get("location")
                if not location:
                    raise WebConnectorError(
                        "WEB_ROBOTS_CHECK_FAILED",
                        "The website robots policy returned an invalid redirect.",
                        blocked=True,
                    )
                current_url = self._normalize_url(urljoin(current_url, location))
                continue
            if snapshot.status_code in {404, 410}:
                return
            if snapshot.status_code != 200:
                raise WebConnectorError(
                    "WEB_ROBOTS_CHECK_FAILED",
                    "The website robots policy could not be verified.",
                    blocked=True,
                )
            try:
                robots_text = snapshot.body.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise WebConnectorError(
                    "WEB_ROBOTS_CHECK_FAILED",
                    "The website robots policy encoding is unsupported.",
                    blocked=True,
                ) from exc
            parser = RobotFileParser()
            parser.set_url(current_url)
            parser.parse(robots_text.splitlines())
            if not parser.can_fetch(self.user_agent, target_url):
                raise WebConnectorError(
                    "WEB_ROBOTS_DISALLOWED",
                    "The website robots policy disallows this fetch.",
                    blocked=True,
                )
            return
        raise WebConnectorError(
            "WEB_ROBOTS_CHECK_FAILED",
            "The website robots policy exceeded the allowed redirect limit.",
            blocked=True,
        )

    async def _validate_destination(self, source_url: str) -> None:
        normalized = self._normalize_url(source_url)
        parts = urlsplit(normalized)
        hostname = parts.hostname
        if hostname is None:
            raise WebConnectorError(
                "WEB_URL_INVALID",
                "The webpage URL is invalid.",
                blocked=True,
            )
        if self.allowed_domains and not any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in self.allowed_domains
        ):
            raise WebConnectorError(
                "WEB_DOMAIN_NOT_ALLOWED",
                "The webpage domain is not in the configured allowlist.",
                blocked=True,
            )
        port = parts.port or (443 if parts.scheme == "https" else 80)
        addresses = await self.resolver.resolve(hostname, port)
        for address in addresses:
            try:
                parsed_address = ip_address(address.split("%", 1)[0])
            except ValueError as exc:
                raise WebConnectorError(
                    "WEB_DNS_ADDRESS_INVALID",
                    "The webpage hostname resolved to an invalid address.",
                    blocked=True,
                ) from exc
            if not parsed_address.is_global:
                raise WebConnectorError(
                    "WEB_PRIVATE_NETWORK_FORBIDDEN",
                    "The webpage hostname resolved to a private or reserved address.",
                    blocked=True,
                )

    async def _get_bounded(
        self, client: httpx.AsyncClient, source_url: str, max_bytes: int
    ) -> _HttpSnapshot:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        }
        async with client.stream("GET", source_url, headers=headers) as response:
            declared_size = response.headers.get("content-length")
            if declared_size is not None:
                try:
                    if int(declared_size) > max_bytes:
                        self._raise_too_large()
                except ValueError:
                    pass
            chunks: list[bytes] = []
            total = 0
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    self._raise_too_large()
                chunks.append(chunk)
            return _HttpSnapshot(response.status_code, response.headers, b"".join(chunks))

    @staticmethod
    def _validate_status(status_code: int) -> None:
        if 200 <= status_code < 300:
            return
        if status_code in {401, 403}:
            raise WebConnectorError(
                "WEB_ACCESS_RESTRICTED",
                "The webpage requires access that the connector does not have.",
                blocked=True,
            )
        if status_code == 429 or status_code >= 500:
            raise WebConnectorError(
                "WEB_FETCH_RETRYABLE_STATUS",
                f"The webpage returned retryable HTTP status {status_code}.",
                blocked=False,
                retryable=True,
            )
        raise WebConnectorError(
            "WEB_FETCH_REJECTED",
            f"The webpage returned HTTP status {status_code}.",
            blocked=True,
        )

    @staticmethod
    def _media_type(headers: httpx.Headers) -> str:
        value = cast(str, headers.get("content-type", ""))
        return value.split(";", 1)[0].strip().lower()

    @classmethod
    def _normalize_html(cls, body: bytes, headers: httpx.Headers) -> bytes:
        charset = cls._header_charset(headers)
        if charset is None:
            match = _CHARSET_PATTERN.search(body[:4096])
            charset = match.group(1).decode("ascii") if match is not None else "utf-8"
        try:
            return body.decode(charset).encode("utf-8")
        except (LookupError, UnicodeDecodeError) as exc:
            raise WebConnectorError(
                "WEB_ENCODING_UNSUPPORTED",
                "The webpage character encoding is unsupported or invalid.",
                blocked=True,
            ) from exc

    @staticmethod
    def _header_charset(headers: httpx.Headers) -> str | None:
        value = headers.get("content-type")
        if value is None:
            return None
        message = Message()
        message["content-type"] = value
        return message.get_content_charset()

    @staticmethod
    def _looks_like_login_page(body_utf8: bytes) -> bool:
        text = body_utf8.decode("utf-8", errors="strict")
        return _PASSWORD_INPUT_PATTERN.search(text) is not None

    @staticmethod
    def _origin(source_url: str) -> str:
        parts = urlsplit(source_url)
        return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")

    @staticmethod
    def _raise_too_large() -> None:
        raise WebConnectorError(
            "WEB_RESPONSE_TOO_LARGE",
            "The webpage exceeded the configured response size limit.",
            blocked=True,
        )

    @staticmethod
    def _normalize_url(source_url: str) -> str:
        try:
            return normalize_public_url(source_url)
        except AppError as exc:
            code = (
                "WEB_PRIVATE_NETWORK_FORBIDDEN"
                if exc.code == "SOURCE_URL_PRIVATE_NETWORK_FORBIDDEN"
                else "WEB_URL_INVALID"
            )
            raise WebConnectorError(
                code,
                "The webpage URL is not an authorized public HTTP or HTTPS address.",
                blocked=True,
            ) from exc
