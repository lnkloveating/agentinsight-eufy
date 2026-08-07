"""项目隔离的原始资料文件存储。"""

import shutil
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

    def save_bytes(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        suffix: str,
        content: bytes,
    ) -> StoredSource:
        if not content:
            raise AppError(
                code="SOURCE_FILE_EMPTY",
                message="The source snapshot cannot be empty.",
                status_code=422,
            )
        if len(content) > self.max_upload_bytes:
            raise AppError(
                code="SOURCE_FILE_TOO_LARGE",
                message="The source snapshot exceeds the storage size limit.",
                status_code=413,
                details={"max_bytes": self.max_upload_bytes},
            )
        project_directory = self._project_directory(project_id)
        project_directory.mkdir(parents=True, exist_ok=True)
        storage_key = f"{project_id}/{source_asset_id}{suffix}"
        final_path = self._resolve_key(storage_key)
        temporary_path = self._resolve_key(f"{project_id}/.{source_asset_id}.capturing")
        try:
            temporary_path.write_bytes(content)
            temporary_path.replace(final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return StoredSource(
            storage_key=storage_key,
            content_hash=sha256(content).hexdigest(),
            byte_size=len(content),
        )

    def save_derived_bytes(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        artifact_id: str,
        suffix: str,
        content: bytes,
    ) -> StoredSource:
        self._validated_component(project_id)
        self._validated_component(source_asset_id)
        self._validated_component(artifact_id)
        if suffix not in {".wav", ".png"}:
            raise AppError(
                code="MEDIA_ARTIFACT_TYPE_INVALID",
                message="The derived media artifact type is invalid.",
                status_code=422,
            )
        if not content or len(content) > self.max_upload_bytes:
            raise AppError(
                code="MEDIA_ARTIFACT_SIZE_INVALID",
                message="The derived media artifact size is invalid.",
                status_code=413,
            )
        directory_key = f"{project_id}/{source_asset_id}.media"
        directory = self._resolve_key(directory_key)
        directory.mkdir(parents=True, exist_ok=True)
        storage_key = f"{directory_key}/{artifact_id}{suffix}"
        final_path = self._resolve_key(storage_key)
        temporary_path = self._resolve_key(
            f"{directory_key}/.{artifact_id}.capturing"
        )
        try:
            temporary_path.write_bytes(content)
            temporary_path.replace(final_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return StoredSource(
            storage_key=storage_key,
            content_hash=sha256(content).hexdigest(),
            byte_size=len(content),
        )

    def delete_derived(self, project_id: str, source_asset_id: str) -> None:
        self._validated_component(project_id)
        self._validated_component(source_asset_id)
        directory = self._resolve_key(f"{project_id}/{source_asset_id}.media")
        if directory.exists():
            shutil.rmtree(directory)

    def resolve_derived_for_read(
        self,
        *,
        project_id: str,
        source_asset_id: str,
        artifact_id: str,
        suffix: str,
    ) -> Path:
        self._validated_component(project_id)
        self._validated_component(source_asset_id)
        self._validated_component(artifact_id)
        if suffix not in {".wav", ".png"}:
            raise AppError(
                code="MEDIA_ARTIFACT_TYPE_INVALID",
                message="The derived media artifact type is invalid.",
                status_code=422,
            )
        storage_key = (
            f"{project_id}/{source_asset_id}.media/{artifact_id}{suffix}"
        )
        path = self._resolve_key(storage_key)
        if not path.is_file():
            raise AppError(
                code="MEDIA_ARTIFACT_NOT_FOUND",
                message="The derived media artifact does not exist.",
                status_code=404,
            )
        return path

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
        self._validated_component(project_id)
        return self._resolve_key(project_id)

    @staticmethod
    def _validated_component(value: str) -> None:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        if not value or any(character not in allowed for character in value):
            raise AppError(
                code="SOURCE_STORAGE_KEY_INVALID",
                message="项目存储标识无效。",
                status_code=422,
            )

    def _resolve_key(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise AppError(
                code="SOURCE_STORAGE_KEY_INVALID",
                message="资料存储路径无效。",
                status_code=422,
            )
        return candidate
