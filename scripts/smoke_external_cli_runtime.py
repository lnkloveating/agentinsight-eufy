from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.application.model_gateway import EnvironmentCredentialResolver
from app.application.runtime import (
    AgentInvocation,
    CancellationToken,
    ExternalCliAgentAdapter,
    ExternalCliProcessRunner,
    OpenCodeCliDriver,
)
from app.core.config import Settings
from app.schemas.project import ResearchBrief
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
)


async def run_smoke() -> dict[str, object]:
    environment_path = BACKEND_ROOT / ".env"
    if not environment_path.is_file():
        raise RuntimeError("src/backend/.env is required for the live smoke test")
    settings = Settings(_env_file=environment_path)
    credentials = EnvironmentCredentialResolver.from_dotenv(str(environment_path))
    driver = OpenCodeCliDriver(
        executable=settings.opencode_executable,
        provider_id=settings.opencode_provider_id,
        provider_name=settings.opencode_provider_name,
        provider_base_url=settings.opencode_provider_base_url,
        provider_model=settings.opencode_provider_model,
        credential_env=settings.opencode_credential_env,
        enabled=settings.opencode_runtime_enabled,
    )
    runner = ExternalCliProcessRunner(
        max_output_bytes=settings.external_cli_max_output_bytes,
        probe_timeout_seconds=settings.external_cli_probe_timeout_seconds,
    )
    adapter = ExternalCliAgentAdapter(
        driver,
        credentials,
        runner,
        REPOSITORY_ROOT / "data" / "runtime-smoke",
    )
    suffix = uuid4().hex[:12]
    task = ResearchTask(
        task_id=f"task_smoke_{suffix}",
        project_id="proj_external_cli_smoke",
        agent_type=ResearchAgentType.RESEARCH_MANAGER,
        goal=(
            "Validate the external CLI contract only. Make no factual claims. "
            "Return a blocked ResearchArtifact with one unknown explaining that "
            "evidence collection is intentionally outside this smoke test."
        ),
        budget={"deadline_seconds": 180},
    )
    invocation = AgentInvocation(
        agent_run_id=f"run_smoke_{suffix}",
        trace_id=f"trace_smoke_{suffix}",
        attempt_number=1,
        workspace_key=f"workspace_smoke_{suffix}",
        input_artifact_ids=(),
        task=task,
        context=AgentContext(
            project_id=task.project_id,
            brief=ResearchBrief(
                question="Can the configured external CLI return the required schema?",
                category="runtime validation",
                target_user="backend developers",
                region="local",
            ),
            iteration=0,
        ),
        cancellation_token=CancellationToken(),
    )
    raw_output = await adapter.execute(invocation)
    artifact = ResearchArtifact.model_validate(raw_output)
    if artifact.task_id != task.task_id:
        raise RuntimeError("live runtime returned an artifact for the wrong task")
    probe = await runner.probe(driver.executable, driver.version_arguments())
    return {
        "runtime_id": driver.runtime_id,
        "runtime_version": probe.version,
        "model_id": driver.model_id,
        "artifact_status": artifact.status,
        "artifact_type": artifact.artifact_type,
        "unknown_count": len(artifact.unknowns),
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_smoke()), ensure_ascii=False, sort_keys=True))
