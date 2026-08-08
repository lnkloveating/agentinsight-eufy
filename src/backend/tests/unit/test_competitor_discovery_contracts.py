from typing import Any

import pytest

from app.agents.competitor.discovery_contracts import (
    CompetitorDiscoveryInputContext,
    CompetitorDiscoveryModelOutput,
)
from app.agents.competitor.discovery_validation import (
    CompetitorDiscoveryOutputValidator,
    CompetitorDiscoveryValidationError,
)
from app.workflows.contracts import (
    EvidenceRules,
    ResearchAgentType,
    ResearchBudget,
    ResearchTask,
    ResearchTaskStatus,
)


def _task() -> ResearchTask:
    return ResearchTask(
        task_id="task_competitor_discovery",
        project_id="proj_test",
        agent_type=ResearchAgentType.COMPETITOR_RESEARCH,
        goal="Find exact competitor models.",
        evidence_rules=EvidenceRules(citation_required=False),
        budget=ResearchBudget(max_pages=3, max_iterations=1, deadline_seconds=60),
    )


def _context() -> CompetitorDiscoveryInputContext:
    return CompetitorDiscoveryInputContext.model_validate(
        {
            "target_products": [{"brand": "eufy", "model": "E340", "variant": None}],
            "search_discovery_run_ids": ["search_1"],
            "candidates": [
                {
                    "candidate_id": "candidate_ring",
                    "search_discovery_run_id": "search_1",
                    "title": "Ring Battery Doorbell Pro",
                    "source_url": "https://ring.example/battery-doorbell-pro",
                    "source_domain": "ring.example",
                    "snippet": "Ring Battery Doorbell Pro product candidate.",
                    "search_score": 0.9,
                },
                {
                    "candidate_id": "candidate_nest",
                    "search_discovery_run_id": "search_1",
                    "title": "Google Nest Doorbell Wired 2nd Gen",
                    "source_url": "https://store.google.example/nest-doorbell-wired",
                    "source_domain": "store.google.example",
                    "snippet": "Google Nest Doorbell Wired 2nd Gen candidate.",
                    "search_score": 0.8,
                },
                {
                    "candidate_id": "candidate_collection",
                    "search_discovery_run_id": "search_1",
                    "title": "Smart doorbells collection",
                    "source_url": "https://retail.example/doorbells",
                    "source_domain": "retail.example",
                    "snippet": "No exact model is shown.",
                    "search_score": 0.6,
                },
            ],
            "minimum_candidates": 2,
            "context_hash": "a" * 64,
        }
    )


def _valid_output() -> dict[str, Any]:
    return {
        "summary": "识别出两个带准确型号的待确认竞品。",
        "proposals": [
            {
                "brand": "Ring",
                "model": "Battery Doorbell Pro",
                "variant": None,
                "category": "smart doorbell",
                "candidate_ids": ["candidate_ring"],
                "comparison_dimensions": ["category_fit", "use_case"],
                "reason": "候选标题明确给出了门铃产品及准确型号。",
                "confidence": 0.9,
                "uncertainties": [],
            },
            {
                "brand": "Google Nest",
                "model": "Doorbell Wired 2nd Gen",
                "variant": None,
                "category": "smart doorbell",
                "candidate_ids": ["candidate_nest"],
                "comparison_dimensions": ["category_fit", "form_factor"],
                "reason": "候选标题明确给出了有线门铃型号。",
                "confidence": 0.82,
                "uncertainties": ["正式命名前缀需要后续官方 Evidence 确认。"],
            },
        ],
        "excluded_candidates": [
            {
                "candidate_ids": ["candidate_collection"],
                "reason": "集合页没有准确型号。",
            }
        ],
        "research_gaps": [],
        "unknowns": [],
    }


def test_validator_builds_completed_candidate_only_artifact() -> None:
    artifact = CompetitorDiscoveryOutputValidator().validate(
        _task(),
        _context(),
        CompetitorDiscoveryModelOutput.model_validate(_valid_output()),
    )

    assert artifact.status is ResearchTaskStatus.COMPLETED
    assert artifact.evidence_ids == []
    assert artifact.artifact_type == ResearchAgentType.COMPETITOR_RESEARCH
    assert len(artifact.payload["proposals"]) == 2
    assert artifact.payload["coverage"] == {
        "input_candidate_count": 3,
        "accounted_candidate_count": 3,
        "proposal_count": 2,
        "exact_model_count": 2,
        "minimum_candidates": 2,
        "context_hash": "a" * 64,
    }
    assert all(
        item["proposal_id"].startswith("proposal_") for item in artifact.payload["proposals"]
    )


@pytest.mark.parametrize(
    ("mutate", "detail_key"),
    [
        (
            lambda data: data["proposals"][0].update(
                {"candidate_ids": ["candidate_not_supplied"]}
            ),
            "unsupported_candidate_ids",
        ),
        (
            lambda data: data.update({"excluded_candidates": []}),
            "unaccounted_candidate_ids",
        ),
        (
            lambda data: data["proposals"][0].update(
                {"brand": "eufy", "model": "E340"}
            ),
            "target_product_overlap",
        ),
        (
            lambda data: data["proposals"][0].update({"model": "Alarm Pro"}),
            "unsubstantiated_products",
        ),
    ],
)
def test_validator_rejects_candidate_or_scope_escape(
    mutate: Any,
    detail_key: str,
) -> None:
    data = _valid_output()
    mutate(data)

    with pytest.raises(CompetitorDiscoveryValidationError) as error:
        CompetitorDiscoveryOutputValidator().validate(
            _task(),
            _context(),
            CompetitorDiscoveryModelOutput.model_validate(data),
        )

    assert detail_key in error.value.details
