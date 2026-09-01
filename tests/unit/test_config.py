import pytest

from backend.config import Settings, get_settings


def test_default_settings() -> None:
    settings = Settings()

    assert settings.unity_bridge_url == "http://127.0.0.1"
    assert settings.unity_bridge_port == 7890
    assert settings.unity_bridge_fallback_port == 7891
    assert settings.unity_bridge_timeout_seconds == 10.0
    assert settings.unity_bridge_ping_timeout_seconds == 2.0
    assert settings.unity_bridge_ports_to_scan == [7890, 7891, 7892, 7893]
    assert settings.unity_bridge_max_retries == 2
    assert settings.unity_bridge_retry_backoff == 0.5
    assert settings.log_level == "INFO"


def test_normalize_bridge_url_trailing_slashes() -> None:
    settings = Settings(unity_bridge_url="http://localhost:7890///")
    assert settings.unity_bridge_url == "http://localhost:7890"

    settings_clean = Settings(unity_bridge_url="http://192.168.1.50:8000")
    assert settings_clean.unity_bridge_url == "http://192.168.1.50:8000"


def test_normalize_log_level_uppercase() -> None:
    settings = Settings(log_level="debug")
    assert settings.log_level == "DEBUG"

    settings_warn = Settings(log_level="warning")
    assert settings_warn.log_level == "WARNING"


def test_parse_ports_to_scan_comma_separated_string() -> None:
    settings = Settings(unity_bridge_ports_to_scan="7890, 7891, 8000, 9000")  # type: ignore[arg-type]
    assert settings.unity_bridge_ports_to_scan == [7890, 7891, 8000, 9000]


def test_parse_ports_to_scan_string_with_invalid_entries() -> None:
    settings = Settings(unity_bridge_ports_to_scan="7890, invalid, 7891, , 8080")  # type: ignore[arg-type]
    assert settings.unity_bridge_ports_to_scan == [7890, 7891, 8080]


def test_parse_ports_to_scan_iterables() -> None:
    # Tuple
    settings_tuple = Settings(unity_bridge_ports_to_scan=(7000, 7001))  # type: ignore[arg-type]
    assert settings_tuple.unity_bridge_ports_to_scan == [7000, 7001]

    # Set
    settings_set = Settings(unity_bridge_ports_to_scan={7002, 7003})  # type: ignore[arg-type]
    assert set(settings_set.unity_bridge_ports_to_scan) == {7002, 7003}


def test_parse_ports_to_scan_fallback_for_other_types() -> None:
    settings = Settings(unity_bridge_ports_to_scan=None)  # type: ignore[arg-type]
    assert settings.unity_bridge_ports_to_scan == [7890, 7891, 7892, 7893]


def test_env_variable_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UNITY_BRIDGE_URL", "http://10.0.0.5/")
    monkeypatch.setenv("UNITY_BRIDGE_PORT", "9999")
    monkeypatch.setenv("UNITY_BRIDGE_FALLBACK_PORT", "9998")
    monkeypatch.setenv("UNITY_BRIDGE_TIMEOUT_SECONDS", "25.5")
    monkeypatch.setenv("UNITY_BRIDGE_PING_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("UNITY_BRIDGE_PORTS_TO_SCAN", "[9999, 9998, 9997]")
    monkeypatch.setenv("UNITY_BRIDGE_MAX_RETRIES", "5")
    monkeypatch.setenv("UNITY_BRIDGE_RETRY_BACKOFF", "1.5")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings()

    assert settings.unity_bridge_url == "http://10.0.0.5"
    assert settings.unity_bridge_port == 9999
    assert settings.unity_bridge_fallback_port == 9998
    assert settings.unity_bridge_timeout_seconds == 25.5
    assert settings.unity_bridge_ping_timeout_seconds == 3.5
    assert settings.unity_bridge_ports_to_scan == [9999, 9998, 9997]
    assert settings.unity_bridge_max_retries == 5
    assert settings.unity_bridge_retry_backoff == 1.5
    assert settings.log_level == "DEBUG"


def test_get_settings_lru_cache() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
