import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.application.evidence import EvidenceRetrievalService
from app.core.config import Settings
from app.infrastructure.database import Database
from app.infrastructure.database.models import EvidenceModel, ProjectModel
from app.main import create_app
from app.schemas.evidence import EvidenceClaimType, EvidenceStatus
from app.schemas.evidence_retrieval import (
    EvidenceRetrievalQuery,
    EvidenceRetrievalStrategy,
)


def _project(project_id: str) -> ProjectModel:
    now = datetime.now(UTC)
    return ProjectModel(
        project_id=project_id,
        status="researching",
        current_stage="parallel_research",
        progress=20,
        brief_json={
            "question": "分析家庭安防未来产品机会",
            "category": "家庭安防",
            "target_user": "北美家庭用户",
            "region": "US",
            "scenarios": ["门前包裹"],
            "constraints": [],
            "focus_dimensions": [],
        },
        created_at=now,
        updated_at=now,
    )


def _evidence(
    evidence_id: str,
    project_id: str,
    *,
    title: str,
    excerpt: str,
    domain: str,
    status: EvidenceStatus = EvidenceStatus.VERIFIED,
    claim_type: EvidenceClaimType = EvidenceClaimType.USER_OPINION,
    product: str | None = "eufy Doorbell",
    region: str | None = "US",
    quality: float = 0.8,
) -> EvidenceModel:
    now = datetime.now(UTC)
    return EvidenceModel(
        evidence_id=evidence_id,
        project_id=project_id,
        source_url=f"https://{domain}/{evidence_id}",
        normalized_source_url=f"https://{domain}/{evidence_id}",
        source_domain=domain,
        source_type="webpage",
        title=title,
        original_excerpt=excerpt,
        claim_type=claim_type.value,
        product=product,
        region=region,
        collected_at=now,
        status=status.value,
        content_hash=(evidence_id.removeprefix("ev_") + "0" * 64)[:64],
        confidence=quality,
        authority_score=quality,
        recency_score=quality,
        diversity_score=quality,
    )


async def _seed(database: Database) -> None:
    async with database.session() as session:
        session.add_all(
            [
                _project("proj_shared_retrieval"),
                _project("proj_other_retrieval"),
                _evidence(
                    "ev_rain_risk",
                    "proj_shared_retrieval",
                    title="包裹天气风险反馈",
                    excerpt="用户担心门口包裹在下雨时被淋湿。",
                    domain="reviews.example",
                    quality=0.75,
                ),
                _evidence(
                    "ev_rain_partial",
                    "proj_shared_retrieval",
                    title="门铃包裹提醒",
                    excerpt="包裹天气风险需要结合送达时间和天气信息。",
                    domain="community.example",
                    status=EvidenceStatus.PARTIALLY_VERIFIED,
                    quality=0.65,
                ),
                _evidence(
                    "ev_rain_same_source",
                    "proj_shared_retrieval",
                    title="包裹天气风险长期反馈",
                    excerpt="用户多次查看门铃以确认包裹是否面临天气风险。",
                    domain="reviews.example",
                    quality=0.95,
                ),
                _evidence(
                    "ev_unrelated_high_quality",
                    "proj_shared_retrieval",
                    title="摄像头安装说明",
                    excerpt="安装支架需要固定在墙面。",
                    domain="manual.example",
                    claim_type=EvidenceClaimType.TECHNICAL_FACT,
                    quality=0.99,
                ),
                _evidence(
                    "ev_unverified_rain",
                    "proj_shared_retrieval",
                    title="未审核包裹天气风险",
                    excerpt="这条内容尚未经过 Evidence 审核。",
                    domain="unknown.example",
                    status=EvidenceStatus.UNVERIFIED,
                ),
                _evidence(
                    "ev_other_project_rain",
                    "proj_other_retrieval",
                    title="其他项目包裹天气风险",
                    excerpt="这个 Evidence 不能跨项目返回。",
                    domain="private.example",
                ),
            ]
        )
        await session.commit()


@pytest.mark.asyncio
async def test_shared_retrieval_is_project_scoped_and_lexically_relevant() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        await _seed(database)
        result = await EvidenceRetrievalService(database).retrieve(
            "proj_shared_retrieval",
            EvidenceRetrievalQuery(
                consumer="commercial_evaluation",
                question="包裹天气风险",
                require_text_match=True,
                max_items=10,
                candidate_limit=20,
            ),
        )

        assert result.strategy is EvidenceRetrievalStrategy.LEXICAL_METADATA
        assert result.candidate_evidence_count == 4
        assert result.context.available_evidence_count == 3
        included_ids = [item.evidence_id for item in result.context.items]
        assert included_ids == [
            "ev_rain_same_source",
            "ev_rain_partial",
            "ev_rain_risk",
        ]
        assert result.context.items[0].source_domain != result.context.items[1].source_domain
        assert all(match.matched_terms for match in result.matches)
        assert "ev_unverified_rain" not in {
            item.evidence_id for item in result.context.items
        }
        assert "ev_other_project_rain" not in {
            item.evidence_id for item in result.context.items
        }
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_exact_retrieval_preserves_handoff_order_and_metadata_boundaries() -> None:
    database = Database("sqlite+aiosqlite:///:memory:")
    await database.create_schema()
    try:
        await _seed(database)
        result = await EvidenceRetrievalService(database).retrieve(
            "proj_shared_retrieval",
            EvidenceRetrievalQuery(
                consumer="product_technical",
                evidence_ids=[
                    "ev_unrelated_high_quality",
                    "ev_rain_risk",
                    "ev_other_project_rain",
                ],
                products=["EUFY DOORBELL"],
                regions=["us"],
                preserve_evidence_order=True,
                diversify_sources=False,
                max_items=3,
                candidate_limit=3,
            ),
        )

        assert result.strategy is EvidenceRetrievalStrategy.EXACT_EVIDENCE_IDS
        assert [item.evidence_id for item in result.context.items] == [
            "ev_unrelated_high_quality",
            "ev_rain_risk",
        ]
        assert result.context.available_evidence_count == 2
        assert all(
            "evidence_id_boundary" in match.match_reasons for match in result.matches
        )
    finally:
        await database.dispose()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'retrieval-api.db'}",
        auto_create_schema=True,
        model_credentials_env_file=None,
        source_storage_root=str(tmp_path / "sources"),
        source_processing_workspace_root=str(tmp_path / "processing"),
    )


def test_shared_retrieval_http_contract_returns_evidence_context(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        asyncio.run(_seed(app.state.database))
        response = client.post(
            "/api/v1/projects/proj_shared_retrieval/evidence/retrievals",
            json={
                "consumer": "red_team",
                "question": "包裹天气风险",
                "claim_types": ["user_opinion"],
                "require_text_match": True,
                "max_items": 5,
                "candidate_limit": 20,
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["strategy"] == "lexical_metadata"
        assert body["context"]["included_evidence_count"] == 3
        assert body["query_hash"]
        assert all(item["evidence_id"].startswith("ev_rain") for item in body["context"]["items"])
