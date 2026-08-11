"""Runtime adapter for deterministic Security Policy verification."""

from app.agents.policy_verification.contracts import PolicyVerificationRunCreate
from app.agents.policy_verification.engine import (
    PolicyVerificationError,
    SecurityPolicyVerificationEngine,
)
from app.agents.security_policy import SecurityPolicyArtifact
from app.application.runtime import AgentInvocation, RuntimeErrorCode, RuntimeGatewayError
from app.workflows.contracts import ResearchAgentType


class PolicyVerificationRuntimeAdapter:
    adapter_type = "deterministic_policy_verification"

    def __init__(self, engine: SecurityPolicyVerificationEngine | None = None) -> None:
        self.engine = engine or SecurityPolicyVerificationEngine()

    async def execute(self, invocation: AgentInvocation) -> object:
        invocation.cancellation_token.raise_if_cancelled()
        raw = invocation.context.upstream_artifacts.get(
            ResearchAgentType.SECURITY_POLICY.value
        )
        if raw is None:
            raise RuntimeGatewayError(
                RuntimeErrorCode.DEPENDENCY_MISSING,
                "Policy Verification requires a Security Policy Artifact.",
                agent_run_id=invocation.agent_run_id,
                retryable=False,
            )
        try:
            policy = SecurityPolicyArtifact.from_research_artifact(raw)
            request = PolicyVerificationRunCreate.model_validate(invocation.task.scope)
            return self.engine.verify(
                invocation.task,
                policy,
                request,
                iteration=invocation.context.iteration,
            )
        except PolicyVerificationError as exc:
            raise RuntimeGatewayError(
                RuntimeErrorCode.ARTIFACT_INVALID,
                str(exc),
                agent_run_id=invocation.agent_run_id,
                retryable=False,
                details=exc.details,
            ) from exc
