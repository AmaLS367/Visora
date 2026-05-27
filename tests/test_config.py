from backend.config import Settings


def test_default_bridge_url_uses_loopback_ip() -> None:
    settings = Settings()

    assert settings.unity_bridge_url == "http://127.0.0.1"
