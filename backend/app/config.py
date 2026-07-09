from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://rag:rag_password@localhost:5432/rag_pageindex"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "dev-secret-change-me"
    session_cookie_name: str = "rag_session"
    access_token_expire_minutes: int = 60 * 24

    admin_email: str = "admin@example.com"
    admin_password: str = "change-me-now"

    openai_api_key: Optional[str] = None
    api_provider: str = "openai"
    openai_base_url: Optional[str] = None
    openai_chat_model: str = "gpt-5.4-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    openai_temperature: float = 0.1
    use_fake_openai: bool = False

    rag_storage_dir: str = "./data"
    max_upload_mb: int = 50
    frontend_origin: str = "http://localhost:3111"
    cors_origins: List[str] = Field(default_factory=list)

    enable_rag_anything: bool = True
    rag_anything_parser: str = "mineru"
    pageindex_min_pages: int = 30
    pageindex_command: Optional[str] = None
    sync_ingestion_on_queue_failure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("openai_api_key", "openai_base_url", "pageindex_command", mode="before")
    @classmethod
    def blank_string_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def all_cors_origins(self) -> List[str]:
        origins = list(self.cors_origins)
        if self.frontend_origin and self.frontend_origin not in origins:
            origins.append(self.frontend_origin)
        return origins

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache
def get_settings() -> Settings:
    return Settings()
