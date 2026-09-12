from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    n8n_base_url: str | None = None
    n8n_api_key: SecretStr = SecretStr("")
    database_url: str = "sqlite:///./flowmedic.db"
    request_timeout: float = Field(default=15, gt=0, le=120)
    ai_api_key: SecretStr = SecretStr("")
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4.1-mini"
    flowmedic_api_key: SecretStr = SecretStr("")
    demo_mode: bool = False
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    monitor_poll_interval_seconds: float = Field(default=60, ge=10, le=3600)
    monitor_page_size: int = Field(default=50, ge=1, le=100)
    monitor_max_retries: int = Field(default=3, ge=0, le=5)
    monitor_retry_base_seconds: float = Field(default=2, gt=0, le=60)

    @field_validator("n8n_base_url", "ai_base_url")
    @classmethod
    def valid_url(cls, value):
        if value is None:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Expected an HTTP(S) base URL without credentials, query or fragment")
        return value.rstrip("/")

    @model_validator(mode="after")
    def key_requires_url(self):
        if self.n8n_api_key.get_secret_value() and not self.n8n_base_url:
            raise ValueError("N8N_BASE_URL is required when N8N_API_KEY is set")
        if self.demo_mode and (
            self.n8n_api_key.get_secret_value() or self.ai_api_key.get_secret_value()
        ):
            raise ValueError("DEMO_MODE cannot be used with N8N_API_KEY or AI_API_KEY")
        return self
