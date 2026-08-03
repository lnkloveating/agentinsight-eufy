from fastapi.testclient import TestClient


def project_payload() -> dict[str, object]:
    return {
        "brief": {
            "question": "eufy 是否应该为北美租房用户设计可迁移的家庭安防产品？",
            "category": "家庭安防",
            "target_user": "北美租房用户",
            "region": "美国和加拿大",
            "scenarios": ["门口访客", "搬家迁移"],
            "constraints": ["免打孔", "低订阅依赖"],
            "focus_dimensions": ["安装", "迁移"],
        }
    }


def test_create_list_get_and_approve_project(client: TestClient) -> None:
    create_response = client.post("/api/v1/projects", json=project_payload())
    assert create_response.status_code == 201
    project = create_response.json()
    project_id = project["project_id"]
    assert project["status"] == "awaiting_brief_approval"
    assert project["pending_decision"]["gate"] == "brief"

    list_response = client.get("/api/v1/projects")
    assert list_response.status_code == 200
    assert [item["project_id"] for item in list_response.json()] == [project_id]

    detail_response = client.get(f"/api/v1/projects/{project_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["brief"]["category"] == "家庭安防"

    agents_response = client.get(f"/api/v1/projects/{project_id}/agents")
    assert agents_response.status_code == 200
    agents = agents_response.json()
    assert len(agents) == 1
    assert agents[0]["agent_name"] == "调研总管 Agent"
    assert agents[0]["status"] == "waiting"

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
