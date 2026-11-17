from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[1]
class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(APP_ROOT / ".env",),
        env_file_encoding="utf-8",
        extra="ignore",
    )
class DbSettings(EnvSettings):
    user:str=Field(alias="MYSQL_USER")
    password:str=Field(alias="MYSQL_PASSWORD")
    host:str=Field(alias="MYSQL_HOST")
    port:int=Field(alias="MYSQL_PORT")
    db:str=Field(alias="MYSQL_DB")

class AgentSettings(EnvSettings):
    max:int =Field(alias="MAX_RETRIES")
class LlmSettings(EnvSettings):
    base_url:str=Field(alias="LLM_BASE_URL")
    model:str=Field(alias="LLM_MODEL")
    api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    provider: str = Field(default="mock", alias="LLM_PROVIDER")
    timeout: float = Field(default=150.0, alias="LLM_TIMEOUT")


class Settings(BaseSettings):
    db:DbSettings=Field(default_factory=DbSettings)
    agent:AgentSettings=Field(default_factory=AgentSettings)
    llm:LlmSettings=Field(default_factory=LlmSettings)


settings = Settings()

