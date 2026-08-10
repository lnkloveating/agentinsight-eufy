from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_device_capability_migration_upgrades_and_downgrades() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        inspector = inspect(connection)
        assert {
            "device_catalog",
            "device_capability_claims",
            "household_device_snapshots",
            "household_devices",
            "household_device_relations",
        }.issubset(set(inspector.get_table_names()))
        assert "household_device_record_id" in {
            str(item["name"]) for item in inspector.get_columns("household_devices")
        }
        assert "relation_record_id" in {
            str(item["name"])
            for item in inspector.get_columns("household_device_relations")
        }

        command.downgrade(config, "0018_universal_agent_recovery")
        remaining = set(inspect(connection).get_table_names())
        assert "device_catalog" not in remaining
        assert "household_device_snapshots" not in remaining
