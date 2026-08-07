"""项目隔离的原始资料文件存储。"""

from collections.abc import Awaitable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from app.core.errors import AppError


class AsyncUploadStream(Protocol):
    def read(self, size: int = -1) -> Awaitable[bytes]: ...


@dataclass(frozen=True)
class StoredSource:
    storage_key: str
    content_hash: str
    byte_size: int


class LocalSourceStorage:
    """只接受后端生成的项目和资产 ID，不使用用户文件名构造目录。"""

    def __init__(self, root: Path, max_upload_bytes: int) -> None:
        self.root = root.resolve()
        self.max_upload_bytes = max_upload_bytes

    async def save(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        suffix: str,
        stream: AsyncUploadStream,
    ) -> StoredSource:
        project_directory = self._project_directory(project_id)
        project_directory.mkdir(parents=True, exist_ok=True)
        final_path = self._resolve_key(f"{project_id}/{source_asset_id}{suffix}")
        temporary_path = self._resolve_key(f"{project_id}/.{source_asset_id}.uploading")
        digest = sha256()
        byte_size = 0
        try:
            with temporary_path.open("xb") as output:
                while chunk := await stream.read(1024 * 1024):
                    byte_size += len(chunk)
                    if byte_size > self.max_upload_bytes:
                        raise AppError(
                            code="SOURCE_FILE_TOO_LARGE",
                            message="上传文件超过允许的大小限制。",
                            status_code=413,
                            details={"max_bytes": self.max_upload_bytes},
                        )
                    digest.update(chunk)
                    output.write(chunk)
            if byte_size == 0:
                raise AppError(
                    code="SOURCE_FILE_EMPTY",
                    message="不能上传空文件。",
                    status_code=422,
                )
            temporary_path.replace(final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        return StoredSource(
            storage_key=f"{project_id}/{source_asset_id}{suffix}",
            content_hash=digest.hexdigest(),
            byte_size=byte_size,
        )

    def delete(self, storage_key: str | None) -> None:
        if storage_key is None:
            return
        path = self._resolve_key(storage_key)
        path.unlink(missing_ok=True)

    def resolve_for_read(self, storage_key: str | None) -> Path:
        if storage_key is None:
            raise AppError(
                code="SOURCE_CONTENT_MISSING",
                message="原始资料内容不存在。",
                status_code=409,
            )
        path = self._resolve_key(storage_key)
        if not path.is_file():
            raise AppError(
                code="SOURCE_CONTENT_MISSING",
                message="原始资料内容不存在。",
                status_code=409,
            )
        return path

    def _project_directory(self, project_id: str) -> Path:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        if not project_id or any(character not in allowed for character in project_id):
            raise AppError(
                code="SOURCE_STORAGE_KEY_INVALID",
                message="项目存储标识无效。",
                status_code=422,
            )
        return self._resolve_key(project_id)

    def _resolve_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise AppError(
                code="SOURCE_STORAGE_KEY_INVALID",
                message="资料存储路径无效。",
                status_code=422,
            )
        return candidate
