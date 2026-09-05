import pytest

from backend.tools.animation._shared_csharp import extract_as_local_function

_AUTHORING_CS = "AnimationAuthoringService.cs"
_BACKUP_CS = "AnimationBackupService.cs"


@pytest.mark.parametrize(
    ("filename", "region_name"),
    [
        (_AUTHORING_CS, "ResolveComponentType"),
        (_AUTHORING_CS, "ResolveChannels"),
        (_AUTHORING_CS, "MapTangentMode"),
        (_AUTHORING_CS, "FindKeyIndexNearTime"),
        (_AUTHORING_CS, "KeyframeHelpers"),
        (_AUTHORING_CS, "SetKeyframe"),
        (_AUTHORING_CS, "MoveKeyframe"),
        (_AUTHORING_CS, "RemoveKeyframe"),
        (_AUTHORING_CS, "ListKeyframes"),
        (_AUTHORING_CS, "SetKeyframeHold"),
        (_AUTHORING_CS, "CreateEvent"),
        (_AUTHORING_CS, "RemoveEvent"),
        (_BACKUP_CS, "PathAndModeGuards"),
        (_BACKUP_CS, "IdempotencyCache"),
        (_BACKUP_CS, "WriteBackup"),
        (_BACKUP_CS, "ListBackups"),
        (_BACKUP_CS, "RestoreBackup"),
    ],
)
def test_every_shared_region_is_present_and_nonempty(filename: str, region_name: str) -> None:
    text = extract_as_local_function(filename, region_name)
    assert text.strip() != ""
    assert "SHARED-ALGORITHM" not in text  # the markers themselves are stripped from the extract


def test_extracted_text_has_no_access_modifier_left_on_its_first_declaration() -> None:
    text = extract_as_local_function(_AUTHORING_CS, "ResolveComponentType")
    first_line = text.strip().splitlines()[0]
    assert not first_line.startswith("public ")
    assert not first_line.startswith("private ")


def test_missing_region_raises_value_error() -> None:
    with pytest.raises(ValueError, match="NotARealRegion"):
        extract_as_local_function(_AUTHORING_CS, "NotARealRegion")


def test_missing_file_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        extract_as_local_function("NotARealFile.cs", "Anything")
