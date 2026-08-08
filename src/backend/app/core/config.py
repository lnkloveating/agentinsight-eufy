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
    user_research_max_evidence_items: int = Field(default=30, ge=1, le=200)
    user_research_max_excerpt_chars: int = Field(default=2_000, ge=200, le=10_000)
    user_research_max_total_evidence_chars: int = Field(default=40_000, ge=1_000, le=500_000)
    competitor_a2a_specialist_timeout_seconds: float = Field(default=300, ge=0.1, le=3_600)
    competitor_official_max_evidence_items: int = Field(default=40, ge=1, le=200)
    competitor_official_max_excerpt_chars: int = Field(default=3_000, ge=200, le=10_000)
    competitor_official_max_total_evidence_chars: int = Field(default=60_000, ge=1_000, le=500_000)
    competitor_official_model_timeout_seconds: float = Field(default=180, ge=1, le=600)
    source_storage_root: str = "./data/sources"
    source_processing_workspace_root: str = "./data/source-processing"
    source_processing_max_input_bytes: int = Field(default=52_428_800, ge=1, le=536_870_912)
    source_processing_max_fragments: int = Field(default=5_000, ge=1, le=50_000)
    source_processing_max_excerpt_chars: int = Field(default=4_000, ge=200, le=20_000)
    web_connector_enabled: bool = True
    web_connector_user_agent: str = "AgentInsightResearchBot/0.1"
    web_connector_timeout_seconds: float = Field(default=20.0, ge=1, le=120)
    web_connector_max_response_bytes: int = Field(default=5_242_880, ge=1_024, le=52_428_800)
    web_connector_max_redirects: int = Field(default=5, ge=0, le=10)
    web_connector_respect_robots_txt: bool = True
    web_connector_allowed_domains: list[str] = Field(default_factory=list)
    media_processing_max_duration_seconds: float = Field(default=1_800, ge=1, le=14_400)
    media_processing_max_streams: int = Field(default=8, ge=1, le=32)
    media_processing_frame_interval_seconds: float = Field(default=10, ge=0.5, le=600)
    media_processing_max_frames: int = Field(default=60, ge=1, le=1_000)
    media_processing_max_frame_dimension: int = Field(default=1_280, ge=64, le=4_096)
    media_processing_max_decoded_video_frames: int = Field(default=100_000, ge=1, le=2_000_000)
    media_processing_audio_sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    media_processing_max_audio_bytes: int = Field(default=115_200_000, ge=1_024, le=1_073_741_824)
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
