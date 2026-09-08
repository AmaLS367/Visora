from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from backend.schemas.intersections import (
    BodyPenetrationEvent,
    SelfIntersectionResult,
)
from backend.tools.animation.intersections import analyze_self_intersections


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
    assert event.penetration_depth_meters == 0.035

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
    assert res.success is True
    assert res.intersections_found == 1
    assert res.clean_interval_percent == 98.3


@pytest.mark.anyio
async def test_analyze_self_intersections_tool() -> None:
    mock_response: dict[str, Any] = {
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

    with patch(
        "backend.bridge.client.UnityBridge.analyze_self_intersections_native",
        new=AsyncMock(return_value=mock_response),
    ):
        result = await analyze_self_intersections(
            target_object_path="Characters/Hero",
            clip_path="Assets/Animations/Sprint.anim",
            sample_fps=30,
            tolerance_meters=0.02,
        )

    assert result.success is True
    assert result.intersections_found == 1
    assert len(result.penetrations) == 1
    assert result.penetrations[0].limb_a == "LeftThigh"
    assert result.clean_interval_percent == 96.7
