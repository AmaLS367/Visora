from typing import Any

import pytest

from backend.schemas import BoneNode, BoneSearchResult, SkeletonMapperResult
from backend.tools import animation
from backend.tools.animation.analysis import (
    detect_duplicate_bones,
    detect_helper_bones,
    detect_mmd_bone_chains,
    map_humanoid_bones,
    match_bones_fuzzy,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeBridge:
    def __init__(self, execute_responses: list[dict[str, Any] | Exception] | None = None) -> None:
        self.execute_responses = list(execute_responses or [])
        self.executed_codes: list[str] = []

    async def execute_code(self, code: str) -> dict[str, Any]:
        self.executed_codes.append(code)
        if self.execute_responses:
            resp = self.execute_responses.pop(0)
            if isinstance(resp, Exception):
                raise resp
            return resp
        return {"success": True, "result": {"success": True}}

    async def execute_capability(self, code: str, **_kwargs: Any) -> dict[str, Any]:
        return await self.execute_code(code)


def _bone(path: str, name: str, parent_path: str | None = None, depth: int = 0) -> BoneNode:
    return BoneNode(path=path, name=name, parent_path=parent_path, depth=depth)


# ---------------------------------------------------------------------------
# Test Analysis Logic: Duplicate/Helper/MMD Detection & Fuzzy Matching
# ---------------------------------------------------------------------------


def test_detect_duplicate_bones() -> None:
    bones = [
        _bone("", "Armature"),
        _bone("Hips", "Hips", "", 1),
        _bone("Hips/LeftUpLeg", "LeftUpLeg", "Hips", 2),
        _bone("Hips/LeftUpLeg/Nub", "Nub", "Hips/LeftUpLeg", 3),
        _bone("Hips/RightUpLeg", "RightUpLeg", "Hips", 2),
        _bone("Hips/RightUpLeg/Nub", "Nub", "Hips/RightUpLeg", 3),
    ]
    duplicates = detect_duplicate_bones(bones)
    assert len(duplicates) == 1
    assert duplicates[0].name == "Nub"
    assert set(duplicates[0].paths) == {"Hips/LeftUpLeg/Nub", "Hips/RightUpLeg/Nub"}


def test_detect_duplicate_bones_none() -> None:
    bones = [_bone("", "Armature"), _bone("Hips", "Hips", "", 1)]
    assert detect_duplicate_bones(bones) == []


def test_detect_helper_bones() -> None:
    bones = [
        _bone("Hips", "Hips", "", 1),
        _bone("Hips/Spine/Dummy", "Dummy", "Hips/Spine", 3),
        _bone("Hips/RightHand/Finger_End", "Finger_End", "Hips/RightHand", 3),
        _bone("Hips/LeftHand/IK_Hand_L", "IK_Hand_L", "Hips/LeftHand", 3),
    ]
    warnings = detect_helper_bones(bones)
    flagged_names = {w.name for w in warnings}
    assert flagged_names == {"Dummy", "Finger_End", "IK_Hand_L"}
    assert "Hips" not in flagged_names


def test_detect_mmd_bone_chains() -> None:
    bones = [
        _bone("Hips", "Hips", "", 1),
        _bone("Hips/Spine", "Spine", "Hips", 2),
        _bone("Hips/Spine/Spine_D", "Spine_D", "Hips/Spine", 3),
        _bone("Hips/Neck", "Neck", "Hips", 2),  # no matching "Neck_D" counterpart
    ]
    chains = detect_mmd_bone_chains(bones)
    assert len(chains) == 1
    assert chains[0].base_name == "Spine"
    assert chains[0].primary_path == "Hips/Spine"
    assert chains[0].d_bone_path == "Hips/Spine/Spine_D"


def test_match_bones_fuzzy_exact_and_fuzzy() -> None:
    bones = [
        _bone("Hips", "Hips", "", 1),
        _bone("Hips/Spine", "Spine", "Hips", 2),
    ]
    exact = match_bones_fuzzy("hips", bones)
    assert exact[0].match_type == "exact"
    assert exact[0].name == "Hips"
    assert exact[0].score == 1.0

    fuzzy = match_bones_fuzzy("Hipz", bones)
    assert fuzzy[0].match_type == "fuzzy"
    assert fuzzy[0].name == "Hips"
    assert 0.0 < fuzzy[0].score < 1.0


def test_match_bones_fuzzy_no_match() -> None:
    bones = [_bone("Hips", "Hips", "", 1)]
    matches = match_bones_fuzzy("999", bones)
    assert matches == []


def test_match_bones_fuzzy_exact_only_skips_fuzzy() -> None:
    bones = [_bone("Hips", "Hips", "", 1)]
    matches = match_bones_fuzzy("Hipz", bones, exact_only=True)
    assert matches == []


def test_map_humanoid_bones_avatar_source() -> None:
    bones = [
        _bone("Hips", "Hips", "", 1),
        _bone("Hips/Spine", "Spine", "Hips", 2),
    ]
    is_valid, source, mappings, missing = map_humanoid_bones(
        bones=bones,
        required_names=["Hips", "Spine", "Head"],
        avatar_human_bones=[("Hips", "Hips"), ("Spine", "Spine")],
    )
    assert source == "avatar"
    assert is_valid is False
    assert mappings == {"Hips": "Hips", "Spine": "Hips/Spine"}
    assert missing == ["Head"]


def test_map_humanoid_bones_heuristic_fallback() -> None:
    bones = [
        _bone("Hips", "Hips", "", 1),
        _bone("Hips/Spine", "Spine", "Hips", 2),
    ]
    is_valid, source, mappings, missing = map_humanoid_bones(
        bones=bones,
        required_names=["Hips", "Spine"],
        avatar_human_bones=None,
    )
    assert source == "heuristic"
    assert is_valid is True
    assert mappings == {"Hips": "Hips", "Spine": "Hips/Spine"}
    assert missing == []


# ---------------------------------------------------------------------------
# Test skeleton_mapper tool
# ---------------------------------------------------------------------------


_BASE_BONES = [
    {
        "path": "",
        "name": "Armature",
        "parentPath": None,
        "depth": 0,
        "childCount": 1,
        "localPosition": [0.0, 0.0, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips",
        "name": "Hips",
        "parentPath": "",
        "depth": 1,
        "childCount": 2,
        "localPosition": [0.0, 1.0, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/Spine",
        "name": "Spine",
        "parentPath": "Hips",
        "depth": 2,
        "childCount": 1,
        "localPosition": [0.0, 0.2, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/Spine/Spine_D",
        "name": "Spine_D",
        "parentPath": "Hips/Spine",
        "depth": 3,
        "childCount": 0,
        "localPosition": [0.0, 0.0, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/LeftUpLeg",
        "name": "LeftUpLeg",
        "parentPath": "Hips",
        "depth": 2,
        "childCount": 1,
        "localPosition": [-0.1, -0.1, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/LeftUpLeg/Nub",
        "name": "Nub",
        "parentPath": "Hips/LeftUpLeg",
        "depth": 3,
        "childCount": 0,
        "localPosition": [0.0, -0.5, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/RightUpLeg",
        "name": "RightUpLeg",
        "parentPath": "Hips",
        "depth": 2,
        "childCount": 1,
        "localPosition": [0.1, -0.1, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/RightUpLeg/Nub",
        "name": "Nub",
        "parentPath": "Hips/RightUpLeg",
        "depth": 3,
        "childCount": 0,
        "localPosition": [0.0, -0.5, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
    {
        "path": "Hips/Spine/Dummy",
        "name": "Dummy",
        "parentPath": "Hips/Spine",
        "depth": 3,
        "childCount": 0,
        "localPosition": [0.0, 0.0, 0.0],
        "localRotationEuler": [0.0, 0.0, 0.0],
        "localScale": [1.0, 1.0, 1.0],
    },
]


@pytest.mark.anyio
async def test_skeleton_mapper_with_avatar(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "rootPath": "Root/Armature",
            "bones": _BASE_BONES,
            "hasAvatar": True,
            "isHumanoidAvatar": True,
            "avatarHumanBones": [
                {"humanName": "Hips", "boneName": "Hips"},
                {"humanName": "Spine", "boneName": "Spine"},
            ],
            "requiredHumanBoneNames": ["Hips", "Spine", "Head"],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.skeleton_mapper("Root/Armature")

    assert isinstance(result, SkeletonMapperResult)
    assert result.success is True
    assert result.bone_count == len(_BASE_BONES)
    assert result.mapping_source == "avatar"
    assert result.mappings == {"Hips": "Hips", "Spine": "Hips/Spine"}
    assert result.missing_bones == ["Head"]
    assert result.is_valid is False
    assert result.warnings == []

    assert len(result.duplicate_bones) == 1
    assert result.duplicate_bones[0].name == "Nub"

    assert len(result.helper_bones) == 1
    assert result.helper_bones[0].name == "Dummy"

    assert len(result.mmd_bone_chains) == 1
    assert result.mmd_bone_chains[0].base_name == "Spine"
    assert result.mmd_bone_chains[0].d_bone_path == "Hips/Spine/Spine_D"


@pytest.mark.anyio
async def test_skeleton_mapper_heuristic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "rootPath": "Root/Armature",
            "bones": _BASE_BONES,
            "hasAvatar": False,
            "isHumanoidAvatar": False,
            "avatarHumanBones": [],
            "requiredHumanBoneNames": ["Hips", "Spine"],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.skeleton_mapper("Root/Armature")

    assert result.success is True
    assert result.mapping_source == "heuristic"
    assert result.is_valid is True
    assert result.mappings == {"Hips": "Hips", "Spine": "Hips/Spine"}
    assert result.missing_bones == []
    assert any("heuristic" in w.lower() for w in result.warnings)


@pytest.mark.anyio
async def test_skeleton_mapper_root_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": False,
            "error": "Root GameObject not found at hierarchy path: Root/Missing",
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.skeleton_mapper("Root/Missing")

    assert result.success is False
    assert "not found" in (result.error or "")


@pytest.mark.anyio
async def test_skeleton_mapper_bridge_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(execute_responses=[ConnectionError("Bridge disconnected")])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.skeleton_mapper("Root/Armature")

    assert result.success is False
    assert "Bridge disconnected" in (result.error or "")


# ---------------------------------------------------------------------------
# Test find_bones tool
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_find_bones_exact_match(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "rootPath": "Root/Armature",
            "bones": _BASE_BONES,
            "hasAvatar": False,
            "isHumanoidAvatar": False,
            "avatarHumanBones": [],
            "requiredHumanBoneNames": [],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.find_bones("Root/Armature", "hips")

    assert isinstance(result, BoneSearchResult)
    assert result.success is True
    assert result.matches[0].match_type == "exact"
    assert result.matches[0].name == "Hips"


@pytest.mark.anyio
async def test_find_bones_fuzzy_match(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "rootPath": "Root/Armature",
            "bones": _BASE_BONES,
            "hasAvatar": False,
            "isHumanoidAvatar": False,
            "avatarHumanBones": [],
            "requiredHumanBoneNames": [],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.find_bones("Root/Armature", "Spyne", max_results=3)

    assert result.success is True
    assert len(result.matches) > 0
    assert result.matches[0].match_type == "fuzzy"
    assert result.matches[0].name == "Spine"


@pytest.mark.anyio
async def test_find_bones_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "rootPath": "Root/Armature",
            "bones": _BASE_BONES,
            "hasAvatar": False,
            "isHumanoidAvatar": False,
            "avatarHumanBones": [],
            "requiredHumanBoneNames": [],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.find_bones("Root/Armature", "999", exact_only=True)

    assert result.success is True
    assert result.matches == []


@pytest.mark.anyio
async def test_find_bones_bridge_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(execute_responses=[ConnectionError("Bridge disconnected")])
    monkeypatch.setattr(animation, "bridge", fake_bridge)

    result = await animation.find_bones("Root/Armature", "Hips")

    assert result.success is False
    assert "Bridge disconnected" in (result.error or "")
