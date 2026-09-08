import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
EXPECTED_SKILLS = [
    "visora-asset-workflow",
    "visora-animation-workflow",
    "visora-camera-action-workflow",
    "visora-rig-retarget-workflow",
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
