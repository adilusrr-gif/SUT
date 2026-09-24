from typing import Literal
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Süt • Рацион"
    database_url: str = "postgresql+psycopg://sut:sut@db:5432/sut"
    app_access_token: SecretStr = SecretStr("")
    llm_provider: Literal['openai', 'ollama', 'disabled'] = 'openai'
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = 'gpt-4o-mini'
    llm_timeout_seconds: float = Field(default=20, ge=1, le=45)
    llm_max_output_tokens: int = Field(default=128, ge=64, le=1024)
    llm_daily_call_limit: int = Field(default=100, ge=0, le=10000)
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "deepseek-r1:14b"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    demo_seed: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

settings = Settings()
