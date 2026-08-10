from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_brief_clarification_migration_upgrades_and_downgrades() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

        inspector = inspect(connection)
        assert "brief_clarification_sessions" in inspector.get_table_names()
        model_call_columns = {
            str(item["name"]): item for item in inspector.get_columns("model_calls")
        }
        assert model_call_columns["clarification_session_id"]["nullable"] is True
        assert model_call_columns["project_id"]["nullable"] is True
        assert model_call_columns["agent_run_id"]["nullable"] is True

        command.downgrade(config, "0019_device_capability_graph")
        inspector = inspect(connection)
        assert "brief_clarification_sessions" not in inspector.get_table_names()
        model_call_columns = {
            str(item["name"]): item for item in inspector.get_columns("model_calls")
        }
        assert "clarification_session_id" not in model_call_columns
        assert model_call_columns["project_id"]["nullable"] is False
        assert model_call_columns["agent_run_id"]["nullable"] is False
