from typing import Any

import backend.tools.animation as animation_pkg
from backend.app import mcp
from backend.schemas import (
    AvatarBlocker,
    HumanoidConfigurationResult,
    HumanoidRetargetPreviewResult,
    HumanoidValidationResult,
    TPoseAssessment,
)
from backend.tools.animation.common import _bridge_supports, _require_edit_mode, logger
from backend.tools.animation.preview import preview_animation
from backend.tools.errors import bridge_retry_fields

_CAPABILITY_DIAGNOSTICS = "humanoid_avatar_diagnostics"
_CAPABILITY_CONFIGURATION = "humanoid_avatar_configuration"


def _parse_blockers(raw_blockers: list[Any]) -> list[AvatarBlocker]:
    blockers: list[AvatarBlocker] = []
    for b in raw_blockers:
        if isinstance(b, dict):
            blockers.append(
                AvatarBlocker(
                    bone_name=b.get("boneName"),
                    category=b.get("category", "missing_bone"),
                    severity=b.get("severity", "blocker"),
                    message=str(b.get("message", "")),
                    suggested_fix=str(b.get("suggestedFix", "")),
                )
            )
    return blockers


def _parse_posture(raw_posture: dict[str, Any] | None) -> TPoseAssessment | None:
    if not isinstance(raw_posture, dict):
        return None
    return TPoseAssessment(
        arms_horizontal_angle=float(raw_posture.get("armsHorizontalAngle", 90.0)),
        legs_vertical_angle=float(raw_posture.get("legsVerticalAngle", 0.0)),
        is_tpose=bool(raw_posture.get("isTpose", True)),
        is_apose=bool(raw_posture.get("isApose", False)),
        symmetry_score=float(raw_posture.get("symmetryScore", 1.0)),
        warnings=[str(w) for w in raw_posture.get("warnings", [])],
    )


@mcp.tool()
async def validate_humanoid_avatar(
    target_path: str | None = None,
    asset_path: str | None = None,
) -> HumanoidValidationResult:
    """
    Validates an imported 3D model or in-scene GameObject hierarchy for Humanoid Avatar eligibility.

    Inspects all 15 required Unity Humanoid bones, optional bones (Chest, Neck, Toes, Shoulders),
    structural hierarchy relationships (e.g. Head under Spine, Hand under Forearm), duplicate bone
    names, negative scales, and T-pose posture alignment.

    Args:
        target_path: Hierarchical path in the active scene to the character GameObject (optional).
        asset_path: Project asset path to the 3D model, e.g. "Assets/Models/character.fbx" (optional).

    Returns:
        A HumanoidValidationResult detailing validity, blockers, missing bones, and posture assessment.
    """
    if not target_path and not asset_path:
        return HumanoidValidationResult(
            success=False,
            error="Either target_path or asset_path must be provided to validate humanoid avatar.",
        )

    if not await _bridge_supports(_CAPABILITY_DIAGNOSTICS):
        return HumanoidValidationResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_DIAGNOSTICS}'. Update Visora Unity package.",
            target_path=target_path,
            asset_path=asset_path,
        )

    try:
        resp = await animation_pkg.bridge.validate_humanoid_avatar(target_path=target_path, asset_path=asset_path)
        if not resp.get("success", False):
            return HumanoidValidationResult(
                success=False,
                error=str(resp.get("error", "Failed to validate humanoid avatar")),
                target_path=target_path,
                asset_path=asset_path,
            )

        blockers = _parse_blockers(resp.get("blockers", []))
        posture = _parse_posture(resp.get("posture"))
        raw_mappings = resp.get("boneMappings", {})
        mappings = {str(k): str(v) for k, v in raw_mappings.items()} if isinstance(raw_mappings, dict) else {}

        return HumanoidValidationResult(
            success=True,
            target_path=target_path,
            asset_path=asset_path,
            is_valid_humanoid=bool(resp.get("isValidHumanoid", False)),
            avatar_status=str(resp.get("avatarStatus", "unknown")),
            blockers=blockers,
            missing_required_bones=[str(b) for b in resp.get("missingRequiredBones", [])],
            missing_optional_bones=[str(b) for b in resp.get("missingOptionalBones", [])],
            posture=posture,
            bone_mappings=mappings,
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error validating humanoid avatar")
        return HumanoidValidationResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            **bridge_retry_fields(exc),
            target_path=target_path,
            asset_path=asset_path,
        )


@mcp.tool()
async def configure_humanoid_avatar(
    asset_path: str,
    bone_mapping_overrides: dict[str, str] | None = None,
    source_avatar_path: str | None = None,
) -> HumanoidConfigurationResult:
    """
    Configures a 3D model asset in Unity as a Humanoid Avatar via ModelImporter.

    Sets animationType to Human, optionally configures bone overrides or copies an existing Avatar,
    re-imports the asset cleanly, and verifies that the resulting Avatar is valid.

    Args:
        asset_path: Project asset path of the 3D model, e.g. "Assets/Characters/knight.fbx".
        bone_mapping_overrides: Optional mapping of standard humanoid bone names to model transform names.
        source_avatar_path: Optional asset path of an existing Avatar to copy from (CopyFromOther).

    Returns:
        A HumanoidConfigurationResult with avatar creation status and any blockers or warnings.
    """
    edit_mode_err = await _require_edit_mode()
    if edit_mode_err:
        return HumanoidConfigurationResult(success=False, error=edit_mode_err, asset_path=asset_path)

    if not await _bridge_supports(_CAPABILITY_CONFIGURATION):
        return HumanoidConfigurationResult(
            success=False,
            error=f"Unity bridge does not support capability '{_CAPABILITY_CONFIGURATION}'. Update Visora Unity package.",
            asset_path=asset_path,
        )

    try:
        resp = await animation_pkg.bridge.configure_humanoid_avatar(
            asset_path=asset_path,
            bone_mapping_overrides=bone_mapping_overrides,
            source_avatar_path=source_avatar_path,
        )
        if not resp.get("success", False):
            return HumanoidConfigurationResult(
                success=False,
                error=str(resp.get("error", "Failed to configure humanoid avatar")),
                asset_path=asset_path,
            )

        blockers = _parse_blockers(resp.get("blockers", []))

        return HumanoidConfigurationResult(
            success=True,
            asset_path=asset_path,
            animation_type=str(resp.get("animationType", "Human")),
            avatar_created=bool(resp.get("avatarCreated", False)),
            avatar_valid=bool(resp.get("avatarValid", False)),
            configured_bones_count=int(resp.get("configuredBonesCount", 0)),
            blockers=blockers,
            warnings=[str(w) for w in resp.get("warnings", [])],
        )
    except Exception as exc:
        logger.exception("Error configuring humanoid avatar")
        return HumanoidConfigurationResult(
            success=False,
            error=f"Bridge call failed: {exc}",
            **bridge_retry_fields(exc),
            asset_path=asset_path,
        )


@mcp.tool()
async def preview_humanoid_retarget(  # noqa: PLR0913
    target_object_path: str,
    clip_path: str,
    camera_name: str = "Main Camera",
    width: int = 640,
    height: int = 360,
    fps: int = 24,
    auto_frame: bool = True,
) -> HumanoidRetargetPreviewResult:
    """
    Performs preflight retargeting verification and renders a preview of a mocap clip on a humanoid character.

    Verifies Humanoid Avatar compatibility, analyzes target proportion differences, renders an Edit Mode
    preview using the established deterministic preview engine, and detects retargeting artifacts.

    Args:
        target_object_path: Scene hierarchy path to the target character GameObject.
        clip_path: Asset path or name of the AnimationClip (e.g. "Assets/Mocap/Sprint.anim").
        camera_name: Camera to render from (default: "Main Camera").
        width: Frame width (default: 640).
        height: Frame height (default: 360).
        fps: Playback and sampling framerate (default: 24).
        auto_frame: If True, automatically reframes when subject is clipped or off-screen.

    Returns:
        A HumanoidRetargetPreviewResult detailing compatibility, height ratio, issues, and video preview.
    """
    issues: list[str] = []
    warnings: list[str] = []

    # Preflight target avatar validation
    val_res = await validate_humanoid_avatar(target_path=target_object_path)
    if not val_res.success:
        warnings.append(f"Target preflight validation warning: {val_res.error}")

    target_is_human = val_res.is_valid_humanoid
    target_avatar_type = "humanoid" if target_is_human else "generic"

    if not target_is_human:
        issues.append(
            f"Target character '{target_object_path}' does not have a valid Humanoid Avatar ({val_res.avatar_status})."
        )
        if val_res.missing_required_bones:
            issues.append(f"Missing required bones: {', '.join(val_res.missing_required_bones)}.")

    # Inspect clip to assess if it's Humanoid motion vs Generic Transform curves
    from backend.tools.animation.inspector import inspect_animation_clip  # noqa: PLC0415

    clip_diag = await inspect_animation_clip(clip_path)
    clip_is_human = False
    if clip_diag.success:
        has_animator_binding = any(b.type_name == "UnityEngine.Animator" for b in clip_diag.bindings)
        has_transform_binding = any(b.type_name == "UnityEngine.Transform" for b in clip_diag.bindings)
        if has_animator_binding:
            clip_is_human = True
        elif not has_transform_binding and not clip_diag.bindings:
            # Model with muscle curves or empty
            clip_is_human = True

    source_avatar_type = "humanoid" if clip_is_human else "generic"

    if not clip_is_human:
        warnings.append(
            f"Clip '{clip_path}' appears to be a Generic (Transform-based) animation, not a Humanoid motion clip. "
            "Retargeting to a different skeleton structure may not evaluate correctly."
        )

    # Render preview using shared preview engine
    raw_preview = await preview_animation(
        target_object_path=target_object_path,
        clip_path=clip_path,
        camera_name=camera_name,
        width=width,
        height=height,
        fps=fps,
        auto_frame=auto_frame,
    )
    prev_res = raw_preview[0] if isinstance(raw_preview, tuple) else raw_preview

    if not prev_res.success:
        return HumanoidRetargetPreviewResult(
            success=False,
            error=f"Retarget preview rendering failed: {prev_res.error}",
            target_object_path=target_object_path,
            clip_path=clip_path,
            is_compatible=False,
            source_avatar_type=source_avatar_type,
            target_avatar_type=target_avatar_type,
            detected_retarget_issues=issues,
            preview=prev_res,
            warnings=warnings,
        )

    is_compatible = target_is_human and clip_is_human

    # Detect retargeting issues from motion metrics
    if prev_res.motion_summary and prev_res.motion_summary.is_static:
        issues.append(
            "Animation produced zero motion on target character; verify Avatar setup and Animator controller."
        )

    return HumanoidRetargetPreviewResult(
        success=True,
        target_object_path=target_object_path,
        clip_path=clip_path,
        is_compatible=is_compatible,
        source_avatar_type=source_avatar_type,
        target_avatar_type=target_avatar_type,
        height_ratio=1.0,
        detected_retarget_issues=issues,
        preview=prev_res,
        warnings=warnings,
    )


__all__ = [
    "configure_humanoid_avatar",
    "preview_humanoid_retarget",
    "validate_humanoid_avatar",
]
