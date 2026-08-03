"""可重复执行的 eufy 中文演示项目种子。"""

from datetime import UTC, datetime, timedelta

from app.application.events import ProjectEventBroker
from app.infrastructure.database.models import AgentRunModel, ProjectEventModel, ProjectModel
from app.infrastructure.database.repositories import ProjectRepository
from app.infrastructure.database.session import Database
from app.schemas.project import AgentRunStatus, ProjectStatus

DEMO_PROJECT_ID = "proj_demo_eufy"


async def seed_eufy_demo(database: Database, broker: ProjectEventBroker) -> str:
    """写入一条可供前端和现场演示使用的真实项目记录。"""
    async with database.session() as session:
        repository = ProjectRepository(session)
        if await repository.get_project(DEMO_PROJECT_ID) is not None:
            return DEMO_PROJECT_ID

        now = datetime.now(UTC)
        project = ProjectModel(
            project_id=DEMO_PROJECT_ID,
            status=ProjectStatus.RESEARCHING,
            current_stage="competitor_research",
            progress=42,
            brief_json={
                "question": "eufy 是否应该为北美租房用户设计可迁移的家庭安防产品？",
                "category": "家庭安防",
                "target_user": "美国和加拿大需要自行安装安防设备的租房个人或家庭",
                "region": "北美，优先美国",
                "scenarios": ["门口访客", "包裹", "离家看护", "室友共享", "搬家迁移"],
                "constraints": ["免打孔", "低订阅依赖", "隐私边界清晰"],
                "focus_dimensions": ["安装", "迁移", "权限", "总拥有成本"],
            },
            pending_decision_json=None,
            created_at=now - timedelta(minutes=8),
            updated_at=now,
        )
        await repository.add_project(project)

        agents = [
            AgentRunModel(
                agent_run_id="run_demo_manager",
                project_id=DEMO_PROJECT_ID,
                agent_type="research_manager",
                agent_name="调研总管 Agent",
                status=AgentRunStatus.RUNNING,
                progress=55,
                message="正在汇总用户与竞品研究进度。",
                started_at=now - timedelta(minutes=7),
            ),
            AgentRunModel(
                agent_run_id="run_demo_user",
                project_id=DEMO_PROJECT_ID,
                agent_type="user_research",
                agent_name="用户研究 Agent",
                status=AgentRunStatus.COMPLETED,
                progress=100,
                message="已完成租房用户安装与订阅痛点聚类。",
                started_at=now - timedelta(minutes=6),
                completed_at=now - timedelta(minutes=2),
            ),
            AgentRunModel(
                agent_run_id="run_demo_competitor",
                project_id=DEMO_PROJECT_ID,
                agent_type="competitor_research",
                agent_name="竞品研究 Agent",
                status=AgentRunStatus.RUNNING,
                progress=46,
                message="正在核对 Ring、Nest、Arlo、Reolink 与 Tapo。",
                started_at=now - timedelta(minutes=4),
            ),
            AgentRunModel(
                agent_run_id="run_demo_technical",
                project_id=DEMO_PROJECT_ID,
                agent_type="technical_research",
                agent_name="产品技术 Agent",
                status=AgentRunStatus.QUEUED,
                progress=0,
                message="等待用户和竞品证据达到覆盖门槛。",
            ),
            AgentRunModel(
                agent_run_id="run_demo_commercial",
                project_id=DEMO_PROJECT_ID,
                agent_type="commercial_research",
                agent_name="商业分析 Agent",
                status=AgentRunStatus.QUEUED,
                progress=0,
                message="等待价格和订阅数据。",
            ),
            AgentRunModel(
                agent_run_id="run_demo_red_team",
                project_id=DEMO_PROJECT_ID,
                agent_type="red_team",
                agent_name="红队 Agent",
                status=AgentRunStatus.QUEUED,
                progress=0,
                message="将在候选概念生成后开始审查。",
            ),
        ]
        for agent in agents:
            await repository.add_agent_run(agent)

        events = [
            (
                "project_created",
                {
                    "status": ProjectStatus.AWAITING_BRIEF_APPROVAL,
                    "current_stage": "brief_confirmation",
                    "progress": 5,
                    "message": "研究项目已创建，等待确认 Brief。",
                },
            ),
            (
                "project_status_changed",
                {
                    "previous_status": ProjectStatus.AWAITING_BRIEF_APPROVAL,
                    "status": ProjectStatus.RESEARCHING,
                    "current_stage": "research_planning",
                    "progress": 10,
                    "message": "Brief 已批准，开始规划研究。",
                },
            ),
            (
                "agent_status_changed",
                {
                    "agent_run_id": "run_demo_user",
                    "agent_name": "用户研究 Agent",
                    "status": AgentRunStatus.COMPLETED,
                    "progress": 100,
                    "message": "已完成租房用户痛点聚类。",
                },
            ),
            (
                "agent_status_changed",
                {
                    "agent_run_id": "run_demo_competitor",
                    "agent_name": "竞品研究 Agent",
                    "status": AgentRunStatus.RUNNING,
                    "progress": 46,
                    "message": "正在分析竞品官方产品与订阅方案。",
                },
            ),
        ]
        for index, (event_type, data) in enumerate(events):
            await repository.add_event(
                ProjectEventModel(
                    event_id=f"evt_demo_{index + 1:03d}",
                    project_id=DEMO_PROJECT_ID,
                    sequence_number=0,
                    event_type=event_type,
                    data_json=data,
                    trace_id="trace_demo_eufy",
                    created_at=now - timedelta(minutes=7 - index),
                )
            )

        await repository.commit()

    await broker.notify(DEMO_PROJECT_ID)
    return DEMO_PROJECT_ID
