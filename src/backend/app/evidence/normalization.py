"""不依赖 LLM 的证据规范化与内容指纹规则。"""

import re
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class NormalizedEvidenceSource:
    source_url: str
    source_domain: str
    content_hash: str


def normalize_url(raw_url: str) -> tuple[str, str]:
    """规范 HTTP(S) URL，并移除不影响来源内容的跟踪参数。"""
    parsed = urlsplit(raw_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Evidence source URL must use HTTP or HTTPS")

    hostname = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
    if hostname.startswith("www."):
        hostname = hostname[4:]

    port = parsed.port
    include_port = port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    )
    netloc = f"{hostname}:{port}" if include_port else hostname
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    normalized_query = urlencode(sorted(query_items))
    normalized_url = urlunsplit((scheme, netloc, path, normalized_query, ""))
    return normalized_url, hostname


def normalize_excerpt(excerpt: str) -> str:
    """统一 Unicode 和空白，保留原始语义用于稳定去重。"""
    normalized = unicodedata.normalize("NFKC", excerpt)
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def build_content_hash(excerpt: str) -> str:
    """对规范化后的引用正文生成稳定 SHA-256 指纹。"""
    canonical_excerpt = normalize_excerpt(excerpt).casefold()
    return sha256(canonical_excerpt.encode("utf-8")).hexdigest()


def normalize_evidence_source(raw_url: str, excerpt: str) -> NormalizedEvidenceSource:
    normalized_url, domain = normalize_url(raw_url)
    return NormalizedEvidenceSource(
        source_url=normalized_url,
        source_domain=domain,
        content_hash=build_content_hash(excerpt),
    )
