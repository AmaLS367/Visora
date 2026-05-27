from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    unity_bridge_url: str = Field(default="http://127.0.0.1", validation_alias="UNITY_BRIDGE_URL")
    unity_bridge_port: int = Field(default=7890, validation_alias="UNITY_BRIDGE_PORT")
    unity_bridge_fallback_port: int = Field(default=7891, validation_alias="UNITY_BRIDGE_FALLBACK_PORT")
    unity_bridge_timeout_seconds: float = Field(default=10.0, validation_alias="UNITY_BRIDGE_TIMEOUT_SECONDS")
    unity_bridge_ping_timeout_seconds: float = Field(default=2.0, validation_alias="UNITY_BRIDGE_PING_TIMEOUT_SECONDS")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("unity_bridge_url")
    @classmethod
    def normalize_bridge_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
