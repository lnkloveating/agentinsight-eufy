"""启动、恢复、重试和读取 LangGraph Checkpoint 的应用边界。"""

from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel, Field

from app.workflows.contracts import ResearchState, StageDecision
from app.workflows.graph import CompiledResearchGraph


class WorkflowSnapshot(BaseModel):
    thread_id: str
    checkpoint_id: str | None = None
    next_nodes: list[str] = Field(default_factory=list)
    values: dict[str, Any] = Field(default_factory=dict)


class WorkflowRunner:
    """让后续 API/Runtime 分支不直接依赖 LangGraph 调用细节。"""

    def __init__(self, graph: CompiledResearchGraph) -> None:
        self.graph = graph

    async def start(self, state: ResearchState) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self.graph.ainvoke(state, self._config(state["project_id"])),
        )

    async def resume(self, project_id: str, decision: StageDecision) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self.graph.ainvoke(
                Command(resume=decision.model_dump(mode="json")),
                self._config(project_id),
            ),
        )

    async def retry(self, project_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self.graph.ainvoke(None, self._config(project_id)),
        )

    async def snapshot(self, project_id: str) -> WorkflowSnapshot:
        state = await self.graph.aget_state(self._config(project_id))
        configurable = state.config.get("configurable", {})
        checkpoint_id = configurable.get("checkpoint_id")
        return WorkflowSnapshot(
            thread_id=project_id,
            checkpoint_id=str(checkpoint_id) if checkpoint_id is not None else None,
            next_nodes=list(state.next),
            values=dict(state.values),
        )

    @staticmethod
    def _config(project_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": project_id}}
