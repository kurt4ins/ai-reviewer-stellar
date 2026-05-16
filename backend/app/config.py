from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).resolve()
_ENV_CANDIDATES = (
    _HERE.parent.parent / ".env",
    _HERE.parent.parent.parent / ".env",
    Path.cwd() / ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(str(p) for p in _ENV_CANDIDATES),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "stellar"
    postgres_user: str = "stellar"
    postgres_password: str = "stellar_dev_password"

    redis_url: str = "redis://localhost:6379/0"

    webhook_base_url: str = "http://localhost:8000"

    log_level: str = "INFO"

    fernet_key: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    default_classifier_model: str = "deepseek/deepseek-v4-flash:free"
    default_analyzer_model: str = "qwen/qwen3-coder:free"
    llm_timeout: float = 120.0
    llm_max_retries: int = 5

    github_api_url: str = "https://api.github.com"
    gitlab_api_url: str = "https://gitlab.com/api/v4"
    git_http_timeout: float = 30.0

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
