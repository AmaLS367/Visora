from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

import backend.tools.animation as animation_pkg
from backend.schemas.intersections import (
    BodyPenetrationEvent,
    SelfIntersectionResult,
)
from backend.tools.animation.intersections import analyze_self_intersections


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeIntersectionBridge:
    def __init__(
        self,
        *,
        supported_features: set[str] | None = None,
        response: dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._supported_features = (
            supported_features if supported_features is not None else {"self_intersection_analysis"}
        )
        self._raises = raises
        self.response = response or {
            "success": True,
            "targetObjectPath": "Characters/Hero",
            "clipPath": "Assets/Animations/Sprint.anim",
            "intersectionsFound": 1,
            "sampleCount": 30,
            "cleanIntervalPercent": 96.7,
            "maxPenetrationDepth": 0.042,
            "penetrations": [
                {
                    "time": 0.33,
                    "limbA": "LeftThigh",
                    "limbB": "RightThigh",
                    "penetrationDepthMeters": 0.042,
                    "severity": "warning",
                    "description": "LeftThigh penetrates RightThigh by 4.2cm at t=0.33s",
                }
            ],
            "warnings": [],
        }

    async def get_editor_state(self) -> dict[str, Any]:
        return {"isPlaying": False}

    async def supports_feature(self, feature: str) -> bool:
        return feature in self._supported_features

    async def analyze_self_intersections_native(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self._raises is not None:
            raise self._raises
        return self.response


def test_intersections_schemas() -> None:
    event = BodyPenetrationEvent(
        time=0.45,
        limb_a="LeftForearm",
        limb_b="Torso",
        penetration_depth_meters=0.035,
        severity="warning",
        description="LeftForearm penetrates Torso by 3.5cm",
    )
    assert event.time == 0.45

    # Missing required fields must fail.
    with pytest.raises(ValidationError):
        BodyPenetrationEvent(time=0.1)  # type: ignore[call-arg]

    # Severity outside the vocabulary is rejected by the schema (the tool coerces before this).
    with pytest.raises(ValidationError):
        BodyPenetrationEvent(
            time=0.1,
            limb_a="a",
            limb_b="b",
            penetration_depth_meters=0.01,
            severity="fatal",  # type: ignore[arg-type]
            description="x",
        )

    res = SelfIntersectionResult(
        success=True,
        target_object_path="Characters/Hero",
        clip_path="Assets/Animations/Sprint.anim",
        intersections_found=1,
        sample_count=60,
        clean_interval_percent=98.3,
        max_penetration_depth=0.035,
        penetrations=[event],
    )
    assert res.intersections_found == 1


@pytest.mark.anyio
async def test_analyze_self_intersections_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIntersectionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_self_intersections(
        target_object_path="Characters/Hero",
        clip_path="Assets/Animations/Sprint.anim",
    )

    assert result.success is True
    assert result.intersections_found == 1
    assert result.penetrations[0].limb_a == "LeftThigh"
    assert result.clean_interval_percent == 96.7


@pytest.mark.anyio
async def test_analyze_self_intersections_coerces_unknown_severity(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIntersectionBridge(
        response={
            "success": True,
            "targetObjectPath": "Characters/Hero",
            "clipPath": "Assets/A.anim",
            "penetrations": [
                {
                    "time": 0.1,
                    "limbA": "a",
                    "limbB": "b",
                    "penetrationDepthMeters": 0.01,
                    "severity": "catastrophic",
                    "description": "x",
                }
            ],
            "warnings": [],
        }
    )
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_self_intersections(target_object_path="Characters/Hero", clip_path="Assets/A.anim")
    assert result.success is True
    assert result.penetrations[0].severity == "unknown"
    assert any("catastrophic" in w for w in result.warnings)


@pytest.mark.anyio
async def test_analyze_self_intersections_fails_when_capability_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIntersectionBridge(supported_features=set())
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_self_intersections(target_object_path="Characters/Hero", clip_path="Assets/A.anim")
    assert result.success is False
    assert "self_intersection_analysis" in (result.error or "")


@pytest.mark.anyio
async def test_analyze_self_intersections_surfaces_bridge_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIntersectionBridge(raises=RuntimeError("bridge unreachable"))
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_self_intersections(target_object_path="Characters/Hero", clip_path="Assets/A.anim")
    assert result.success is False
    assert "Bridge call failed" in (result.error or "")


@pytest.mark.anyio
async def test_analyze_self_intersections_validates_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _FakeIntersectionBridge()
    monkeypatch.setattr(animation_pkg, "bridge", bridge)

    result = await analyze_self_intersections(
        target_object_path="Characters/Hero", clip_path="Assets/A.anim", sample_fps=0
    )
    assert result.success is False
    assert "sample_fps" in (result.error or "")
    assert bridge.calls == []
