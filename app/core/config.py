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
        return self
