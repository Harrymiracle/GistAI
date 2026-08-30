from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """应用运行配置。"""

    database_url: str = "postgresql+psycopg://gistai:gistai@localhost:5432/gistai"
    fetch_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    fetch_max_redirects: int = Field(default=5, ge=0, le=10)
    fetch_min_content_chars: int = Field(default=200, ge=1, le=10_000)
    playwright_navigation_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    playwright_network_idle_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    embedding_base_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    embedding_model: str = "text-embedding-v4"
    embedding_dimension: int = Field(default=1024, ge=1, le=4096)
    embedding_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    embedding_batch_size: int = Field(default=10, ge=1, le=100)
    rag_chunk_size: int = Field(default=400, ge=1, le=8192)
    rag_chunk_overlap: int = Field(default=80, ge=0, le=8191)
    rag_top_k: int = Field(default=3, ge=1, le=50)
    rag_similarity_threshold: float = Field(default=0.35, ge=-1.0, le=1.0)
    rag_max_context_chars: int = Field(default=12_000, ge=1_000, le=100_000)
    fetch_user_agent: str = Field(
        default=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36 GistAI/1.0"
        ),
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> "Settings":
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP 必须小于 RAG_CHUNK_SIZE")
        return self

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
