from backend.schemas.animation import (
    AnimationBindingCurve,
    AnimationEventInfo,
    BoneMatch,
    BoneNode,
    BoneSearchResult,
    ClipInspectorResult,
    DangerousCurveWarning,
    DuplicateBoneGroup,
    HelperBoneWarning,
    MmdBoneChain,
    SampleAnimationResult,
    SkeletonMapperResult,
    TransformPose,
)
from backend.schemas.base import BaseToolResult
from backend.schemas.bridge import (
    BridgeStatusResult,
    EditorStateInfo,
    PortScanResult,
)
from backend.schemas.mesh import (
    BoneBindingInfo,
    BoundsInfo,
    DeformationInfo,
    DiagnosticIssue,
    MaterialSlotInfo,
    SkinnedMeshDiagnosticsResult,
    SubMeshInfo,
)
from backend.schemas.queue import QueueStatusResult
from backend.schemas.scene import (
    EditorStateResult,
    PlayModeManagementResult,
    RestoreSceneResult,
    SafeTransactionResult,
    SaveSceneResult,
    WaitForEditorIdleResult,
)
from backend.schemas.vision import (
    CameraFramingDiagnosticsResult,
    FrameMotionMetrics,
    ListSceneCamerasResult,
    ProjectWorldPointsResult,
    SceneCameraInfo,
    ScreenPoint,
    ScreenshotResult,
    VideoFrame,
    VideoFrameSequence,
    VideoFramesResult,
    VideoMp4Result,
    VisualCapture,
    VisualComparisonResult,
    VisualInspectionResult,
)


def test_base_tool_result_defaults() -> None:
    res = BaseToolResult(success=True)
    assert res.success is True
    assert res.error is None

    res_err = BaseToolResult(success=False, error="Bridge disconnected")
    assert res_err.success is False
    assert res_err.error == "Bridge disconnected"

    dumped = res.model_dump()
    assert dumped["success"] is True
    assert dumped["error"] is None


def test_bridge_schemas_serialization() -> None:
    port_info = PortScanResult(port=7890, is_open=True, latency_ms=1.5)
    assert port_info.port == 7890
    assert port_info.is_open is True
    assert port_info.latency_ms == 1.5

    editor_info = EditorStateInfo(
        is_playing=False,
        is_paused=False,
        is_compiling=False,
        active_scene="Assets/Scenes/Main.unity",
        unity_version="2022.3.10f1",
    )
    assert editor_info.is_playing is False
    assert editor_info.active_scene == "Assets/Scenes/Main.unity"

    bridge_res = BridgeStatusResult(
        success=True,
        connected=True,
        active_port=7890,
        bridge_url="http://127.0.0.1",
        latency_ms=1.5,
        scanned_ports=[port_info],
        editor_state=editor_info,
        message="Connected to Unity Editor",
    )
    dumped = bridge_res.model_dump()
    assert dumped["active_port"] == 7890
    assert dumped["scanned_ports"][0]["port"] == 7890


def test_queue_schemas_serialization() -> None:
    q_res = QueueStatusResult(
        success=True,
        ticket_id="ticket-001",
        status="completed",
        progress=1.0,
        result={"baked": True},
        duration_seconds=3.25,
    )
    assert q_res.success is True
    assert q_res.ticket_id == "ticket-001"
    assert q_res.progress == 1.0
    assert q_res.duration_seconds == 3.25


def test_scene_schemas_serialization() -> None:
    # EditorStateResult
    state_res = EditorStateResult(
        success=True,
        is_idle=True,
        is_playing=False,
        is_compiling=False,
        is_updating=False,
        active_scene_name="TestScene",
        active_scene_path="Assets/Scenes/TestScene.unity",
        active_scene_dirty=False,
        loaded_scene_count=1,
    )
    assert state_res.is_idle is True
    assert state_res.active_scene_name == "TestScene"

    # WaitForEditorIdleResult
    idle_res = WaitForEditorIdleResult(
        success=True,
        is_idle=True,
        waited_seconds=0.1,
        message="Editor reached idle state",
    )
    assert idle_res.is_idle is True

    # PlayModeManagementResult
    play_res = PlayModeManagementResult(
        success=True,
        is_playing=True,
        previous_state=False,
        message="Entered Play Mode",
    )
    assert play_res.is_playing is True

    # SaveSceneResult
    save_res = SaveSceneResult(
        success=True,
        is_saved=True,
        scene_name="TestScene",
        scene_path="Assets/Scenes/TestScene.unity",
        was_dirty=True,
        message="Scene saved successfully",
    )
    assert save_res.is_saved is True

    # SafeTransactionResult
    tx_res = SafeTransactionResult(
        success=True,
        transaction_id="tx-999",
        undo_group=42,
        rolled_back=False,
        scene_saved=True,
        execution_result={"created": "Cube"},
        logs=["Created Cube"],
        message="Transaction complete",
    )
    assert tx_res.transaction_id == "tx-999"
    assert tx_res.undo_group == 42

    # RestoreSceneResult
    restore_res = RestoreSceneResult(
        success=True,
        reverted_undo=True,
        reloaded_scene=False,
        active_scene_name="TestScene",
        message="Scene restored",
    )
    assert restore_res.reverted_undo is True


def test_vision_schemas_serialization() -> None:
    # ScreenshotResult
    screen_res = ScreenshotResult(
        success=True,
        image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        camera_name="MainCamera",
        width=1920,
        height=1080,
    )
    assert screen_res.width == 1920
    assert screen_res.camera_name == "MainCamera"

    # VisualComparisonResult
    comp_res = VisualComparisonResult(
        success=True,
        same_dimensions=True,
        width=1920,
        height=1080,
        changed_pixel_ratio=0.02,
        mean_delta=1.5,
        max_delta=50,
        changed_bounds=[10, 10, 100, 100],
    )
    assert comp_res.changed_pixel_ratio == 0.02

    # VisualCapture & VisualInspectionResult
    capture = VisualCapture(
        mode="game_camera",
        image_base64="pngdata",
        width=640,
        height=360,
        camera_name="Main Camera",
    )
    insp_res = VisualInspectionResult(
        success=True,
        subject_path="Player",
        captures=[capture],
        recommended_interpretation="Inspect lighting artifacts",
    )
    assert len(insp_res.captures) == 1

    # SceneCameraInfo & ListSceneCamerasResult
    cam_info = SceneCameraInfo(
        name="Main Camera",
        path="Cameras/MainCamera",
        enabled=True,
        active=True,
        tag="MainCamera",
        depth=0.0,
        field_of_view=60.0,
        orthographic=False,
        orthographic_size=5.0,
    )
    list_cams = ListSceneCamerasResult(success=True, camera_count=1, cameras=[cam_info])
    assert list_cams.camera_count == 1
    assert list_cams.cameras[0].name == "Main Camera"

    # ScreenPoint & ProjectWorldPointsResult
    screen_pt = ScreenPoint(x=100.0, y=200.0, z=5.0, is_behind_camera=False)
    proj_res = ProjectWorldPointsResult(success=True, screen_points=[screen_pt])
    assert len(proj_res.screen_points) == 1
    assert proj_res.screen_points[0].x == 100.0

    # CameraFramingDiagnosticsResult
    framing_res = CameraFramingDiagnosticsResult(
        success=True,
        subject_path="Player",
        camera_name="Main Camera",
        viewport_bounds=[0.2, 0.2, 0.8, 0.8],
        visible_ratio=0.95,
        is_visible=True,
        is_behind_camera=False,
        is_clipped=False,
        framing_status="centered",
    )
    assert framing_res.framing_status == "centered"

    # VideoFrame, FrameMotionMetrics, VideoFrameSequence, VideoFramesResult, VideoMp4Result
    vf = VideoFrame(
        frame_index=0,
        timestamp_seconds=0.0,
        camera_name="Main",
        mode="game_camera",
        image_base64="abc",
        width=640,
        height=360,
    )
    metric = FrameMotionMetrics(
        from_frame=0,
        to_frame=1,
        changed_pixel_ratio=0.05,
        mean_delta=2.0,
        max_delta=40,
    )
    seq = VideoFrameSequence(
        camera_name="Main",
        mode="game_camera",
        duration_seconds=1.0,
        fps=30,
        frames=[vf],
        motion_metrics=[metric],
    )
    v_res = VideoFramesResult(
        success=True,
        sequences=[seq],
        recommended_interpretation="Check motion consistency",
    )
    assert len(v_res.sequences) == 1
    assert v_res.sequences[0].fps == 30

    mp4_res = VideoMp4Result(
        success=True,
        camera_name="Main",
        mode="game_camera",
        duration_seconds=1.0,
        fps=30,
        width=640,
        height=360,
        artifact_path="/tmp/video.mp4",
        video_base64="xyz",
    )
    assert mp4_res.format == "mp4"


def test_animation_schemas_serialization() -> None:
    # AnimationBindingCurve & DangerousCurveWarning & AnimationEventInfo
    curve = AnimationBindingCurve(
        path="Root/Hips",
        property_name="m_LocalPosition.x",
        type_name="UnityEngine.Transform",
        curve_type="position",
        keyframe_count=10,
        min_value=-1.0,
        max_value=1.0,
        start_value=0.0,
        end_value=0.0,
        is_constant=False,
    )
    danger = DangerousCurveWarning(
        risk_level="warning",
        binding_path="Root/Hips",
        property_name="m_LocalPosition.x",
        reason="Abnormal scale",
        description="Scale goes negative",
        recommendation="Clamp scale curve",
    )
    event = AnimationEventInfo(
        time=0.5,
        function_name="FootstepEvent",
        string_param="Left",
    )

    # ClipInspectorResult
    clip_res = ClipInspectorResult(
        success=True,
        clip_name="Walk",
        clip_path="Assets/Animations/Walk.anim",
        length=1.2,
        fps=30.0,
        loop_time=True,
        wrap_mode="Loop",
        is_legacy=False,
        has_root_motion=False,
        curves_count=1,
        events_count=1,
        bindings=[curve],
        dangerous_curves=[danger],
        events=[event],
    )
    assert clip_res.clip_name == "Walk"
    assert len(clip_res.bindings) == 1

    # TransformPose & SampleAnimationResult
    pose = TransformPose(
        path="Root/Hips",
        name="Hips",
        local_position=[0.0, 1.0, 0.0],
        local_rotation_euler=[0.0, 0.0, 0.0],
        local_scale=[1.0, 1.0, 1.0],
    )
    sample_res = SampleAnimationResult(
        success=True,
        clip_name="Walk",
        clip_path="Assets/Animations/Walk.anim",
        target_game_object="Player",
        sample_time=0.5,
        normalized_time=0.416,
        pose_restored=True,
        sampled_transforms={"Root/Hips": pose},
    )
    assert sample_res.sample_time == 0.5
    assert sample_res.pose_restored is True

    # BoneNode, DuplicateBoneGroup, HelperBoneWarning, MmdBoneChain, SkeletonMapperResult
    bone = BoneNode(
        path="Root/Hips",
        name="Hips",
        parent_path=None,
        depth=0,
        child_count=2,
        local_position=[0.0, 1.0, 0.0],
    )
    dup = DuplicateBoneGroup(name="Arm", paths=["Left/Arm", "Right/Arm"])
    helper = HelperBoneWarning(path="Root/Twist", name="Twist", reason="Twist bone suffix")
    mmd = MmdBoneChain(base_name="Skirt", primary_path="Root/Skirt", d_bone_path="Root/Skirt_D")

    skel_res = SkeletonMapperResult(
        success=True,
        root_transform_path="Root",
        bone_count=1,
        bones=[bone],
        mapping_source="avatar",
        is_valid=True,
        mappings={"Hips": "Root/Hips"},
        duplicate_bones=[dup],
        helper_bones=[helper],
        mmd_bone_chains=[mmd],
    )
    assert skel_res.is_valid is True
    assert skel_res.mapping_source == "avatar"

    # BoneMatch & BoneSearchResult
    match = BoneMatch(path="Root/Head", name="Head", match_type="exact", score=1.0)
    search_res = BoneSearchResult(
        success=True,
        root_transform_path="Root",
        query="Head",
        matches=[match],
    )
    assert len(search_res.matches) == 1
    assert search_res.matches[0].score == 1.0


def test_mesh_schemas_serialization() -> None:
    issue = DiagnosticIssue(
        category="geometry_skinning",
        severity="warning",
        message="Submesh vertex count is high",
        details={"vertex_count": 65000},
    )
    bounds = BoundsInfo(
        local_center=[0.0, 1.0, 0.0],
        local_size=[1.0, 2.0, 1.0],
        world_center=[0.0, 1.0, 0.0],
        world_size=[1.0, 2.0, 1.0],
        is_zero_volume=False,
        is_abnormal=False,
        update_when_offscreen=True,
    )
    bone_binding = BoneBindingInfo(
        bone_index=0,
        bone_name="Hips",
        bone_path="Root/Hips",
        is_null=False,
        has_bindpose=True,
    )
    mat_slot = MaterialSlotInfo(
        slot_index=0,
        material_name="PlayerMat",
        shader_name="Standard",
        is_missing=False,
        is_error_shader=False,
        main_texture_name="PlayerTex",
        has_main_texture=True,
    )
    submesh = SubMeshInfo(
        submesh_index=0,
        vertex_count=5000,
        triangle_count=2500,
        has_matching_material=True,
        topology="Triangles",
    )
    deform = DeformationInfo(
        has_blendshapes=True,
        blendshape_count=5,
        active_blendshapes=[{"name": "Smile", "weight": 50.0}],
        root_bone_path="Root/Hips",
        root_bone_scale=[1.0, 1.0, 1.0],
        has_non_uniform_or_zero_scale=False,
    )

    mesh_res = SkinnedMeshDiagnosticsResult(
        success=True,
        mesh_renderer_path="Player/Body",
        mesh_name="BodyMesh",
        vertex_count=5000,
        submesh_count=1,
        material_count=1,
        bone_count=1,
        bounds_center=[0.0, 1.0, 0.0],
        bounds_size=[1.0, 2.0, 1.0],
        is_sub_mesh_valid=True,
        has_bounds_issue=False,
        has_broken_bones=False,
        has_material_mismatch=False,
        has_deformation_issue=False,
        primary_issue_category="none",
        bounds=bounds,
        bone_bindings=[bone_binding],
        materials=[mat_slot],
        submeshes=[submesh],
        deformation=deform,
        issues=[issue],
    )
    assert mesh_res.mesh_renderer_path == "Player/Body"
    assert mesh_res.is_sub_mesh_valid is True
    assert len(mesh_res.issues) == 1
    assert mesh_res.bone_count == 1
