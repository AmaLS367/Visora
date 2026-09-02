import re
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    # NoDecode: pydantic-settings otherwise JSON-decodes list-typed env values before our
    # validator ever runs, so a plain comma-separated string (the documented .env format, e.g.
    # "7890,7891,7892,7893") crashes Settings() outright with a JSONDecodeError instead of being
    # parsed by parse_ports_to_scan below. Verified live: setting this var in .env as documented
    # broke server startup entirely.
    unity_bridge_ports_to_scan: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [7890, 7891, 7892, 7893], validation_alias="UNITY_BRIDGE_PORTS_TO_SCAN"
    )
    unity_bridge_max_retries: int = Field(default=2, validation_alias="UNITY_BRIDGE_MAX_RETRIES")
    unity_bridge_retry_backoff: float = Field(default=0.5, validation_alias="UNITY_BRIDGE_RETRY_BACKOFF")
    unity_bridge_mode: str = Field(default="legacy", validation_alias="UNITY_BRIDGE_MODE")
    unity_bridge_execution_timeout_seconds: float = Field(
        default=60.0, validation_alias="UNITY_BRIDGE_EXECUTION_TIMEOUT_SECONDS"
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    sketchfab_api_token: str = Field(default="", validation_alias="SKETCHFAB_API_TOKEN")
    poly_pizza_api_key: str = Field(default="", validation_alias="POLY_PIZZA_API_KEY")
    default_asset_import_dir: str = Field(default="Assets/VisoraDownloads", validation_alias="DEFAULT_ASSET_IMPORT_DIR")
    asset_download_timeout_seconds: float = Field(default=120.0, validation_alias="ASSET_DOWNLOAD_TIMEOUT_SECONDS")
    max_asset_download_size_bytes: int = Field(default=250_000_000, validation_alias="MAX_ASSET_DOWNLOAD_SIZE_BYTES")
    asset_cache_dir: str = Field(default=".visora_cache", validation_alias="ASSET_CACHE_DIR")
    max_asset_archive_entries: int = Field(default=10_000, validation_alias="MAX_ASSET_ARCHIVE_ENTRIES")
    max_asset_archive_uncompressed_size_bytes: int = Field(
        default=1_000_000_000, validation_alias="MAX_ASSET_ARCHIVE_UNCOMPRESSED_SIZE_BYTES"
    )
    max_asset_archive_entry_size_bytes: int = Field(
        default=250_000_000, validation_alias="MAX_ASSET_ARCHIVE_ENTRY_SIZE_BYTES"
    )
    max_asset_archive_compression_ratio: float = Field(
        default=100.0, validation_alias="MAX_ASSET_ARCHIVE_COMPRESSION_RATIO"
    )
    # Sketchfab's own public search API ignores its query text (verified live), so
    # find_sketchfab_models_via_web_search() uses these keyless SearXNG instances as a real-search
    # fallback, trying each in order before falling back further to scraping DuckDuckGo. Verified
    # live that public instances commonly refuse or rate-limit the JSON API for anonymous callers
    # (SearXNG's own recommended anti-abuse posture) - the DuckDuckGo fallback is what actually
    # carries most real-world queries unless this is pointed at a self-hosted instance.
    searxng_instance_urls: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["https://searx.be", "https://searx.tiekoetter.com", "https://priv.au"],
        validation_alias="SEARXNG_INSTANCE_URLS",
    )
    web_search_timeout_seconds: float = Field(default=10.0, validation_alias="WEB_SEARCH_TIMEOUT_SECONDS")

    @field_validator("unity_bridge_ports_to_scan", mode="before")
    @classmethod
    def parse_ports_to_scan(cls, value: Any) -> list[int]:
        if isinstance(value, str):
            # Extract digit runs rather than splitting on "," alone: with NoDecode active this
            # also receives the raw env/dotenv string for the legacy JSON-array format some
            # existing deployments use (e.g. "[9999, 9998, 9997]"), not just the documented
            # plain comma-separated one - findall handles both without caring about brackets.
            return [int(p) for p in re.findall(r"\d+", value)]
        if isinstance(value, (list, tuple, set)):
            return [int(p) for p in value]
        return [7890, 7891, 7892, 7893]

    @field_validator("searxng_instance_urls", mode="before")
    @classmethod
    def parse_searxng_instance_urls(cls, value: Any) -> list[str]:
        # Same NoDecode rationale as unity_bridge_ports_to_scan above: pydantic-settings otherwise
        # tries to JSON-decode this list-typed env value before we can split it, and the documented
        # plain comma-separated .env format ("https://a,https://b") isn't valid JSON.
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(v).strip() for v in value if str(v).strip()]
        return ["https://searx.be", "https://searx.tiekoetter.com", "https://priv.au"]

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
