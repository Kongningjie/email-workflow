from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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

    @field_validator("data_dir", "config_dir", "frontend_dist_dir", mode="after")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
