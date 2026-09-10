import pytest

import backend.tools.animation as animation_pkg
from backend.tools.animation.authoring import list_animation_keyframes


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeBridge:
    def __init__(self, *, supported: bool = True) -> None:
        self.calls: list[str] = []
        self._supported = supported

    async def supports_feature(self, feature: str) -> bool:
        return self._supported and feature == "animation_authoring"

    async def list_keyframes_native(
        self, clip_path: str, target_path: str, type_name: str, property_name: str
    ) -> dict[str, object]:
        self.calls.append("list_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "targetPath": target_path,
            "typeName": type_name,
            "propertyName": property_name,
            "channels": ["m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z"],
            "keyframes": [
                {
                    "time": 0.5,
                    "values": [1.0, 2.0, 3.0],
                    "exact": [True, True, True],
                    "inTangents": [0.0, 0.0, 0.0],
                    "outTangents": [0.0, 0.0, 0.0],
                    "tangentMode": "smooth",
                }
            ],
        }


@pytest.mark.anyio
async def test_list_animation_keyframes_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    list_res = await list_animation_keyframes(
        clip_path="Assets/A.anim", target_path="Rebecca", type_name="Transform", property_name="m_LocalPosition"
    )
    assert list_res.success is True
    assert list_res.clip_path == "Assets/A.anim"
    assert list_res.target_path == "Rebecca"
    assert list_res.channels == ["m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z"]
    assert len(list_res.keyframes) == 1
    assert list_res.keyframes[0].time == 0.5
    assert list_res.keyframes[0].values == [1.0, 2.0, 3.0]
    assert list_res.keyframes[0].tangent_mode == "smooth"
    assert fake.calls == ["list_native"]


@pytest.mark.anyio
async def test_list_animation_keyframes_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge(supported=False)
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    list_res = await list_animation_keyframes(
        clip_path="Assets/A.anim", target_path="Rebecca", type_name="Transform", property_name="m_LocalPosition"
    )
    assert list_res.success is False
    assert "animation_authoring requires the Visora Unity package" in (list_res.error or "")


@pytest.mark.anyio
async def test_list_animation_keyframes_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()

    async def _failing_list(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("Bridge connection failed")

    fake.list_keyframes_native = _failing_list  # type: ignore[method-assign]
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    list_res = await list_animation_keyframes(
        clip_path="Assets/A.anim", target_path="Rebecca", type_name="Transform", property_name="m_LocalPosition"
    )
    assert list_res.success is False
    assert "Bridge connection failed" in (list_res.error or "")
