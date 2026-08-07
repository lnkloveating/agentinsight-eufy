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
    model_credentials_env_file: str | None = ".env"
    openai_compatible_providers_json: str = "[]"
    default_model_id: str | None = None
    model_max_retries: int = Field(default=2, ge=0, le=5)
    model_retry_base_seconds: float = Field(default=0.5, ge=0, le=30)
    source_storage_root: str = "./data/sources"
    source_max_upload_bytes: int = Field(
        default=262_144_000,
        ge=1,
        le=2_147_483_648,
    )
    external_runtime_workspace_root: str = "./data/runtime"
    external_cli_max_output_bytes: int = Field(
        default=4_194_304,
        ge=1_024,
        le=67_108_864,
    )
    external_cli_probe_timeout_seconds: float = Field(default=5.0, ge=0.1, le=30)
    opencode_runtime_enabled: bool = True
    opencode_executable: str = "opencode"
    opencode_provider_id: str = "anker-router"
    opencode_provider_name: str = "Anker Router"
    opencode_provider_base_url: str = "https://ai-router-cn-pub.anker-in.com"
    opencode_provider_model: str = "hackathon/v_model/glm-5.2"
    opencode_credential_env: str = "ANKER_ROUTER_API_KEY"


@lru_cache
def get_settings() -> Settings:
    """返回进程级配置单例。"""
    return Settings()
