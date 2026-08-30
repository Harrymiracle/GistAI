from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """应用运行配置。"""

    database_url: str = "postgresql+psycopg://gistai:gistai@localhost:5432/gistai"

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
