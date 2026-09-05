import pytest

import backend.tools.animation as animation_pkg
from backend.tools.animation.authoring import (
    create_animation_event,
    list_animation_keyframes,
    move_animation_keyframe,
    remove_animation_event,
    remove_animation_keyframe,
    set_animation_keyframe,
    set_keyframe_hold,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeBridge:
    def __init__(self, *, is_playing: bool = False) -> None:
        self.calls: list[str] = []
        self._is_playing = is_playing

    async def supports_feature(self, feature: str) -> bool:
        return feature == "animation_authoring"

    async def get_editor_state(self) -> dict[str, object]:
        return {"isPlaying": self._is_playing}

    async def set_keyframe_native(self, **kwargs: object) -> dict[str, object]:
        self.calls.append("native")
        return {
            "success": True,
            "clipPath": kwargs["clip_path"],
            "targetPath": kwargs["target_path"],
            "typeName": kwargs["type_name"],
            "propertyName": kwargs["property_name"],
            "channelsAffected": ["m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z"],
            "curveCreated": True,
            "time": kwargs["time"],
            "hasTime": True,
            "backupId": "Assets__A.anim/x.anim",
            "undoGroupId": 3,
            "warnings": [],
        }

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

    async def move_keyframe_native(  # noqa: PLR0913
        self, clip_path: str, target_path: str, type_name: str, property_name: str, from_time: float, to_time: float
    ) -> dict[str, object]:
        self.calls.append("move_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "targetPath": target_path,
            "typeName": type_name,
            "propertyName": property_name,
            "channelsAffected": ["m_LocalPosition.x"],
            "curveCreated": False,
            "time": to_time,
            "hasTime": True,
            "previousTime": from_time,
            "hasPreviousTime": True,
            "keysCleared": [],
            "backupId": "b1",
            "undoGroupId": 1,
            "warnings": [],
        }

    async def remove_keyframe_native(
        self, clip_path: str, target_path: str, type_name: str, property_name: str, time: float
    ) -> dict[str, object]:
        self.calls.append("remove_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "targetPath": target_path,
            "typeName": type_name,
            "propertyName": property_name,
            "channelsAffected": ["m_LocalPosition.x"],
            "curveCreated": False,
            "time": time,
            "hasTime": True,
            "keysCleared": [time],
            "backupId": "b2",
            "undoGroupId": 2,
            "warnings": [],
        }

    async def hold_keyframe_native(
        self,
        clip_path: str,
        target_path: str,
        type_name: str,
        property_name: str,
        time: float,
        _hold_until: float,
        _value: list[float] | None,
    ) -> dict[str, object]:
        self.calls.append("hold_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "targetPath": target_path,
            "typeName": type_name,
            "propertyName": property_name,
            "channelsAffected": ["m_LocalPosition.x"],
            "curveCreated": False,
            "time": time,
            "hasTime": True,
            "keysCleared": [],
            "backupId": "b3",
            "undoGroupId": 3,
            "warnings": [],
        }

    async def create_event_native(
        self,
        clip_path: str,
        time: float,
        function_name: str,
        _string_param: str,
        _float_param: float,
        _int_param: int,
    ) -> dict[str, object]:
        self.calls.append("create_event_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "time": time,
            "hasTime": True,
            "functionName": function_name,
            "eventsAffected": 1,
            "backupId": "b4",
            "undoGroupId": 4,
            "warnings": [],
        }

    async def remove_event_native(self, clip_path: str, time: float, function_name: str | None) -> dict[str, object]:
        self.calls.append("remove_event_native")
        return {
            "success": True,
            "clipPath": clip_path,
            "time": time,
            "hasTime": True,
            "functionName": function_name,
            "eventsAffected": 1,
            "backupId": "b5",
            "undoGroupId": 5,
            "warnings": [],
        }


@pytest.mark.anyio
async def test_set_animation_keyframe_uses_native_path_when_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await set_animation_keyframe(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        value=[1.0, 2.0, 3.0],
    )

    assert fake.calls == ["native"]
    assert result.success is True
    assert result.curve_created is True
    assert result.channels_affected == ["m_LocalPosition.x", "m_LocalPosition.y", "m_LocalPosition.z"]


@pytest.mark.anyio
async def test_set_animation_keyframe_normalizes_scalar_value(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    sent: dict[str, object] = {}

    async def capturing_set_keyframe_native(**kwargs: object) -> dict[str, object]:
        sent.update(kwargs)
        return await _FakeBridge.set_keyframe_native(fake, **kwargs)

    fake.set_keyframe_native = capturing_set_keyframe_native  # type: ignore[method-assign]
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    await set_animation_keyframe(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Light",
        property_name="m_Intensity",
        time=0.5,
        value=2.5,
    )

    assert sent["values"] == [2.5]


@pytest.mark.anyio
async def test_set_animation_keyframe_refuses_play_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge(is_playing=True)
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await set_animation_keyframe(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        value=[1.0, 2.0, 3.0],
    )

    assert result.success is False
    assert result.error is not None
    assert "Edit Mode" in result.error
    assert fake.calls == []  # refused before any bridge write call was attempted


@pytest.mark.anyio
async def test_set_animation_keyframe_unwraps_a_legacy_business_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class _LegacyFailureBridge(_FakeBridge):
        async def supports_feature(self, _feature: str) -> bool:
            return False  # forces legacy path

        async def execute_code(self, _code: str) -> dict[str, object]:
            self.calls.append("legacy")
            return {
                "success": True,  # snippet executed cleanly
                "logs": [],
                "result": {
                    "success": False,
                    "clipPath": "Assets/A.anim",
                    "error": "AnimationClip not found at exact path 'Assets/A.anim'.",
                },
            }

    fake = _LegacyFailureBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    result = await set_animation_keyframe(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=0.5,
        value=[1.0, 2.0, 3.0],
    )

    assert fake.calls == ["legacy"]
    assert result.success is False
    assert result.error == "AnimationClip not found at exact path 'Assets/A.anim'."


@pytest.mark.anyio
async def test_list_move_remove_hold_and_events(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBridge()
    monkeypatch.setattr(animation_pkg, "bridge", fake)

    # list
    list_res = await list_animation_keyframes(
        clip_path="Assets/A.anim", target_path="Rebecca", type_name="Transform", property_name="m_LocalPosition"
    )
    assert list_res.success is True
    assert len(list_res.keyframes) == 1
    assert list_res.keyframes[0].time == 0.5

    # move
    move_res = await move_animation_keyframe(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        from_time=0.5,
        to_time=1.0,
    )
    assert move_res.success is True
    assert move_res.time == 1.0
    assert move_res.previous_time == 0.5

    # remove
    rem_res = await remove_animation_keyframe(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=1.0,
    )
    assert rem_res.success is True
    assert rem_res.keys_cleared == [1.0]

    # hold
    hold_res = await set_keyframe_hold(
        clip_path="Assets/A.anim",
        target_path="Rebecca",
        type_name="Transform",
        property_name="m_LocalPosition",
        time=1.0,
        hold_until=2.0,
    )
    assert hold_res.success is True

    # create event
    ev_create = await create_animation_event(
        clip_path="Assets/A.anim",
        time=0.5,
        function_name="OnFootstep",
        string_param="dirt",
        float_param=1.0,
        int_param=2,
    )
    assert ev_create.success is True
    assert ev_create.events_affected == 1

    # remove event
    ev_remove = await remove_animation_event(
        clip_path="Assets/A.anim",
        time=0.5,
        function_name="OnFootstep",
    )
    assert ev_remove.success is True
    assert ev_remove.events_affected == 1
