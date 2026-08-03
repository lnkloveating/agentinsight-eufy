"""项目生命周期的持久化模型。"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.base import Base


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)


class ProjectModel(Base):
    """研究项目及其当前状态。"""

    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    current_stage: Mapped[str] = mapped_column(String(80), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    pending_decision_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    agent_runs: Mapped[list["AgentRunModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    events: Mapped[list["ProjectEventModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["DecisionModel"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class AgentRunModel(Base):
    """一个 Agent 在项目中的运行记录。"""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_project_status", "project_id", "status"),)

    agent_run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(80), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[ProjectModel] = relationship(back_populates="agent_runs")


class ProjectEventModel(Base):
    """可回放的项目领域事件。"""

    __tablename__ = "project_events"
    __table_args__ = (
        UniqueConstraint("project_id", "sequence_number", name="uq_project_event_sequence"),
        Index("ix_project_events_project_created", "project_id", "created_at"),
    )

    event_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="events")


class DecisionModel(Base):
    """人工审批和流程恢复决定。"""

    __tablename__ = "decisions"
    __table_args__ = (Index("ix_decisions_project_created", "project_id", "created_at"),)

    decision_record_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True
    )
    gate: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    selected_concept_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    trace_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    project: Mapped[ProjectModel] = relationship(back_populates="decisions")
