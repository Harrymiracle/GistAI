from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """应用运行配置。"""

    database_url: str = "postgresql+psycopg://gistai:gistai@localhost:5432/gistai"
    fetch_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    fetch_max_redirects: int = Field(default=5, ge=0, le=10)
    fetch_min_content_chars: int = Field(default=200, ge=1, le=10_000)
    fetch_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 GistAI/1.0"
        ),
        min_length=1,
    )

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """返回缓存后的应用配置。"""

    return Settings()


settings = get_settings()
