"""只读 Artifact Store 应用边界，写入由 Runtime Gateway 原子完成。"""

from app.application.runtime.contracts import StoredArtifact
from app.infrastructure.database.models import AgentArtifactModel
from app.infrastructure.database.runtime_repository import AgentRuntimeRepository
from app.infrastructure.database.session import Database
from app.workflows.contracts import ResearchArtifact


class ArtifactAccessDeniedError(PermissionError):
    pass


class ArtifactStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(self, project_id: str, artifact_id: str) -> StoredArtifact | None:
        async with self.database.session() as session:
            model = await AgentRuntimeRepository(session).get_artifact(artifact_id)
        if model is None:
            return None
        if model.project_id != project_id:
            raise ArtifactAccessDeniedError("artifact belongs to another project")
        return self._to_stored_artifact(model)

    async def list_versions(self, project_id: str, task_id: str) -> list[StoredArtifact]:
        async with self.database.session() as session:
            models = await AgentRuntimeRepository(session).list_task_artifacts(
                project_id, task_id
            )
        return [self._to_stored_artifact(model) for model in models]

    @staticmethod
    def _to_stored_artifact(model: AgentArtifactModel) -> StoredArtifact:
        artifact = ResearchArtifact.model_validate(
            {
                "artifact_id": model.artifact_id,
                "task_id": model.task_id,
                "artifact_type": model.artifact_type,
                "schema_version": model.schema_version,
                "status": model.status,
                "payload": model.payload_json,
                "evidence_ids": model.evidence_ids_json,
                "contradictions": model.contradictions_json,
                "unknowns": model.unknowns_json,
                "quality_score": model.quality_score,
                "errors": model.errors_json,
            }
        )
        return StoredArtifact(
            artifact=artifact,
            project_id=model.project_id,
            agent_run_id=model.agent_run_id,
            version=model.version,
            input_artifact_ids=tuple(model.input_artifact_ids_json),
            content_hash=model.content_hash,
        )
