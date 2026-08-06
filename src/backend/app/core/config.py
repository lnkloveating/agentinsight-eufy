"""应用配置。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量读取的后端配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AgentInsight × eufy API"
    app_version: str = "0.2.0"
    app_env: str = "development"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite+aiosqlite:///./data/agentinsight.db"
    auto_create_schema: bool = True
    frontend_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    sse_heartbeat_seconds: float = 15.0
    model_catalog_json: str = "[]"
    default_model_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    """返回进程级配置单例。"""
    return Settings()
