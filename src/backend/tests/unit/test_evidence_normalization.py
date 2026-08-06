from app.evidence.normalization import (
    build_content_hash,
    normalize_evidence_source,
    normalize_excerpt,
    normalize_url,
)


def test_normalize_url_removes_tracking_fragment_and_default_port() -> None:
    normalized, domain = normalize_url(
        "HTTPS://WWW.Example.com:443/research/?utm_source=test&b=2&a=1#section"
    )

    assert normalized == "https://example.com/research?a=1&b=2"
    assert domain == "example.com"


def test_content_hash_is_stable_across_unicode_case_and_whitespace() -> None:
    first = "Ｐackage   Delivered\nToday"
    second = "package delivered today"

    assert normalize_excerpt(first) == "Package Delivered Today"
    assert build_content_hash(first) == build_content_hash(second)


def test_normalize_evidence_source_keeps_domain_and_hash_together() -> None:
    result = normalize_evidence_source("https://example.com/report", "A cited finding")

    assert result.source_url == "https://example.com/report"
    assert result.source_domain == "example.com"
    assert result.content_hash == build_content_hash("A cited finding")
