import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.application.model_gateway import (
    ModelUsage,
    ProviderModelRequest,
    ProviderModelResult,
)
from app.core.config import Settings
from app.main import create_app


class ClarifierProvider:
    provider_id = "clarifier-test"

    def __init__(self) -> None:
        self.requests: list[ProviderModelRequest] = []

    async def generate(self, request: ProviderModelRequest) -> ProviderModelResult:
        self.requests.append(request)
        user_prompt = request.messages[-1].content
        conversation = json.loads(
            user_prompt.split("conversation_json=", 1)[1].split("\ncurrent_draft_json=", 1)[0]
        )
        user_messages = [item for item in conversation if item["role"] == "user"]
        evidence_message_id = user_messages[-1]["message_id"]
        if len(user_messages) == 1:
            output: dict[str, Any] = {
                "assistant_message": "我先确认研究范围和隐私边界。",
                "draft_patch": {
                    "question": user_messages[0]["content"],
                    "safety_domains": ["elder_safety"],
                    "target_ecosystems": ["eufy"],
                    # Simulate an unsafe model guess. The service must reject it
                    # because this sensitive field was not asked and confirmed.
                    "privacy_boundary": {"raw_media_allowed": True},
                },
                "field_evidence": [
                    {"field_path": path, "message_ids": [evidence_message_id]}
                    for path in (
                        "question",
                        "safety_domains",
                        "target_ecosystems",
                        "privacy_boundary.raw_media_allowed",
                    )
                ],
                "questions": [
                    {
                        "question_id": "scope-and-goals",
                        "field_paths": [
                            "research_scope",
                            "target_users",
                            "markets",
                            "time_horizon",
                            "safety_goals",
                            "risk_scenarios",
                            "deliverables",
                        ],
                        "prompt": "请确认生态范围、用户、市场、风险场景和交付物。",
                        "choices": [],
                    },
                    {
                        "question_id": "signals-and-privacy",
                        "field_paths": [
                            "authorized_signal_types",
                            "privacy_boundary.raw_media_allowed",
                            "privacy_boundary.restricted_zones",
                            "privacy_boundary.retention_policy",
                            "privacy_boundary.external_sharing_allowed",
                        ],
                        "prompt": "允许哪些信号？是否允许原始视频，哪些区域受限，如何保留和分享？",
                        "choices": [],
                    },
                    {
                        "question_id": "actions-and-source-permissions",
                        "field_paths": [
                            "intervention_boundary.allowed_interventions",
                            "intervention_boundary.prohibited_actions",
                            "intervention_boundary.high_impact_action_requires_human_approval",
                            "forbidden_inferences",
                            "source_permissions.public_sources",
                            "source_permissions.user_uploaded_materials",
                            "source_permissions.enterprise_internal_materials",
                            "source_permissions.authorized_household_events",
                        ],
                        "prompt": "请明确允许动作、禁止推断和四类资料权限。",
                        "choices": [],
                    }
                ],
            }
        else:
            patch = _completed_patch()
            output = {
                "assistant_message": "信息已补齐，请确认 Research Brief。",
                "draft_patch": patch,
                "field_evidence": [
                    {"field_path": path, "message_ids": [evidence_message_id]}
                    for path, _ in _flatten(patch)
                ],
                "questions": [],
            }
        return ProviderModelResult(
            output=output,
            usage=ModelUsage(input_tokens=120, output_tokens=80),
            provider_request_id=f"clarifier-{len(self.requests)}",
        )


def _completed_patch() -> dict[str, Any]:
    return {
        "research_scope": "home_safety_ecosystem",
        "comparison_ecosystems": ["Ring", "Google Nest"],
        "target_users": ["独居老人及其授权照护者"],
        "markets": ["北美"],
        "time_horizon": "未来三年",
        "safety_goals": ["在危险动作发生前发现风险并请求确认"],
        "risk_scenarios": ["夜间楼梯活动", "异常离家"],
        "authorized_signal_types": [
            "motion_event",
            "door_event",
            "device_status",
            "user_confirmation",
        ],
        "privacy_boundary": {
            "raw_media_allowed": False,
            "restricted_zones": ["卧室", "卫生间"],
            "retention_policy": "仅保留去标识事件元数据 30 天",
            "external_sharing_allowed": False,
        },
        "intervention_boundary": {
            "allowed_interventions": [
                "continue_observing",
                "request_additional_signal",
                "ask_user",
            ],
            "prohibited_actions": ["未经确认联系急救或照护者", "进行医疗诊断"],
            "high_impact_action_requires_human_approval": True,
        },
        "forbidden_inferences": ["疾病诊断", "未经授权的身份识别"],
        "evaluation_dimensions": ["提前量", "误报率", "跨设备协作", "隐私"],
        "validation_expectations": ["使用模拟事件验证正常、危险和证据不足路径"],
        "source_permissions": {
            "public_sources": True,
            "user_uploaded_materials": True,
            "enterprise_internal_materials": False,
            "authorized_household_events": False,
        },
        "deliverables": ["ecosystem_opportunity_portfolio", "policy_dry_run"],
    }


def _flatten(payload: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    result = []
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.extend(_flatten(value, path))
        else:
            result.append((path, value))
    return result


@pytest.fixture
def clarifier_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("CLARIFIER_TEST_KEY", "test-only-secret")
    catalog = json.dumps(
        [
            {
                "model_id": "test:clarifier",
                "provider": "clarifier-test",
                "provider_model": "clarifier-model",
                "display_name": "Clarifier Test",
                "credential_env": "CLARIFIER_TEST_KEY",
                "capabilities": ["text", "structured_output"],
                "input_cost_microusd_per_million_tokens": 1_000_000,
                "output_cost_microusd_per_million_tokens": 2_000_000,
            }
        ]
    )
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'clarifier.db'}",
        auto_create_schema=True,
        model_catalog_json=catalog,
        default_model_id="test:clarifier",
        model_credentials_env_file=None,
        model_max_retries=0,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "source-processing"),
    )
    application = create_app(settings)
    provider = ClarifierProvider()
    application.state.model_provider_registry.register(provider)
    with TestClient(application) as client:
        client.app.state.clarifier_test_provider = provider
        yield client


def test_vague_goal_requires_questions_then_completed_brief_is_validated(
    clarifier_client: TestClient,
) -> None:
    started = clarifier_client.post(
        "/api/v1/research-brief-clarifications",
        json={"initial_question": "研究一下 eufy 未来的老人安防产品"},
    )
    assert started.status_code == 201
    first = started.json()
    assert first["status"] == "awaiting_user"
    assert first["draft"] == {
        "question": "研究一下 eufy 未来的老人安防产品",
        "research_scope": None,
        "safety_domains": ["elder_safety"],
        "target_ecosystems": ["eufy"],
        "comparison_ecosystems": None,
        "target_users": None,
        "markets": None,
        "time_horizon": None,
        "safety_goals": None,
        "risk_scenarios": None,
        "authorized_signal_types": None,
        "privacy_boundary": None,
        "intervention_boundary": None,
        "forbidden_inferences": None,
        "evaluation_dimensions": None,
        "validation_expectations": None,
        "source_permissions": None,
        "deliverables": None,
    }
    assert "privacy_boundary.raw_media_allowed" in first["missing_fields"]
    assert first["completed_brief"] is None
    assert len(first["questions"]) == 3

    answered = clarifier_client.post(
        f"/api/v1/research-brief-clarifications/{first['session_id']}/messages",
        json={
            "message": (
                "研究整个家庭安全生态，面向北美独居老人和授权照护者，周期未来三年；"
                "重点验证夜间楼梯和异常离家，交付生态机会组合和策略 dry-run。"
                "只允许动作、门、设备状态和用户确认事件；不允许原始音视频；"
                "卧室和卫生间受限；去标识事件元数据保留30天；禁止外部分享。"
                "只允许继续观察、请求额外信号和询问用户；禁止医疗诊断和未经确认联系第三方；"
                "高影响动作必须人工批准；禁止疾病诊断和未经授权身份识别。"
                "允许公开资料和用户上传；不允许企业内部资料与家庭事件。"
            ),
            "expected_version": first["version"],
        },
    )
    assert answered.status_code == 200
    final = answered.json()
    assert final["status"] == "ready_for_confirmation"
    assert final["missing_fields"] == []
    assert final["validation_issues"] == []
    assert final["questions"] == []
    assert final["completed_brief"]["research_scope"] == "home_safety_ecosystem"
    assert final["completed_brief"]["privacy_boundary"]["raw_media_allowed"] is False
    assert final["completed_brief"]["source_permissions"]["authorized_household_events"] is False
    assert final["version"] == 2
    assert final["input_tokens"] == 240
    assert final["output_tokens"] == 160
    assert final["estimated_cost_microusd"] == 560

    loaded = clarifier_client.get(
        f"/api/v1/research-brief-clarifications/{first['session_id']}"
    )
    assert loaded.status_code == 200
    assert loaded.json() == final
    provider = clarifier_client.app.state.clarifier_test_provider
    assert len(provider.requests) == 2
    assert all(request.credential == "test-only-secret" for request in provider.requests)


def test_answer_rejects_stale_version(clarifier_client: TestClient) -> None:
    started = clarifier_client.post(
        "/api/v1/research-brief-clarifications",
        json={"initial_question": "研究 eufy 老人家庭安全生态机会"},
    ).json()
    response = clarifier_client.post(
        f"/api/v1/research-brief-clarifications/{started['session_id']}/messages",
        json={"message": "补充范围", "expected_version": 99},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "BRIEF_CLARIFICATION_VERSION_CONFLICT"
