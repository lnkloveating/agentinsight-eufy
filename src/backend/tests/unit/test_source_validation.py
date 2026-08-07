from io import BytesIO
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.infrastructure.source_storage import LocalSourceStorage
from app.schemas.source import SourceMediaCategory
from app.sources.validation import classify_source_file, normalize_public_url


class AsyncBytesStream:
    def __init__(self, content: bytes) -> None:
        self.stream = BytesIO(content)

    async def read(self, size: int = -1) -> bytes:
        return self.stream.read(size)


def test_file_classification_uses_allowlist_and_removes_client_path() -> None:
    profile = classify_source_file(r"C:\fakepath\doorbell-events.csv", "text/csv")

    assert profile.display_name == "doorbell-events.csv"
    assert profile.media_type == "text/csv"
    assert profile.media_category is SourceMediaCategory.DATASET


def test_file_classification_rejects_unsupported_extension() -> None:
    with pytest.raises(AppError) as error:
        classify_source_file("payload.exe", "application/octet-stream")

    assert error.value.code == "SOURCE_FILE_TYPE_UNSUPPORTED"
    assert error.value.status_code == 415


def test_file_classification_rejects_cross_category_media_type() -> None:
    with pytest.raises(AppError) as error:
        classify_source_file("doorbell.mp4", "application/pdf")

    assert error.value.code == "SOURCE_MEDIA_TYPE_MISMATCH"


@pytest.mark.parametrize(
    "source_url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/internal",
        "http://10.1.2.3/internal",
        "http://[::1]/internal",
        "https://user:password@example.com/private",
    ],
)
def test_url_validation_rejects_private_network_and_embedded_credentials(
    source_url: str,
) -> None:
    with pytest.raises(AppError):
        normalize_public_url(source_url)


def test_url_normalization_removes_fragment_tracking_and_default_port() -> None:
    normalized = normalize_public_url(
        "HTTPS://Example.COM:443/report?utm_source=chat&b=2&a=1#details"
    )

    assert normalized == "https://example.com/report?a=1&b=2"


@pytest.mark.asyncio
async def test_local_storage_enforces_limit_and_cleans_partial_file(tmp_path: Path) -> None:
    storage = LocalSourceStorage(tmp_path / "sources", max_upload_bytes=4)

    with pytest.raises(AppError) as error:
        await storage.save(
            project_id="proj_test",
            source_asset_id="source_test",
            suffix=".pdf",
            stream=AsyncBytesStream(b"12345"),
        )

    assert error.value.code == "SOURCE_FILE_TOO_LARGE"
    assert list((tmp_path / "sources" / "proj_test").iterdir()) == []


def test_local_storage_rejects_path_escape(tmp_path: Path) -> None:
    storage = LocalSourceStorage(tmp_path / "sources", max_upload_bytes=10)

    with pytest.raises(AppError) as error:
        storage.delete("../outside.pdf")

    assert error.value.code == "SOURCE_STORAGE_KEY_INVALID"
