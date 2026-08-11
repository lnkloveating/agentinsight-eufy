"""把各领域 Agent 的原生缺口确定性投影为统一补研契约。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from app.schemas.source_recovery import (
    AgentArtifactGap,
    AgentGapSeverity,
    RecoverableAgentType,
)
from app.workflows.contracts import ResearchArtifact

_GAP_COLLECTION_KEYS = {
    "research_gaps",
    "portfolio_gaps",
    "compilation_gaps",
    "source_requirements",
    "commercial_gaps",
    "validation_gaps",
    "red_team_gaps",
    "gaps",
}


class AgentGapProjector:
    """只读取 Artifact JSON，不调用模型，也不修改原始 Artifact。"""

    def project(
        self,
        artifact: ResearchArtifact,
        agent_type: RecoverableAgentType,
    ) -> list[AgentArtifactGap]:
        projected: list[AgentArtifactGap] = []
        seen: set[str] = set()
        for path, raw_gap in self._walk_gap_collections(artifact.payload, "payload"):
            gap = self._project_one(artifact, agent_type, path, raw_gap)
            if gap is None or gap.gap_id in seen:
                continue
            seen.add(gap.gap_id)
            projected.append(gap)
        return projected

    def _project_one(
        self,
        artifact: ResearchArtifact,
        agent_type: RecoverableAgentType,
        source_path: str,
        raw: dict[str, Any],
    ) -> AgentArtifactGap | None:
        question = self._text(raw.get("question"))
        if not question:
            return None
        reason = self._text(raw.get("reason")) or "该 Agent 标记此问题缺少可验证资料。"
        scope_label = self._optional_text(
            raw.get("scope_label") or raw.get("product") or raw.get("candidate_name")
        )
        dimension = self._optional_text(raw.get("dimension"))
        recommended = self._string_list(raw.get("recommended_source_types"))
        required = self._string_list(raw.get("required_evidence_types"))
        affected = self._string_list(
            raw.get("affected_candidate_ids")
            or raw.get("affected_opportunity_ids")
            or raw.get("affected_policy_ids")
        )
        affected_agents = self._string_list(raw.get("affected_agent_types"))
        supplied_id = self._text(raw.get("gap_id"))
        gap_id = supplied_id or self._stable_gap_id(
            agent_type=agent_type,
            question=question,
            scope_label=scope_label,
            dimension=dimension,
            recommended_source_types=recommended,
            required_evidence_types=required,
            affected_candidate_ids=affected,
            affected_agent_types=affected_agents,
        )
        return AgentArtifactGap(
            gap_id=gap_id,
            artifact_id=artifact.artifact_id,
            task_id=artifact.task_id,
            agent_type=agent_type,
            question=question,
            reason=reason,
            severity=self._severity(raw.get("severity")),
            recommended_source_types=recommended,
            required_evidence_types=required,
            affected_candidate_ids=affected,
            affected_agent_types=affected_agents,
            scope_label=scope_label,
            dimension=dimension,
            source_path=source_path,
        )

    @classmethod
    def _walk_gap_collections(
        cls,
        value: object,
        path: str,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                if key in _GAP_COLLECTION_KEYS and isinstance(child, list):
                    for index, item in enumerate(child):
                        if isinstance(item, dict):
                            yield f"{child_path}[{index}]", item
                    continue
                yield from cls._walk_gap_collections(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from cls._walk_gap_collections(child, f"{path}[{index}]")

    @staticmethod
    def _stable_gap_id(
        *,
        agent_type: RecoverableAgentType,
        question: str,
        scope_label: str | None,
        dimension: str | None,
        recommended_source_types: list[str],
        required_evidence_types: list[str],
        affected_candidate_ids: list[str],
        affected_agent_types: list[str],
    ) -> str:
        canonical = json.dumps(
            {
                "agent_type": agent_type.value,
                "question": question.casefold(),
                "scope_label": (scope_label or "").casefold(),
                "dimension": (dimension or "").casefold(),
                "recommended_source_types": sorted(recommended_source_types),
                "required_evidence_types": sorted(required_evidence_types),
                "affected_candidate_ids": sorted(affected_candidate_ids),
                "affected_agent_types": sorted(affected_agent_types),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"gap_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _severity(value: object) -> AgentGapSeverity:
        normalized = AgentGapProjector._text(value).casefold()
        try:
            return AgentGapSeverity(normalized)
        except ValueError:
            return AgentGapSeverity.UNKNOWN

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return list(
            dict.fromkeys(text for item in value if (text := AgentGapProjector._text(item)))
        )[:20]

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = AgentGapProjector._text(value)
        return text or None

    @staticmethod
    def _text(value: object) -> str:
        if value is None:
            return ""
        candidate = getattr(value, "value", value)
        return str(candidate).strip()
