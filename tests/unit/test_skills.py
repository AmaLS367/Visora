import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
EXPECTED_SKILLS = [
    "visora-asset-workflow",
    "visora-animation-workflow",
    "visora-camera-action-workflow",
    "visora-rig-retarget-workflow",
    "visora-contact-ik-workflow",
    "visora-gaze-and-acting-workflow",
    "visora-animation-qa-workflow",
    "visora-motion-polish-workflow",
    "visora-camera-contact-workflow",
    "visora-sequence-authoring-workflow",
    "visora-lookdev-workflow",
]


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parses simple YAML frontmatter from a markdown file."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    raw_fm = parts[1].strip()
    body = parts[2].strip()
    fm: dict[str, str] = {}
    for line in raw_fm.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def test_expected_skills_exist() -> None:
    assert SKILLS_DIR.is_dir()
    for skill_name in EXPECTED_SKILLS:
        skill_dir = SKILLS_DIR / skill_name
        assert skill_dir.is_dir(), f"Expected skill directory missing: {skill_name}"
        skill_file = skill_dir / "SKILL.md"
        assert skill_file.is_file(), f"SKILL.md missing in {skill_name}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_validity(skill_name: str) -> None:
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(content)
    assert fm, f"Failed to parse frontmatter in {skill_name}/SKILL.md"
    assert fm.get("name") == skill_name, f"Skill name '{fm.get('name')}' must match directory '{skill_name}'"
    assert "description" in fm, f"Skill {skill_name} must contain 'description' in frontmatter"
    assert len(fm["description"]) > 20, f"Skill {skill_name} must have a detailed description"
    assert len(body) > 100, f"Skill {skill_name} body must not be empty"


def test_animation_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-animation-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "never infer animation success from a static screenshot" in lower
    assert "smallest safe preview" in lower
    assert "preview_animation" in content
    assert "motion_summary.is_static" in content
    assert "analyze_contact_constraints" in content
    assert "bake_contact_constraints" in content
    assert "concrete bridge" in lower


def test_camera_action_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-camera-action-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "authoritative impact timestamp" in lower
    assert "no unsynchronized procedural camera shake" in lower
    assert "never infer impact synchronization from a static screenshot" in lower
    assert "set_keyframe_hold" in content
    assert "create_animation_event" in content
    assert "diagnose_camera_framing" in content
    assert "project_world_points" in content


def test_rig_retarget_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-rig-retarget-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "never infer retargeting success from a static screenshot" in lower
    assert "validate_humanoid_avatar" in content
    assert "configure_humanoid_avatar" in content
    assert "preview_humanoid_retarget" in content
    assert "generic / no-avatar fallback" in lower
    assert "never force humanoid mode" in lower


def test_contact_ik_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-contact-ik-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "never infer ik or contact success from a static screenshot" in lower
    assert "solve_two_bone_ik" in content
    assert "place_effector_in_viewport" in content
    assert "reach_distance" in content
    assert "preview_animation" in content


def test_gaze_acting_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-gaze-and-acting-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "never turn only the head bone" in lower
    assert "never infer natural acting from a static screenshot" in lower
    assert "solve_character_gaze" in content
    assert "chest_weight" in content
    assert "was_clamped" in content


def test_animation_qa_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-animation-qa-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "never commit an animation without running temporal qa" in lower
    assert "treat quaternion sign flips as critical defects" in lower
    assert "detect_curve_discontinuities" in content
    assert "analyze_joint_motion" in content
    assert "compare_animation_previews" in content


def test_motion_polish_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-motion-polish-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "motion travels in continuous arcs" in lower
    assert "every energetic action requires anticipation" in lower
    assert "never infer animation polish from a static screenshot" in lower
    assert "analyze_joint_motion" in content
    assert "set_keyframe_hold" in content


def test_camera_contact_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-camera-contact-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "authoritative timestamp" in lower
    assert "never add unsynchronized procedural camera shake" in lower
    assert "solve_camera_subject_contact" in content
    assert "place_effector_in_viewport" in content


def test_sequence_authoring_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-sequence-authoring-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "edit_animation_transaction" in lower
    assert "never execute disconnected single-keyframe writes" in lower
    assert "edit_animation_transaction" in content
    assert "preview_animation" in content


def test_lookdev_workflow_skill_acceptance() -> None:
    content = (SKILLS_DIR / "visora-lookdev-workflow" / "SKILL.md").read_text(encoding="utf-8")
    lower = content.lower()
    assert "silhouette contrast" in lower
    assert "never leave scenes in unlit" in lower
    assert "diagnose_camera_framing" in content
    assert "capture_camera_screenshot" in content
