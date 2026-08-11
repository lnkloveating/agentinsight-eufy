"""Deterministic Evidence, scope, verdict and retry validation for Red Team v2."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.commercial_evaluation_v2 import (
    CommercialEvaluationArtifact,
    CommercialRecommendation,
)
from app.agents.ecosystem_opportunity import EcosystemOpportunityArtifact
from app.agents.policy_verification import PolicyVerificationArtifact
from app.agents.red_team_policy_revision.contracts import (
    REQUIRED_AUTOMATED_DIMENSIONS,
    ChallengeResponseStatus,
    RedTeamArtifact,
    RedTeamChallenge,
    RedTeamChallengeResponse,
    RedTeamCoverage,
    RedTeamFinding,
    RedTeamGap,
    RedTeamModelOutput,
    RedTeamPayload,
    RedTeamRevisionRequest,
    RedTeamSeverity,
    RedTeamVerdict,
    RedTeamVersionDiff,
    finding_id,
    red_team_gap_id,
    revision_id,
)
from app.agents.security_policy import SecurityPolicyArtifact
from app.workflows.contracts import (
    AgentContext,
    ResearchAgentType,
    ResearchArtifact,
    ResearchTask,
    ResearchTaskStatus,
)

_PREVIOUS_RED_TEAM_KEY = "previous_red_team"
_REQUIRED_UPSTREAM = (
    ResearchAgentType.USER_RESEARCH,
    ResearchAgentType.COMPETITOR_RESEARCH,
    ResearchAgentType.ECOSYSTEM_OPPORTUNITY,
    ResearchAgentType.TECHNICAL_FEASIBILITY,
    ResearchAgentType.SECURITY_POLICY,
    ResearchAgentType.POLICY_VERIFICATION,
    ResearchAgentType.COMMERCIAL_EVALUATION,
)
_REVISION_ORDER = {item.value: index for index, item in enumerate(_REQUIRED_UPSTREAM)}
_ALLOWED_REVISION_AGENTS = set(_REVISION_ORDER)


@dataclass(frozen=True)
class RedTeamValidationError(ValueError):
    message: str
    details: dict[str, object]

    def __str__(self) -> str:
        return self.message


class RedTeamOutputValidator:
    def validate(
        self,
        task: ResearchTask,
        context: AgentContext,
        output: RedTeamModelOutput,
        challenges: list[RedTeamChallenge],
    ) -> RedTeamArtifact:
        upstream = self._required_upstream(context)
        opportunity = EcosystemOpportunityArtifact.from_research_artifact(
            upstream[ResearchAgentType.ECOSYSTEM_OPPORTUNITY]
        )
        policy = SecurityPolicyArtifact.from_research_artifact(
            upstream[ResearchAgentType.SECURITY_POLICY]
        )
        verification = PolicyVerificationArtifact.from_research_artifact(
            upstream[ResearchAgentType.POLICY_VERIFICATION]
        )
        commercial = CommercialEvaluationArtifact.from_research_artifact(
            upstream[ResearchAgentType.COMMERCIAL_EVALUATION]
        )
        self._validate_dimensions(output, bool(challenges))
        self._validate_challenge_targets(challenges, upstream, policy, verification)

        context_evidence = (
            context.evidence_context.items if context.evidence_context else []
        )
        allowed_evidence = {
            *(
                item.evidence_id
                for item in context_evidence
            ),
            *(
                evidence_id
                for artifact in upstream.values()
                for evidence_id in artifact.evidence_ids
            ),
        }
        cited = self._cited_evidence(output)
        unsupported = sorted(cited - allowed_evidence)
        if unsupported:
            raise self._error(
                "Red Team cites Evidence outside the bounded context.",
                unsupported_evidence_ids=unsupported,
            )

        source_artifact_ids = {
            agent.value: artifact.artifact_id for agent, artifact in upstream.items()
        }
        known_artifact_ids = set(source_artifact_ids.values())
        known_opportunity_ids = {item.opportunity_id for item in opportunity.payload.opportunities}
        known_policy_ids = {item.policy_id for item in policy.payload.policies}
        known_scenario_ids = {item.scenario_id for item in verification.payload.scenarios}
        findings = [
            RedTeamFinding(
                finding_id=finding_id(item),
                **item.model_dump(mode="python"),
            )
            for item in output.findings
        ]
        self._validate_findings(
            findings,
            known_artifact_ids,
            known_opportunity_ids,
            known_policy_ids,
            known_scenario_ids,
        )
        gaps = [
            RedTeamGap(
                gap_id=red_team_gap_id(item),
                **item.model_dump(mode="python"),
            )
            for item in output.red_team_gaps
        ]
        self._validate_gaps(gaps, known_opportunity_ids)
        self._validate_source_recovery_links(findings, gaps)

        challenge_responses = self._challenge_responses(challenges, output, findings)
        verdict = self._verdict(findings, gaps, challenge_responses)
        if (
            commercial.payload.recommendation is CommercialRecommendation.DO_NOT_RECOMMEND
            and not any(item.dimension.value == "commercial_claim" for item in findings)
        ):
            raise self._error(
                "A do-not-recommend commercial result requires an explicit red-team finding."
            )
        if verdict is RedTeamVerdict.REJECT and output.fallback_plan is None:
            raise self._error("Rejected proposals require a safe fallback plan.")

        revision_requests = self._revision_requests(findings, upstream, verdict)
        previous = self._previous(context)
        diff = self._version_diff(previous, findings)
        unresolved_challenges = sum(
            item.status
            in {
                ChallengeResponseStatus.UNRESOLVED,
                ChallengeResponseStatus.PARTIALLY_ANSWERED,
                ChallengeResponseStatus.REQUIRES_HUMAN_DECISION,
            }
            for item in challenge_responses
        )
        payload = RedTeamPayload(
            source_artifact_ids=source_artifact_ids,
            summary=output.summary,
            summary_evidence_ids=output.summary_evidence_ids,
            findings=findings,
            challenge_responses=challenge_responses,
            red_team_gaps=gaps,
            revision_requests=revision_requests,
            fallback_plan=output.fallback_plan,
            verdict=verdict,
            verdict_reason=self._verdict_reason(verdict, findings, gaps, unresolved_challenges),
            version_diff=diff,
            coverage=RedTeamCoverage(
                required_dimension_count=len(REQUIRED_AUTOMATED_DIMENSIONS),
                attacked_dimension_count=len(set(output.attacked_dimensions)),
                finding_count=len(findings),
                challenge_count=len(challenges),
                unresolved_challenge_count=unresolved_challenges,
                evidence_context_hash=(
                    context.evidence_context.context_hash
                    if context.evidence_context is not None
                    else "0" * 64
                ),
            ),
        )
        return RedTeamArtifact(
            artifact_id=f"artifact_{task.task_id}_{context.iteration + 1}",
            task_id=task.task_id,
            status=(
                ResearchTaskStatus.PARTIAL
                if verdict
                in {
                    RedTeamVerdict.REVISE,
                    RedTeamVerdict.NEEDS_MORE_EVIDENCE,
                    RedTeamVerdict.HUMAN_REVIEW,
                }
                else ResearchTaskStatus.COMPLETED
            ),
            payload=payload,
            evidence_ids=sorted(cited),
            contradictions=[item.description for item in findings],
            unknowns=list(dict.fromkeys([*output.unknowns, *(item.question for item in gaps)])),
            quality_score=max(
                0.0,
                round(
                    100
                    - len(gaps) * 5
                    - unresolved_challenges * 5
                    - max(
                        0,
                        len(REQUIRED_AUTOMATED_DIMENSIONS)
                        - len(set(output.attacked_dimensions)),
                    )
                    * 10,
                    2,
                ),
            ),
        )

    def _required_upstream(
        self, context: AgentContext
    ) -> dict[ResearchAgentType, ResearchArtifact]:
        missing = [
            item.value
            for item in _REQUIRED_UPSTREAM
            if item.value not in context.upstream_artifacts
        ]
        if missing:
            raise self._error(
                "Red Team requires all current upstream Artifacts.",
                missing_agent_types=missing,
            )
        return {item: context.upstream_artifacts[item.value] for item in _REQUIRED_UPSTREAM}

    def _validate_dimensions(self, output: RedTeamModelOutput, has_challenges: bool) -> None:
        attacked = set(output.attacked_dimensions)
        missing = sorted(item.value for item in REQUIRED_AUTOMATED_DIMENSIONS - attacked)
        if missing:
            raise self._error(
                "Red Team did not attack every required automated dimension.",
                missing_dimensions=missing,
            )
        if has_challenges and "user_challenge" not in {item.value for item in attacked}:
            raise self._error("User challenges require the user_challenge dimension.")

    def _validate_challenge_targets(
        self,
        challenges: list[RedTeamChallenge],
        upstream: dict[ResearchAgentType, ResearchArtifact],
        policy: SecurityPolicyArtifact,
        verification: PolicyVerificationArtifact,
    ) -> None:
        artifact_ids = {item.artifact_id for item in upstream.values()}
        policy_ids = {item.policy_id for item in policy.payload.policies}
        scenario_ids = {item.scenario_id for item in verification.payload.scenarios}
        unknown_artifacts = sorted(
            {item for challenge in challenges for item in challenge.target_artifact_ids}
            - artifact_ids
        )
        unknown_policies = sorted(
            {item for challenge in challenges for item in challenge.target_policy_ids} - policy_ids
        )
        unknown_scenarios = sorted(
            {item for challenge in challenges for item in challenge.target_scenario_ids}
            - scenario_ids
        )
        if unknown_artifacts or unknown_policies or unknown_scenarios:
            raise self._error(
                "User challenge targets are outside the current review scope.",
                unknown_artifact_ids=unknown_artifacts,
                unknown_policy_ids=unknown_policies,
                unknown_scenario_ids=unknown_scenarios,
            )

    def _validate_findings(
        self,
        findings: list[RedTeamFinding],
        artifact_ids: set[str],
        opportunity_ids: set[str],
        policy_ids: set[str],
        scenario_ids: set[str],
    ) -> None:
        if len({item.finding_id for item in findings}) != len(findings):
            raise self._error("Red Team findings must be unique.")
        invalid_agents = sorted(
            {
                agent
                for item in findings
                for agent in item.affected_agent_types
                if agent not in _ALLOWED_REVISION_AGENTS
            }
        )
        invalid_artifacts = sorted(
            {value for item in findings for value in item.affected_artifact_ids} - artifact_ids
        )
        invalid_opportunities = sorted(
            {value for item in findings for value in item.affected_opportunity_ids}
            - opportunity_ids
        )
        invalid_policies = sorted(
            {value for item in findings for value in item.affected_policy_ids} - policy_ids
        )
        invalid_scenarios = sorted(
            {value for item in findings for value in item.affected_scenario_ids} - scenario_ids
        )
        if any(
            (
                invalid_agents,
                invalid_artifacts,
                invalid_opportunities,
                invalid_policies,
                invalid_scenarios,
            )
        ):
            raise self._error(
                "Red Team findings reference values outside current Artifacts.",
                invalid_agent_types=invalid_agents,
                invalid_artifact_ids=invalid_artifacts,
                invalid_opportunity_ids=invalid_opportunities,
                invalid_policy_ids=invalid_policies,
                invalid_scenario_ids=invalid_scenarios,
            )

    def _validate_gaps(self, gaps: list[RedTeamGap], opportunity_ids: set[str]) -> None:
        gap_ids = [gap.gap_id for gap in gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise self._error("Red Team gap IDs must be unique.")

        invalid_agents = sorted(
            {
                agent
                for gap in gaps
                for agent in gap.affected_agent_types
                if agent not in _ALLOWED_REVISION_AGENTS
            }
        )
        invalid_opportunities = sorted(
            {value for gap in gaps for value in gap.affected_opportunity_ids} - opportunity_ids
        )
        if invalid_agents or invalid_opportunities:
            raise self._error(
                "Red Team gaps reference values outside current scope.",
                invalid_agent_types=invalid_agents,
                invalid_opportunity_ids=invalid_opportunities,
            )

    def _validate_source_recovery_links(
        self, findings: list[RedTeamFinding], gaps: list[RedTeamGap]
    ) -> None:
        for finding in findings:
            if not finding.requires_source_recovery:
                continue
            if not any(
                gap.dimension is finding.dimension
                and bool(set(gap.affected_agent_types) & set(finding.affected_agent_types))
                for gap in gaps
            ):
                raise self._error(
                    "Every source-recovery finding requires a matching red_team_gap.",
                    finding_id=finding.finding_id,
                )

    def _challenge_responses(
        self,
        challenges: list[RedTeamChallenge],
        output: RedTeamModelOutput,
        findings: list[RedTeamFinding],
    ) -> list[RedTeamChallengeResponse]:
        expected = {item.challenge_id: item for item in challenges}
        actual = {item.challenge_id: item for item in output.challenge_responses}
        if len(actual) != len(output.challenge_responses) or set(actual) != set(expected):
            raise self._error(
                "Red Team must answer every user challenge exactly once.",
                expected_challenge_ids=sorted(expected),
                actual_challenge_ids=sorted(actual),
            )
        responses: list[RedTeamChallengeResponse] = []
        for challenge_id, intent in actual.items():
            invalid_indexes = sorted(
                index
                for index in intent.related_finding_indexes
                if index < 0 or index >= len(findings)
            )
            if invalid_indexes:
                raise self._error(
                    "Challenge response references an unknown finding index.",
                    challenge_id=challenge_id,
                    invalid_indexes=invalid_indexes,
                )
            responses.append(
                RedTeamChallengeResponse(
                    challenge_id=challenge_id,
                    question=expected[challenge_id].question,
                    status=intent.status,
                    answer=intent.answer,
                    evidence_ids=intent.evidence_ids,
                    related_finding_ids=[
                        findings[index].finding_id for index in intent.related_finding_indexes
                    ],
                )
            )
        return responses

    def _revision_requests(
        self,
        findings: list[RedTeamFinding],
        upstream: dict[ResearchAgentType, ResearchArtifact],
        verdict: RedTeamVerdict,
    ) -> list[RedTeamRevisionRequest]:
        if verdict is not RedTeamVerdict.REVISE:
            return []
        actionable = [
            item for item in findings if item.required_actions and not item.requires_source_recovery
        ]
        agents = sorted(
            {agent for item in actionable for agent in item.affected_agent_types},
            key=_REVISION_ORDER.__getitem__,
        )
        if not actionable or not agents:
            raise self._error("A revise verdict requires actionable findings and targets.")
        task_ids = [upstream[ResearchAgentType(agent)].task_id for agent in agents]
        finding_ids = [item.finding_id for item in actionable]
        actions = list(
            dict.fromkeys(action for item in actionable for action in item.required_actions)
        )
        return [
            RedTeamRevisionRequest(
                revision_id=revision_id(finding_ids, task_ids),
                finding_ids=finding_ids,
                affected_agent_types=agents,
                affected_task_ids=task_ids,
                required_actions=actions,
                resume_from_agent=agents[0],
                reason=("红队发现可修订问题；从最早受影响 Agent 恢复，并让依赖节点重新生成。"),
            )
        ]

    @staticmethod
    def _verdict(
        findings: list[RedTeamFinding],
        gaps: list[RedTeamGap],
        responses: list[RedTeamChallengeResponse],
    ) -> RedTeamVerdict:
        if any(item.irreducible and item.severity is RedTeamSeverity.CRITICAL for item in findings):
            return RedTeamVerdict.REJECT
        if any(item.requires_human_decision for item in findings) or any(
            item.status is ChallengeResponseStatus.REQUIRES_HUMAN_DECISION for item in responses
        ):
            return RedTeamVerdict.HUMAN_REVIEW
        if (
            gaps
            or any(item.requires_source_recovery for item in findings)
            or any(
                item.status
                in {
                    ChallengeResponseStatus.UNRESOLVED,
                    ChallengeResponseStatus.PARTIALLY_ANSWERED,
                }
                for item in responses
            )
        ):
            return RedTeamVerdict.NEEDS_MORE_EVIDENCE
        if any(
            item.required_actions
            or item.severity
            in {
                RedTeamSeverity.MEDIUM,
                RedTeamSeverity.HIGH,
                RedTeamSeverity.CRITICAL,
            }
            for item in findings
        ):
            return RedTeamVerdict.REVISE
        return RedTeamVerdict.PASS

    @staticmethod
    def _verdict_reason(
        verdict: RedTeamVerdict,
        findings: list[RedTeamFinding],
        gaps: list[RedTeamGap],
        unresolved_challenges: int,
    ) -> str:
        return (
            f"后端确定性结论={verdict.value}；Finding={len(findings)}；"
            f"补研缺口={len(gaps)}；未完全回答的用户质疑={unresolved_challenges}。"
            "该结论只决定返工、补研或进入下一阶段，不代表真实部署获批。"
        )

    def _previous(self, context: AgentContext) -> RedTeamArtifact | None:
        raw = context.upstream_artifacts.get(_PREVIOUS_RED_TEAM_KEY)
        return RedTeamArtifact.from_research_artifact(raw) if raw is not None else None

    @staticmethod
    def _version_diff(
        previous: RedTeamArtifact | None, findings: list[RedTeamFinding]
    ) -> RedTeamVersionDiff:
        current_ids = {item.finding_id for item in findings}
        previous_ids = (
            {item.finding_id for item in previous.payload.findings}
            if previous is not None
            else set()
        )
        return RedTeamVersionDiff(
            previous_artifact_id=previous.artifact_id if previous else None,
            added_finding_ids=sorted(current_ids - previous_ids),
            resolved_finding_ids=sorted(previous_ids - current_ids),
            unchanged_finding_ids=sorted(current_ids & previous_ids),
        )

    @staticmethod
    def _cited_evidence(output: RedTeamModelOutput) -> set[str]:
        return {
            *output.summary_evidence_ids,
            *(value for item in output.findings for value in item.evidence_ids),
            *(value for item in output.challenge_responses for value in item.evidence_ids),
        }

    @staticmethod
    def _error(message: str, **details: object) -> RedTeamValidationError:
        return RedTeamValidationError(message, details)
