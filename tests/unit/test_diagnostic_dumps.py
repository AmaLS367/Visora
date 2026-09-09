from typing import Any

import pytest

from backend.tools import animation, asset, mesh


class FakeBridge:
    def __init__(self, execute_responses: list[dict[str, Any]]) -> None:
        self._responses = list(execute_responses)

    async def execute_capability(self, _code: str, **_kwargs: Any) -> dict[str, Any]:
        if not self._responses:
            return {"success": True, "result": {}}
        return self._responses.pop(0)


@pytest.mark.anyio
async def test_inspect_animation_clip_truncation_and_filtering(monkeypatch: pytest.MonkeyPatch) -> None:
    # 60 bindings: 30 on Hips, 30 on Spine
    raw_bindings = []
    for i in range(30):
        raw_bindings.append(
            {
                "path": "Hips",
                "propertyName": f"m_LocalPosition.x_{i}",
                "typeName": "UnityEngine.Transform",
                "curveType": "position",
                "keyframeCount": 2,
            }
        )
    for i in range(30):
        raw_bindings.append(
            {
                "path": "Spine",
                "propertyName": f"m_LocalRotation.x_{i}",
                "typeName": "UnityEngine.Transform",
                "curveType": "rotation",
                "keyframeCount": 2,
            }
        )

    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "BigClip",
            "clipPath": "Assets/BigClip.anim",
            "length": 2.0,
            "fps": 30.0,
            "bindings": raw_bindings,
            "events": [],
        },
    }

    monkeypatch.setattr(animation, "bridge", FakeBridge([unity_response]))

    # Default max_bindings=25
    res = await animation.inspect_animation_clip("Assets/BigClip.anim")
    assert res.success is True
    assert res.curves_count == 60
    assert len(res.bindings) == 25
    assert "truncation_note" in res.summary_metrics
    assert "Showing 25 of 60 bindings" in res.summary_metrics["truncation_note"]

    # Filter by path "Spine"
    monkeypatch.setattr(animation, "bridge", FakeBridge([unity_response]))
    res_filtered = await animation.inspect_animation_clip("Assets/BigClip.anim", path_filter="Spine", max_bindings=50)
    assert res_filtered.curves_count == 60
    assert len(res_filtered.bindings) == 30
    assert all(b.path == "Spine" for b in res_filtered.bindings)


@pytest.mark.anyio
async def test_sample_animation_clip_truncation_and_priority(monkeypatch: pytest.MonkeyPatch) -> None:
    # 50 transforms, one with an extreme scale anomaly
    sampled_transforms: dict[str, Any] = {}
    for i in range(50):
        name = f"Bone_{i:02d}"
        path = f"Root/{name}"
        scale = [1.0, 1.0, 1.0]
        if i == 45:
            # Anomalous bone
            scale = [-1.0, 1.0, 1.0]
        sampled_transforms[path] = {
            "path": path,
            "name": name,
            "localPosition": [0.0, float(i), 0.0],
            "localRotationEuler": [0.0, 0.0, 0.0],
            "localScale": scale,
        }

    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "clipName": "TestSample",
            "sampledTransforms": sampled_transforms,
            "poseRestored": True,
        },
    }

    monkeypatch.setattr(animation, "bridge", FakeBridge([unity_response]))

    # Default max_transforms is 25
    res = await animation.sample_animation_clip("Player", "Assets/Test.anim")
    assert res.success is True
    assert len(res.sampled_transforms) == 25
    assert any("Showing 25 of 50 transforms" in w for w in res.warnings)
    # The anomalous bone (Bone_45) must be prioritized and included
    assert "Root/Bone_45" in res.sampled_transforms
    assert len(res.anomalies_detected) > 0


@pytest.mark.anyio
async def test_skeleton_mapper_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    # 60 bones
    bones = []
    for i in range(60):
        bones.append(
            {
                "path": f"Bone_{i}",
                "name": f"Bone_{i}",
                "parentPath": None if i == 0 else f"Bone_{i - 1}",
                "depth": i,
                "childCount": 1 if i < 59 else 0,
                "localPosition": [0.0, 0.0, 0.0],
                "localRotationEuler": [0.0, 0.0, 0.0],
                "localScale": [1.0, 1.0, 1.0],
            }
        )

    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "bones": bones,
            "isHumanoidAvatar": False,
        },
    }

    monkeypatch.setattr(animation, "bridge", FakeBridge([unity_response]))

    # Default max_bones is 30
    res = await animation.skeleton_mapper("Root")
    assert res.success is True
    assert res.bone_count == 60
    assert len(res.bones) == 30
    assert any("Showing 30 of 60 bones" in w for w in res.warnings)


@pytest.mark.anyio
async def test_skinned_mesh_diagnostics_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    # 50 bone slots, 2 null/broken
    bones = []
    for i in range(50):
        is_null = i in (10, 20)
        bones.append(
            {
                "index": i,
                "name": None if is_null else f"Bone_{i}",
                "path": None if is_null else f"Armature/Bone_{i}",
                "isNull": is_null,
            }
        )

    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "hasSharedMesh": True,
            "meshName": "HeroMesh",
            "vertexCount": 1000,
            "subMeshCount": 1,
            "bindPosesCount": 50,
            "hasRootBone": True,
            "rootBonePath": "Armature",
            "bones": bones,
            "materials": [{"index": 0, "name": "Mat", "shaderName": "Standard", "isMissing": False, "isPink": False}],
            "submeshes": [{"index": 0, "topology": "Triangles", "vertexCount": 1000}],
            "blendshapes": [],
            "localCenter": [0.0, 1.0, 0.0],
            "localSize": [1.0, 2.0, 1.0],
            "worldCenter": [0.0, 1.0, 0.0],
            "worldSize": [1.0, 2.0, 1.0],
        },
    }

    monkeypatch.setattr(mesh, "bridge", FakeBridge([unity_response]))

    # Default max_bone_bindings is 30
    res = await mesh.skinned_mesh_diagnostics("Hero")
    assert res.success is True
    assert res.bone_count == 50
    assert len(res.bone_bindings) == 30
    assert res.has_broken_bones is True
    # The 2 null bones must be prioritized in bone_bindings
    null_bindings = [b for b in res.bone_bindings if b.is_null]
    assert len(null_bindings) == 2
    assert any("Showing 30 of 50 bone bindings" in w for w in res.warnings)


@pytest.mark.anyio
async def test_inspect_imported_asset_truncation(monkeypatch: pytest.MonkeyPatch) -> None:
    # 80 hierarchy nodes
    nodes = [f"Node_{i}" for i in range(80)]
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "asset_path": "Assets/Model.glb",
            "asset_type": "Model",
            "hierarchy_tree": nodes,
            "warnings": [],
        },
    }

    monkeypatch.setattr(asset.operations, "bridge", FakeBridge([unity_response]))

    # Default max_hierarchy_nodes is 50
    res = await asset.inspect_imported_asset("Assets/Model.glb")
    assert res.success is True
    assert len(res.hierarchy_tree) == 50
    assert any("Showing 50 of 80 nodes in hierarchy_tree" in w for w in res.warnings)
