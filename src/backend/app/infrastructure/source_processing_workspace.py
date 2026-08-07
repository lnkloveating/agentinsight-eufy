import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from app.core.errors import AppError


@dataclass(frozen=True)
class MaterializedSource:
    workspace: Path
    source_path: Path
    content_hash: str


class SourceProcessingWorkspaceManager:
    """Creates one bounded workspace for one persisted Collection Job."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def materialize(
        self,
        *,
        project_id: str,
        collection_job_id: str,
        source_path: Path,
    ) -> MaterializedSource:
        project_component = self._safe_component(project_id)
        job_component = self._safe_component(collection_job_id)
        workspace = self._resolve(project_component, job_component)
        if workspace.exists():
            shutil.rmtree(workspace)
        input_directory = workspace / "input"
        input_directory.mkdir(parents=True, exist_ok=False)
        destination = input_directory / f"source{source_path.suffix.lower()}"
        digest = sha256()
        with source_path.open("rb") as source, destination.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        return MaterializedSource(
            workspace=workspace,
            source_path=destination,
            content_hash=digest.hexdigest(),
        )

    def materialize_bytes(
        self,
        *,
        project_id: str,
        collection_job_id: str,
        content: bytes,
        suffix: str,
    ) -> MaterializedSource:
        project_component = self._safe_component(project_id)
        job_component = self._safe_component(collection_job_id)
        workspace = self._resolve(project_component, job_component)
        if workspace.exists():
            shutil.rmtree(workspace)
        input_directory = workspace / "input"
        input_directory.mkdir(parents=True, exist_ok=False)
        source_path = input_directory / f"source{suffix}"
        source_path.write_bytes(content)
        return MaterializedSource(
            workspace=workspace,
            source_path=source_path,
            content_hash=sha256(content).hexdigest(),
        )

    def cleanup(self, workspace: Path | None) -> None:
        if workspace is None:
            return
        resolved = workspace.resolve()
        if resolved == self.root or self.root not in resolved.parents:
            raise AppError(
                code="SOURCE_PROCESSING_WORKSPACE_INVALID",
                message="资料处理工作目录无效。",
                status_code=500,
            )
        shutil.rmtree(resolved, ignore_errors=True)

    def _resolve(self, *parts: str) -> Path:
        candidate = self.root.joinpath(*parts).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise AppError(
                code="SOURCE_PROCESSING_WORKSPACE_INVALID",
                message="资料处理工作目录无效。",
                status_code=500,
            )
        return candidate

    @staticmethod
    def _safe_component(value: str) -> str:
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        if value and all(character in allowed for character in value):
            return value
        return sha256(value.encode("utf-8")).hexdigest()[:32]
