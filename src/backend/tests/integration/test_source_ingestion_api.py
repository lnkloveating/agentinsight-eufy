import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.database.models import CollectionJobModel, SourceAssetModel


def _project_payload(question: str = "智能门铃应如何理解包裹风险？") -> dict[str, object]:
    return {
        "brief": {
            "question": question,
            "category": "家庭安防",
            "target_user": "智能门铃用户",
            "region": "北美",
            "scenarios": ["包裹送达"],
            "constraints": ["隐私优先"],
            "focus_dimensions": ["证据", "技术"],
        }
    }


def _create_project(client: TestClient, question: str = "智能门铃应如何理解包裹风险？") -> str:
    response = client.post("/api/v1/projects", json=_project_payload(question))
    assert response.status_code == 201
    return str(response.json()["project_id"])


def _upload_pdf(
    client: TestClient,
    project_id: str,
    content: bytes = b"%PDF-1.7 authorized doorbell research",
) -> object:
    return client.post(
        f"/api/v1/projects/{project_id}/sources/files",
        files={"file": ("doorbell-research.pdf", content, "application/pdf")},
        data={
            "authorization_basis": "enterprise_authorized",
            "authorization_confirmed": "true",
            "authorized_by": "research-team",
            "purpose": "未来门铃产品机会研究",
        },
    )


def test_file_upload_is_project_isolated_deduplicated_and_audited(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client)
    other_project_id = _create_project(client, "另一个项目如何研究家庭安防？")

    first = _upload_pdf(client, project_id)
    duplicate = _upload_pdf(client, project_id)

    assert first.status_code == 201
    assert duplicate.status_code == 201
    first_body = first.json()
    duplicate_body = duplicate.json()
    assert first_body["created"] is True
    assert duplicate_body["created"] is False
    asset = first_body["source_asset"]
    assert duplicate_body["source_asset"]["source_asset_id"] == asset["source_asset_id"]
    assert asset["kind"] == "file"
    assert asset["media_category"] == "document"
    assert asset["source_url"] is None
    assert len(asset["content_hash"]) == 64

    page = client.get(f"/api/v1/projects/{project_id}/sources")
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["source_asset_id"] == asset["source_asset_id"]

    isolated = client.get(
        f"/api/v1/projects/{other_project_id}/sources/{asset['source_asset_id']}"
    )
    assert isolated.status_code == 404
    assert isolated.json()["code"] == "SOURCE_ASSET_NOT_FOUND"

    async def counts() -> tuple[int, int]:
        async with client.app.state.database.session() as session:
            assets = int(
                await session.scalar(select(func.count(SourceAssetModel.source_asset_id))) or 0
            )
            jobs = int(
                await session.scalar(select(func.count(CollectionJobModel.collection_job_id))) or 0
            )
            return assets, jobs

    assert asyncio.run(counts()) == (1, 1)
    stored_files = list((tmp_path / "sources" / project_id).glob("*.pdf"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == b"%PDF-1.7 authorized doorbell research"


def test_delete_removes_content_and_reupload_restores_asset(
    client: TestClient, tmp_path: Path
) -> None:
    project_id = _create_project(client)
    uploaded = _upload_pdf(client, project_id).json()["source_asset"]
    original_job_id = uploaded["collection_job_id"]

    deleted = client.delete(
        f"/api/v1/projects/{project_id}/sources/{uploaded['source_asset_id']}"
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert not list((tmp_path / "sources" / project_id).glob("*.pdf"))

    restored_response = _upload_pdf(client, project_id)
    assert restored_response.status_code == 201
    restored = restored_response.json()
    assert restored["created"] is False
    assert restored["source_asset"]["status"] == "ready"
    assert restored["source_asset"]["source_asset_id"] == uploaded["source_asset_id"]
    assert restored["source_asset"]["collection_job_id"] != original_job_id
    assert len(list((tmp_path / "sources" / project_id).glob("*.pdf"))) == 1

    async def job_statuses() -> tuple[str, str]:
        async with client.app.state.database.session() as session:
            original = await session.get(CollectionJobModel, original_job_id)
            replacement = await session.get(
                CollectionJobModel, restored["source_asset"]["collection_job_id"]
            )
            assert original is not None
            assert replacement is not None
            return original.status, replacement.status

    assert asyncio.run(job_statuses()) == ("blocked", "queued")


def test_link_registration_does_not_fetch_and_normalizes_duplicates(client: TestClient) -> None:
    project_id = _create_project(client)
    payload = {
        "source_url": "https://Example.com:443/report?utm_source=chat&a=1#section",
        "display_name": "公开产品报告",
        "authorization_basis": "publicly_available",
        "authorization_confirmed": True,
        "authorized_by": "research-team",
        "purpose": "竞品公开资料研究",
    }

    first = client.post(f"/api/v1/projects/{project_id}/sources/links", json=payload)
    payload["source_url"] = "https://example.com/report?a=1"
    second = client.post(f"/api/v1/projects/{project_id}/sources/links", json=payload)

    assert first.status_code == 201
    assert first.json()["created"] is True
    assert second.status_code == 201
    assert second.json()["created"] is False
    assert second.json()["source_asset"]["source_asset_id"] == first.json()["source_asset"][
        "source_asset_id"
    ]
    assert first.json()["source_asset"]["media_category"] == "webpage"


def test_source_ingestion_rejects_missing_authorization_private_url_and_executable(
    client: TestClient,
) -> None:
    project_id = _create_project(client)
    unauthorized = client.post(
        f"/api/v1/projects/{project_id}/sources/files",
        files={"file": ("research.pdf", b"%PDF-test", "application/pdf")},
        data={
            "authorization_basis": "user_owned",
            "authorization_confirmed": "false",
            "authorized_by": "research-team",
            "purpose": "test",
        },
    )
    executable = client.post(
        f"/api/v1/projects/{project_id}/sources/files",
        files={"file": ("payload.exe", b"binary", "application/octet-stream")},
        data={
            "authorization_basis": "user_owned",
            "authorization_confirmed": "true",
            "authorized_by": "research-team",
            "purpose": "test",
        },
    )
    private_url = client.post(
        f"/api/v1/projects/{project_id}/sources/links",
        json={
            "source_url": "http://127.0.0.1/private",
            "display_name": "private",
            "authorization_basis": "enterprise_authorized",
            "authorization_confirmed": True,
            "authorized_by": "research-team",
            "purpose": "test",
        },
    )

    assert unauthorized.status_code == 422
    assert unauthorized.json()["code"] == "SOURCE_AUTHORIZATION_REQUIRED"
    assert executable.status_code == 415
    assert executable.json()["code"] == "SOURCE_FILE_TYPE_UNSUPPORTED"
    assert private_url.status_code == 422
    assert private_url.json()["code"] == "SOURCE_URL_PRIVATE_NETWORK_FORBIDDEN"


def test_source_query_filters_status_and_rejects_unknown_project(client: TestClient) -> None:
    project_id = _create_project(client)
    asset = _upload_pdf(client, project_id).json()["source_asset"]
    client.delete(f"/api/v1/projects/{project_id}/sources/{asset['source_asset_id']}")

    deleted_page = client.get(
        f"/api/v1/projects/{project_id}/sources", params={"status": "deleted"}
    )
    ready_page = client.get(
        f"/api/v1/projects/{project_id}/sources", params={"status": "ready"}
    )
    missing = client.get("/api/v1/projects/proj_missing/sources")

    assert deleted_page.status_code == 200
    assert deleted_page.json()["total"] == 1
    assert ready_page.json()["total"] == 0
    assert missing.status_code == 404
    assert missing.json()["code"] == "PROJECT_NOT_FOUND"
