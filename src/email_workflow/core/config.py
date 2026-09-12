from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量加载并一次性验证运行配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "邮件驱动测试计划自动化平台"
    app_env: Literal["development", "test", "production"] = "development"
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = (
        "postgresql+asyncpg://email_workflow:email_workflow@localhost:5432/email_workflow"
    )
    data_dir: Path = Path("data")
    config_dir: Path = Path("config")
    frontend_dist_dir: Path = Path("frontend/dist")
    dashscope_api_key: SecretStr | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen3.7-plus-2026-05-26"
    mock_gateway_base_url: str = "http://localhost:8001"
    mock_gateway_key_id: str = "local-demo"
    mock_gateway_hmac_secret: SecretStr = Field(
        default=SecretStr("replace-with-a-local-demo-secret")
    )
    run_live_llm_tests: bool = False
    max_upload_bytes: int = 5 * 1024 * 1024
    max_clean_body_chars: int = 200_000
    max_header_count: int = 200
    max_header_value_chars: int = 16_384
    max_mime_depth: int = 10
    max_mime_parts: int = 100
    evidence_segment_chars: int = 1_000
    evidence_overlap_chars: int = 100
    raw_retention_hours: int = 24
    evidence_retention_days: int = 90

    @field_validator("data_dir", "config_dir", "frontend_dist_dir", mode="after")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator(
        "max_upload_bytes",
        "max_clean_body_chars",
        "max_header_count",
        "max_header_value_chars",
        "max_mime_depth",
        "max_mime_parts",
        "evidence_segment_chars",
        "raw_retention_hours",
        "evidence_retention_days",
    )
    @classmethod
    def positive_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("安全限制必须大于零")
        return value

    @field_validator("evidence_overlap_chars")
    @classmethod
    def valid_overlap(cls, value: int, info: ValidationInfo) -> int:
        if value < 0:
            raise ValueError("证据重叠长度不得为负数")
        segment_chars = info.data.get("evidence_segment_chars")
        if isinstance(segment_chars, int) and value >= segment_chars:
            raise ValueError("证据重叠长度必须小于切片长度")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
