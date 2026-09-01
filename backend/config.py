from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    unity_bridge_url: str = Field(default="http://127.0.0.1", validation_alias="UNITY_BRIDGE_URL")
    unity_bridge_port: int = Field(default=7890, validation_alias="UNITY_BRIDGE_PORT")
    unity_bridge_fallback_port: int = Field(default=7891, validation_alias="UNITY_BRIDGE_FALLBACK_PORT")
    unity_bridge_timeout_seconds: float = Field(default=10.0, validation_alias="UNITY_BRIDGE_TIMEOUT_SECONDS")
    unity_bridge_ping_timeout_seconds: float = Field(default=2.0, validation_alias="UNITY_BRIDGE_PING_TIMEOUT_SECONDS")
    unity_bridge_ports_to_scan: list[int] = Field(
        default_factory=lambda: [7890, 7891, 7892, 7893], validation_alias="UNITY_BRIDGE_PORTS_TO_SCAN"
    )
    unity_bridge_max_retries: int = Field(default=2, validation_alias="UNITY_BRIDGE_MAX_RETRIES")
    unity_bridge_retry_backoff: float = Field(default=0.5, validation_alias="UNITY_BRIDGE_RETRY_BACKOFF")
    unity_bridge_mode: str = Field(default="auto", validation_alias="UNITY_BRIDGE_MODE")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("unity_bridge_ports_to_scan", mode="before")
    @classmethod
    def parse_ports_to_scan(cls, value: Any) -> list[int]:
        if isinstance(value, str):
            return [int(p.strip()) for p in value.split(",") if p.strip().isdigit()]
        if isinstance(value, (list, tuple, set)):
            return [int(p) for p in value]
        return [7890, 7891, 7892, 7893]

    @field_validator("unity_bridge_url")
    @classmethod
    def normalize_bridge_url(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("unity_bridge_mode")
    @classmethod
    def normalize_bridge_mode(cls, value: str) -> str:
        val = value.lower().strip()
        return val if val in {"auto", "native", "legacy"} else "auto"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
