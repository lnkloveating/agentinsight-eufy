from fastapi.testclient import TestClient

from tests.research_brief import home_safety_brief_payload


def project_payload() -> dict[str, object]:
    return {
        "brief": home_safety_brief_payload(
            "eufy 如何为北美租房家庭构建可迁移、可验证的 AI 原生安防生态？"
        )
    }


def test_create_list_get_and_approve_project(client: TestClient) -> None:
    create_response = client.post("/api/v1/projects", json=project_payload())
    assert create_response.status_code == 201
    project = create_response.json()
    project_id = project["project_id"]
    assert project["status"] == "awaiting_brief_approval"
    assert project["model_selection"] is None
    assert project["pending_decision"]["gate"] == "brief"

    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    assert [item["project_id"] for item in list_response.json()] == [project_id]

    detail_response = client.get(f"/api/v1/projects/{project_id}")
    assert detail_response.status_code == 200
    brief = detail_response.json()["brief"]
    assert brief["research_scope"] == "home_safety_ecosystem"
    assert brief["target_ecosystems"] == ["eufy Security"]
    assert "category" not in brief

    agents_response = client.get(f"/api/v1/projects/{project_id}/agents")
    assert agents_response.status_code == 200
    agents = agents_response.json()
    assert len(agents) == 1
    assert agents[0]["agent_name"] == "调研总管 Agent"
    assert agents[0]["status"] == "waiting"
    assert agents[0]["task_id"] is None
    assert agents[0]["quality_score"] == 0
    assert agents[0]["evidence_ids"] == []
    assert agents[0]["unknowns"] == []
    assert agents[0]["model_id"] is None
    assert agents[0]["model_provider"] is None
    assert agents[0]["prompt_key"] is None
    assert agents[0]["prompt_version"] is None
    assert agents[0]["input_tokens"] == 0
    assert agents[0]["output_tokens"] == 0
    assert agents[0]["estimated_cost_microusd"] == 0

    decision_response = client.post(
        f"/api/v1/projects/{project_id}/decisions",
        json={
            "decision_id": project["pending_decision"]["decision_id"],
            "action": "approve",
            "reason": "Brief 范围明确，批准开始研究。",
            "actor": "产品经理",
            "selected_concept_ids": [],
        },
    )
    assert decision_response.status_code == 202
    assert decision_response.json()["status"] == "researching"
    assert decision_response.json()["current_stage"] == "research_planning"

    agents_after_approval = client.get(f"/api/v1/projects/{project_id}/agents").json()
    assert agents_after_approval[0]["status"] == "running"
    assert agents_after_approval[0]["message"] == "Brief 已通过，正在规划调研任务。"


def test_project_not_found_uses_chinese_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/projects/proj_missing")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "PROJECT_NOT_FOUND"
    assert body["message"] == "没有找到指定的研究项目。"
    assert body["trace_id"].startswith("trace_")


def test_legacy_single_product_brief_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={
            "brief": {
                "question": "分析 eufy 未来产品机会",
                "category": "家庭安防",
                "target_user": "北美家庭",
                "region": "US",
                "scenarios": ["package delivery"],
            }
        },
    )

    assert response.status_code == 422
    serialized = response.text
    assert "research_scope" in serialized
    assert "category" in serialized


def test_rejects_mismatched_decision_id(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json=project_payload()).json()
    response = client.post(
        f"/api/v1/projects/{project['project_id']}/decisions",
        json={
            "decision_id": "decision_wrong",
            "action": "approve",
            "reason": "测试错误审批编号。",
            "actor": "测试人员",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "DECISION_ID_MISMATCH"
