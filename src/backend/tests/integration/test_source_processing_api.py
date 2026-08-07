import asyncio
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.application.evidence import SourceEvidencePromotionService
from app.infrastructure.database.evidence_repository import EvidenceRepository
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.source_repository import SourceAssetRepository
from app.schemas.evidence import (
    EvidenceClaimType,
    EvidenceFromSourceFragmentIngest,
)
from app.sources.web_connector import WebConnectorError, WebFetchResult


class StaticWebConnector:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.calls = 0

    async def fetch(self, source_url: str) -> WebFetchResult:
        self.calls += 1
        return WebFetchResult(
            requested_url=source_url,
            final_url="https://www.eufy.com/products/example",
            media_type="text/html",
            status_code=200,
            body_utf8=self.body,
            fetched_at=datetime(2026, 8, 7, tzinfo=UTC),
            etag='"fixture-v1"',
        )


class FailingWebConnector:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, source_url: str) -> WebFetchResult:
        del source_url
        self.calls += 1
        raise WebConnectorError(
            "WEB_FETCH_TIMEOUT",
            "The webpage fetch timed out.",
            blocked=False,
            retryable=True,
        )


def _create_project(client: TestClient, question: str = "研究门铃包裹风险") -> str:
    response = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": question,
                "category": "家庭安防",
                "target_user": "智能门铃用户",
                "region": "北美",
                "scenarios": ["包裹送达"],
                "constraints": ["隐私优先"],
                "focus_dimensions": ["证据", "技术"],
            }
        },
    )
    assert response.status_code == 201
    return str(response.json()["project_id"])


def _upload(
    client: TestClient,
    project_id: str,
    *,
    filename: str,
    content: bytes,
    media_type: str,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/sources/files",
        files={"file": (filename, content, media_type)},
        data={
            "authorization_basis": "enterprise_authorized",
            "authorization_confirmed": "true",
            "authorized_by": "research-team",
            "purpose": "未来门铃产品机会研究",
        },
    )
    assert response.status_code == 201
    return dict(response.json()["source_asset"])


def _pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_text_processing_persists_verified_artifact_and_cleans_workspace(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client)
    asset = _upload(
        client,
        project_id,
        filename="research.md",
        content="包裹已经送达。\n\n预计一小时后下雨。\n".encode(),
        media_type="text/markdown",
    )
    source_asset_id = str(asset["source_asset_id"])

    queued = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    processed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    repeated = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    )

    assert queued.status_code == 200
    assert queued.json()["job"]["status"] == "queued"
    assert processed.status_code == 200
    assert processed.json()["job"]["status"] == "succeeded"
    assert processed.json()["job"]["attempt_count"] == 1
    assert processed.json()["parsed_artifact"]["parser_id"] == "deterministic-text"
    assert repeated.json()["parsed_artifact"]["parsed_artifact_id"] == processed.json()[
        "parsed_artifact"
    ]["parsed_artifact_id"]
    assert fragments.status_code == 200
    assert fragments.json()["total"] == 1
    assert fragments.json()["items"][0]["verification_status"] == "verified"
    assert fragments.json()["items"][0]["original_excerpt"] == (
        "包裹已经送达。\n\n预计一小时后下雨。"
    )
    assert not [
        path
        for path in (tmp_path / "source-processing").rglob("*")
        if path.is_file()
    ]


def test_cancel_then_retry_runs_the_original_collection_job(client: TestClient) -> None:
    project_id = _create_project(client)
    asset = _upload(
        client,
        project_id,
        filename="notes.txt",
        content=b"Package remains outside.",
        media_type="text/plain",
    )
    source_asset_id = str(asset["source_asset_id"])

    cancelled = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing/cancel"
    )
    retried = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing/retry"
    )

    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    assert cancelled.json()["job"]["attempt_count"] == 0
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "succeeded"
    assert retried.json()["job"]["attempt_count"] == 1
    assert retried.json()["job"]["collection_job_id"] == cancelled.json()["job"][
        "collection_job_id"
    ]


def test_invalid_json_fails_without_artifact_and_retry_is_audited(
    client: TestClient,
) -> None:
    project_id = _create_project(client)
    asset = _upload(
        client,
        project_id,
        filename="broken.json",
        content=b'{"event":',
        media_type="application/json",
    )
    source_asset_id = str(asset["source_asset_id"])

    first = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    second = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing/retry"
    )
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    )

    assert first.status_code == 200
    assert first.json()["job"]["status"] == "failed"
    assert first.json()["job"]["error_code"] == "SOURCE_JSON_INVALID"
    assert first.json()["parsed_artifact"] is None
    assert second.json()["job"]["status"] == "failed"
    assert second.json()["job"]["attempt_count"] == 2
    assert fragments.json()["total"] == 0


def test_link_and_media_without_connectors_are_explicitly_blocked(
    client: TestClient,
) -> None:
    project_id = _create_project(client)
    link = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://example.com/product",
            "display_name": "公开产品页",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "竞品研究",
        },
    ).json()["source_asset"]
    audio = _upload(
        client,
        project_id,
        filename="interview.mp3",
        content=b"not-real-audio-but-authorized",
        media_type="audio/mpeg",
    )

    configured_connector = client.app.state.web_connector
    client.app.state.web_connector = None
    try:
        link_result = client.post(
            f"/api/v1/projects/{project_id}/sources/{link['source_asset_id']}/processing"
        )
    finally:
        client.app.state.web_connector = configured_connector
    audio_result = client.post(
        f"/api/v1/projects/{project_id}/sources/{audio['source_asset_id']}/processing"
    )

    assert link_result.status_code == 200
    assert link_result.json()["job"]["status"] == "blocked"
    assert link_result.json()["job"]["error_code"] == (
        "SOURCE_CONNECTOR_NOT_CONFIGURED"
    )
    assert audio_result.json()["job"]["status"] == "blocked"
    assert audio_result.json()["job"]["error_code"] == "SOURCE_PARSER_NOT_CONFIGURED"


def test_authorized_webpage_is_snapshotted_verified_and_promoted(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client)
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://www.eufy.com/products/example?utm_source=test",
            "display_name": "Authorized product page",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "Product opportunity research",
        },
    )
    assert registered.status_code == 201
    source_asset_id = registered.json()["source_asset"]["source_asset_id"]
    connector = StaticWebConnector(
        b"<html><body><main><h1>Doorbell product</h1>"
        b"<script>untrusted hidden text</script>"
        b"<p>Local package detection is supported.</p></main></body></html>"
    )
    client.app.state.web_connector = connector

    processed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    fragments_response = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    )

    assert processed.status_code == 200
    result = processed.json()
    assert result["job"]["status"] == "succeeded"
    assert result["parsed_artifact"]["parser_id"] == "deterministic-html"
    assert result["job"]["result"]["final_url"] == (
        "https://www.eufy.com/products/example"
    )
    assert result["job"]["result"]["captured_content_hash"] == result[
        "parsed_artifact"
    ]["source_content_hash"]
    assert connector.calls == 1
    fragments = fragments_response.json()["items"]
    assert [item["original_excerpt"] for item in fragments] == [
        "Doorbell product",
        "Local package detection is supported.",
    ]
    assert fragments[0]["locator"]["kind"] == "web"
    assert fragments[0]["locator"]["web_path"] == "/html/body/main/h1"
    snapshot = tmp_path / "sources" / project_id / f"{source_asset_id}.html"
    assert snapshot.is_file()
    assert b"untrusted hidden text" in snapshot.read_bytes()

    async def promote() -> object:
        async with client.app.state.database.session() as session:
            service = SourceEvidencePromotionService(
                SourceAssetRepository(session),
                EvidenceRepository(session),
                ProjectRepository(session),
                "trace_web_test",
                client.app.state.event_broker,
            )
            return await service.promote(
                project_id,
                EvidenceFromSourceFragmentIngest(
                    source_fragment_id=fragments[1]["source_fragment_id"],
                    claim_type=EvidenceClaimType.FACT,
                    confidence=0.8,
                    authority_score=0.8,
                    recency_score=0.8,
                    diversity_score=0.5,
                ),
            )

    promoted = asyncio.run(promote())
    assert promoted.created is True
    assert str(promoted.evidence.source_url) == "https://www.eufy.com/products/example"
    assert promoted.evidence.source_locator.kind == "web"

    deleted = client.delete(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
    )
    assert deleted.status_code == 200
    assert snapshot.exists() is False


def test_retryable_web_failure_creates_no_snapshot_or_fragments(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client)
    registered = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "https://example.com/research",
            "display_name": "Unavailable page",
            "authorization_basis": "publicly_available",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "Competitor research",
        },
    ).json()["source_asset"]
    source_asset_id = registered["source_asset_id"]
    connector = FailingWebConnector()
    client.app.state.web_connector = connector

    first = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    second = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing/retry"
    )
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    )

    assert first.json()["job"]["status"] == "failed"
    assert first.json()["job"]["error_code"] == "WEB_FETCH_TIMEOUT"
    assert second.json()["job"]["attempt_count"] == 2
    assert connector.calls == 2
    assert fragments.json()["total"] == 0
    assert not list((tmp_path / "sources" / project_id).glob("*.html"))


def test_delete_purges_verified_fragments_and_blocks_completed_job(
    client: TestClient,
) -> None:
    project_id = _create_project(client)
    asset = _upload(
        client,
        project_id,
        filename="notes.txt",
        content=b"Package remains outside.",
        media_type="text/plain",
    )
    source_asset_id = str(asset["source_asset_id"])
    processed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    assert processed.json()["job"]["status"] == "succeeded"

    deleted = client.delete(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}"
    )
    status = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    )

    assert deleted.status_code == 200
    assert status.json()["job"]["status"] == "blocked"
    assert status.json()["job"]["error_code"] == "SOURCE_ASSET_DELETED"
    assert status.json()["job"]["result"]["parsed_content_purged"] is True
    assert status.json()["parsed_artifact"] is None
    assert fragments.json()["total"] == 0


def test_pdf_processing_uses_page_locator(client: TestClient) -> None:
    project_id = _create_project(client)
    asset = _upload(
        client,
        project_id,
        filename="report.pdf",
        content=_pdf_with_text("Package risk evidence"),
        media_type="application/pdf",
    )
    source_asset_id = str(asset["source_asset_id"])

    processed = client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    fragments = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    )

    assert processed.status_code == 200
    assert processed.json()["job"]["status"] == "succeeded"
    assert processed.json()["parsed_artifact"]["parser_id"] == "pypdf-text"
    assert fragments.json()["items"][0]["locator"]["kind"] == "page"
    assert fragments.json()["items"][0]["locator"]["page_number"] == 1


def test_verified_fragment_is_the_only_source_derived_evidence_entry(
    client: TestClient,
) -> None:
    project_id = _create_project(client)
    asset = _upload(
        client,
        project_id,
        filename="notes.txt",
        content=b"Package remains outside after delivery.",
        media_type="text/plain",
    )
    source_asset_id = str(asset["source_asset_id"])
    client.post(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/processing"
    )
    fragment = client.get(
        f"/api/v1/projects/{project_id}/sources/{source_asset_id}/fragments"
    ).json()["items"][0]

    async def promote() -> object:
        async with client.app.state.database.session() as session:
            service = SourceEvidencePromotionService(
                SourceAssetRepository(session),
                EvidenceRepository(session),
                ProjectRepository(session),
                "trace_test",
                client.app.state.event_broker,
            )
            return await service.promote(
                project_id,
                EvidenceFromSourceFragmentIngest(
                    source_fragment_id=fragment["source_fragment_id"],
                    claim_type=EvidenceClaimType.USER_OPINION,
                    confidence=0.8,
                    authority_score=0.6,
                    recency_score=0.8,
                    diversity_score=0.5,
                ),
            )

    promoted = asyncio.run(promote())
    evidence = promoted.evidence
    assert promoted.created is True
    assert evidence.status == "partially_verified"
    assert evidence.source_url is None
    assert evidence.source_asset_id == source_asset_id
    assert evidence.source_fragment_id == fragment["source_fragment_id"]
    assert evidence.source_locator is not None
    assert evidence.original_excerpt == fragment["original_excerpt"]

    listed = client.get(f"/api/v1/projects/{project_id}/evidence")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["source_fragment_id"] == fragment[
        "source_fragment_id"
    ]

    client.delete(f"/api/v1/projects/{project_id}/sources/{source_asset_id}")
    after_delete = client.get(f"/api/v1/projects/{project_id}/evidence")
    assert after_delete.json()["total"] == 0
