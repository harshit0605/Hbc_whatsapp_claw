"""Env-driven config. Reads from .env at process start."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://society:society_dev_password@localhost:5432/society"
    )
    sync_database_url: str = Field(
        default="postgresql://society:society_dev_password@localhost:5432/society"
    )

    # Object storage
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minio_admin"
    s3_secret_access_key: str = "minio_admin_password"
    s3_bucket: str = "society-media"
    s3_region: str = "auto"
    s3_public_base_url: str = "http://localhost:9000"

    # Claude
    anthropic_api_key: str = "sk-ant-replace-me"
    claude_conversation_model: str = "claude-sonnet-4-6"
    claude_classifier_model: str = "claude-haiku-4-5-20251001"

    # HTTP API
    skills_http_host: str = "0.0.0.0"
    skills_http_port: int = 8080
    skills_http_internal_token: str = "dev-token"
    skills_media_url_ttl_seconds: int = 900

    # OpenCLAW outbound bridge
    openclaw_outbound_url: str = "http://localhost:7787/v1/messages"
    openclaw_outbound_token: str = "dev-token"

    # Admin alerting
    admin_alert_jids: str = ""

    @property
    def admin_alert_jid_list(self) -> list[str]:
        return [j.strip() for j in self.admin_alert_jids.split(",") if j.strip()]

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
