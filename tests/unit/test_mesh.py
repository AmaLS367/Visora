from typing import Any

import pytest

from backend.schemas.mesh import (
    BoneBindingInfo,
    BoundsInfo,
    DeformationInfo,
    DiagnosticIssue,
    MaterialSlotInfo,
    SkinnedMeshDiagnosticsResult,
    SubMeshInfo,
)
from backend.tools import mesh
from backend.tools.mesh.analysis import (
    analyze_bones,
    analyze_bounds,
    analyze_deformation,
    analyze_materials_and_submeshes,
    classify_diagnostics,
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


# ---------------------------------------------------------------------------
# Test Pure Analysis Logic: Bounds
# ---------------------------------------------------------------------------


def test_analyze_bounds_healthy() -> None:
    bounds, issues = analyze_bounds(
        local_center=[0.0, 1.0, 0.0],
        local_size=[0.5, 1.8, 0.3],
        world_center=[0.0, 1.0, 0.0],
        world_size=[0.5, 1.8, 0.3],
        update_when_offscreen=True,
    )
    assert isinstance(bounds, BoundsInfo)
    assert bounds.is_zero_volume is False
    assert bounds.is_abnormal is False
    assert bounds.update_when_offscreen is True
    assert len(issues) == 0


def test_analyze_bounds_zero_volume() -> None:
    bounds, issues = analyze_bounds(
        local_center=[0.0, 0.0, 0.0],
        local_size=[0.0, 1.0, 1.0],
        world_center=[0.0, 0.0, 0.0],
        world_size=[0.0, 1.0, 1.0],
    )
    assert bounds.is_zero_volume is True
    assert any("zero" in i.message.lower() for i in issues)


def test_analyze_bounds_nan_inf() -> None:
    bounds, issues = analyze_bounds(
        local_center=[float("nan"), 0.0, 0.0],
        local_size=[1.0, 1.0, 1.0],
        world_center=[0.0, 0.0, 0.0],
        world_size=[1.0, float("inf"), 1.0],
    )
    assert bounds.is_abnormal is True
    assert any("nan or infinity" in i.message.lower() for i in issues)


def test_analyze_bounds_giant() -> None:
    bounds, issues = analyze_bounds(
        local_center=[0.0, 0.0, 0.0],
        local_size=[5000.0, 100.0, 100.0],
        world_center=[0.0, 0.0, 0.0],
        world_size=[5000.0, 100.0, 100.0],
    )
    assert bounds.is_abnormal is True
    assert any("unusually large" in i.message.lower() for i in issues)


# ---------------------------------------------------------------------------
# Test Pure Analysis Logic: Bones
# ---------------------------------------------------------------------------


def test_analyze_bones_healthy() -> None:
    bones_data: list[dict[str, Any]] = [
        {"index": 0, "isNull": False, "name": "Hips", "path": "Hips"},
        {"index": 1, "isNull": False, "name": "Spine", "path": "Hips/Spine"},
    ]
    bindings, issues = analyze_bones(
        bones_data=bones_data,
        has_root_bone=True,
        root_bone_path="Hips",
        bind_poses_count=2,
        vertex_count=500,
    )
    assert len(bindings) == 2
    assert all(isinstance(b, BoneBindingInfo) for b in bindings)
    assert all(not b.is_null for b in bindings)
    assert len(issues) == 0


def test_analyze_bones_null_and_missing_root() -> None:
    bones_data: list[dict[str, Any]] = [
        {"index": 0, "isNull": False, "name": "Hips", "path": "Hips"},
        {"index": 1, "isNull": True, "name": None, "path": None},
    ]
    bindings, issues = analyze_bones(
        bones_data=bones_data,
        has_root_bone=False,
        root_bone_path=None,
        bind_poses_count=3,
        vertex_count=500,
    )
    assert bindings[1].is_null is True
    assert any("unassigned (null) bone" in i.message.lower() for i in issues)
    assert any("rootbone" in i.message.lower() for i in issues)
    assert any("mismatch between bones array count" in i.message.lower() for i in issues)


# ---------------------------------------------------------------------------
# Test Pure Analysis Logic: Materials and Submeshes
# ---------------------------------------------------------------------------


def test_analyze_materials_healthy() -> None:
    materials_data: list[dict[str, Any]] = [
        {
            "index": 0,
            "isMissing": False,
            "name": "BodyMat",
            "shaderName": "Universal Render Pipeline/Lit",
            "isSupported": True,
            "isErrorShader": False,
            "mainTextureName": "body_diffuse",
            "hasMainTexture": True,
        }
    ]
    submeshes_data: list[dict[str, Any]] = [{"index": 0, "indexCount": 300, "topology": "Triangles"}]

    mats, submeshes, issues = analyze_materials_and_submeshes(materials_data, submeshes_data)
    assert len(mats) == 1
    assert isinstance(mats[0], MaterialSlotInfo)
    assert mats[0].is_missing is False
    assert mats[0].is_error_shader is False
    assert len(submeshes) == 1
    assert isinstance(submeshes[0], SubMeshInfo)
    assert submeshes[0].has_matching_material is True
    assert len(issues) == 0


def test_analyze_materials_pink_shader_and_mismatch() -> None:
    materials_data: list[dict[str, Any]] = [
        {
            "index": 0,
            "isMissing": False,
            "name": "ErrorMat",
            "shaderName": "Hidden/InternalErrorShader",
            "isSupported": False,
            "isErrorShader": True,
            "mainTextureName": None,
            "hasMainTexture": False,
        }
    ]
    submeshes_data: list[dict[str, Any]] = [
        {"index": 0, "indexCount": 300, "topology": "Triangles"},
        {"index": 1, "indexCount": 150, "topology": "Triangles"},
    ]

    mats, submeshes, issues = analyze_materials_and_submeshes(materials_data, submeshes_data)
    assert mats[0].is_error_shader is True
    assert submeshes[1].has_matching_material is False
    assert any("pink/magenta" in i.message.lower() for i in issues)
    assert any("has no corresponding material slot" in i.message.lower() for i in issues)


def test_analyze_materials_missing_material_slot() -> None:
    materials_data: list[dict[str, Any]] = [
        {
            "index": 0,
            "isMissing": True,
            "name": None,
            "shaderName": None,
            "isSupported": False,
            "isErrorShader": False,
        }
    ]
    submeshes_data: list[dict[str, Any]] = [{"index": 0, "indexCount": 300, "topology": "Triangles"}]

    mats, _submeshes, issues = analyze_materials_and_submeshes(materials_data, submeshes_data)
    assert mats[0].is_missing is True
    assert any("missing material" in i.message.lower() for i in issues)


# ---------------------------------------------------------------------------
# Test Pure Analysis Logic: Deformation & Scaling
# ---------------------------------------------------------------------------


def test_analyze_deformation_healthy() -> None:
    blendshapes_data: list[dict[str, Any]] = [{"name": "Smile", "weight": 50.0}]
    bones_data: list[dict[str, Any]] = [{"name": "Hips", "lossyScale": [1.0, 1.0, 1.0], "isNull": False}]
    deform, issues = analyze_deformation(
        blendshapes_data=blendshapes_data,
        root_bone_scale=[1.0, 1.0, 1.0],
        root_bone_path="Hips",
        bones_data=bones_data,
    )
    assert isinstance(deform, DeformationInfo)
    assert deform.has_blendshapes is True
    assert deform.blendshape_count == 1
    assert deform.has_non_uniform_or_zero_scale is False
    assert len(issues) == 0


def test_analyze_deformation_zero_scale_and_extreme_blendshape() -> None:
    blendshapes_data: list[dict[str, Any]] = [{"name": "Blink", "weight": 200.0}]
    bones_data: list[dict[str, Any]] = []
    deform, issues = analyze_deformation(
        blendshapes_data=blendshapes_data,
        root_bone_scale=[0.0, 1.0, 1.0],
        root_bone_path="Hips",
        bones_data=bones_data,
    )
    assert deform.has_non_uniform_or_zero_scale is True
    assert any("zero or negative" in i.message.lower() for i in issues)
    assert any("unusual weight" in i.message.lower() for i in issues)


# ---------------------------------------------------------------------------
# Test Issue Classification
# ---------------------------------------------------------------------------


def test_classify_diagnostics_categories() -> None:
    # No issues
    cat, b_iss, brk_b, mat_m, def_m = classify_diagnostics([])
    assert cat == "none"
    assert not b_iss
    assert not brk_b
    assert not mat_m
    assert not def_m

    # Texture/Material issue (pink shader)
    mat_issue = DiagnosticIssue(
        category="texture_material",
        severity="error",
        message="Shader is pink/error shader",
    )
    cat, b_iss, brk_b, mat_m, def_m = classify_diagnostics([mat_issue])
    assert cat == "texture_material"
    assert mat_m is True
    assert brk_b is False

    # Geometry/Skinning issue (null bone)
    bone_issue = DiagnosticIssue(
        category="geometry_skinning",
        severity="error",
        message="Null bone in bones array",
    )
    cat, b_iss, brk_b, mat_m, def_m = classify_diagnostics([bone_issue])
    assert cat == "geometry_skinning"
    assert brk_b is True
    assert mat_m is False


# ---------------------------------------------------------------------------
# Test MCP Tool: skinned_mesh_diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_skinned_mesh_diagnostics_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "targetPath": "Character/Body",
            "hasSharedMesh": True,
            "meshName": "BodyMesh",
            "vertexCount": 1200,
            "subMeshCount": 1,
            "blendShapeCount": 2,
            "bindPosesCount": 2,
            "submeshes": [{"index": 0, "indexCount": 3600, "topology": "Triangles"}],
            "blendshapes": [{"name": "Smile", "weight": 0.0}, {"name": "Blink", "weight": 20.0}],
            "bones": [
                {"index": 0, "isNull": False, "name": "Hips", "path": "Hips", "lossyScale": [1.0, 1.0, 1.0]},
                {"index": 1, "isNull": False, "name": "Spine", "path": "Hips/Spine", "lossyScale": [1.0, 1.0, 1.0]},
            ],
            "hasRootBone": True,
            "rootBonePath": "Hips",
            "rootBoneScale": [1.0, 1.0, 1.0],
            "materials": [
                {
                    "index": 0,
                    "isMissing": False,
                    "name": "BodyMat",
                    "shaderName": "Universal Render Pipeline/Lit",
                    "isSupported": True,
                    "isErrorShader": False,
                    "mainTextureName": "body_diff",
                    "hasMainTexture": True,
                }
            ],
            "updateWhenOffscreen": True,
            "localCenter": [0.0, 1.0, 0.0],
            "localSize": [0.6, 1.8, 0.4],
            "worldCenter": [0.0, 1.0, 0.0],
            "worldSize": [0.6, 1.8, 0.4],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(mesh, "bridge", fake_bridge)

    result = await mesh.skinned_mesh_diagnostics("Character/Body")

    assert isinstance(result, SkinnedMeshDiagnosticsResult)
    assert result.success is True
    assert result.mesh_renderer_path == "Character/Body"
    assert result.mesh_name == "BodyMesh"
    assert result.vertex_count == 1200
    assert result.submesh_count == 1
    assert result.material_count == 1
    assert result.bone_count == 2
    assert result.has_bounds_issue is False
    assert result.has_broken_bones is False
    assert result.has_material_mismatch is False
    assert result.has_deformation_issue is False
    assert result.primary_issue_category == "none"
    assert result.is_sub_mesh_valid is True
    assert result.warnings == []


@pytest.mark.anyio
async def test_skinned_mesh_diagnostics_broken_bones_and_pink_shader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "targetPath": "Character/BrokenMesh",
            "hasSharedMesh": True,
            "meshName": "BrokenMesh",
            "vertexCount": 500,
            "subMeshCount": 1,
            "blendShapeCount": 0,
            "bindPosesCount": 2,
            "submeshes": [{"index": 0, "indexCount": 1500, "topology": "Triangles"}],
            "blendshapes": [],
            "bones": [
                {"index": 0, "isNull": True, "name": None, "path": None},
                {"index": 1, "isNull": False, "name": "Spine", "path": "Hips/Spine"},
            ],
            "hasRootBone": False,
            "rootBonePath": None,
            "rootBoneScale": None,
            "materials": [
                {
                    "index": 0,
                    "isMissing": False,
                    "name": "CorruptedMat",
                    "shaderName": "Hidden/InternalErrorShader",
                    "isSupported": False,
                    "isErrorShader": True,
                    "mainTextureName": None,
                    "hasMainTexture": False,
                }
            ],
            "updateWhenOffscreen": False,
            "localCenter": [0.0, 0.0, 0.0],
            "localSize": [0.0, 0.0, 0.0],
            "worldCenter": [0.0, 0.0, 0.0],
            "worldSize": [0.0, 0.0, 0.0],
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(mesh, "bridge", fake_bridge)

    result = await mesh.skinned_mesh_diagnostics("Character/BrokenMesh")

    assert result.success is True
    assert result.has_bounds_issue is True
    assert result.has_broken_bones is True
    assert result.has_material_mismatch is True
    assert len(result.issues) > 0


@pytest.mark.anyio
async def test_skinned_mesh_diagnostics_no_shared_mesh(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": True,
            "targetPath": "Character/EmptyMesh",
            "hasSharedMesh": False,
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(mesh, "bridge", fake_bridge)

    result = await mesh.skinned_mesh_diagnostics("Character/EmptyMesh")

    assert result.success is True
    assert result.mesh_name is None
    assert result.vertex_count == 0
    assert any("no sharedmesh" in w.lower() for w in result.warnings)


@pytest.mark.anyio
async def test_skinned_mesh_diagnostics_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    unity_response = {
        "success": True,
        "result": {
            "success": False,
            "error": "GameObject not found at hierarchy path: Character/Missing",
        },
    }
    fake_bridge = FakeBridge(execute_responses=[unity_response])
    monkeypatch.setattr(mesh, "bridge", fake_bridge)

    result = await mesh.skinned_mesh_diagnostics("Character/Missing")

    assert result.success is False
    assert "not found" in (result.error or "")


@pytest.mark.anyio
async def test_skinned_mesh_diagnostics_bridge_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bridge = FakeBridge(execute_responses=[ConnectionError("Bridge disconnected")])
    monkeypatch.setattr(mesh, "bridge", fake_bridge)

    result = await mesh.skinned_mesh_diagnostics("Character/Body")

    assert result.success is False
    assert "Bridge disconnected" in (result.error or "")
