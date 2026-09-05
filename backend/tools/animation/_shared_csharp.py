import re
from functools import cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKOUT_DIR = _REPO_ROOT / "unity-package" / "Editor" / "Services"
_PACKAGED_DIR = Path(__file__).resolve().parent.parent.parent / "_unity_shared"

_LEADING_MODIFIER = re.compile(r"^(\s*)(public|private|internal|protected)\s+static\b", re.MULTILINE)


@cache
def _read_source(filename: str) -> str:
    checkout_path = _CHECKOUT_DIR / filename
    if checkout_path.is_file():
        return checkout_path.read_text(encoding="utf-8")

    packaged_path = _PACKAGED_DIR / filename
    if packaged_path.is_file():
        return packaged_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"'{filename}' was not found in a repo checkout ('{checkout_path}') or as a packaged "
        f"copy ('{packaged_path}'). A checkout needs the former; a built wheel needs the latter "
        "via pyproject.toml's wheel force-include entries."
    )


def extract_as_local_function(filename: str, region_name: str) -> str:
    """
    Extracts the text between `// SHARED-ALGORITHM:<region_name> START` and the matching `END`
    comment in `filename`, with the leading access modifier (public/private/internal/protected)
    stripped from every declaration it contains.

    The strip matters because this text is pasted as a sequence of C# *local functions* inside
    another method's body (see authoring_scripts.py) — local functions do not accept access
    modifiers, only the compiled service's own class-member declarations do, and one canonical
    text has to serve both. A missing region raises immediately rather than the legacy and native
    paths silently drifting apart the moment someone renames or removes one without updating the
    other.
    """
    source = _read_source(filename)
    pattern = re.compile(
        rf"// SHARED-ALGORITHM:{re.escape(region_name)} START\n(.*?)// SHARED-ALGORITHM:{re.escape(region_name)} END",
        re.DOTALL,
    )
    match = pattern.search(source)
    if match is None:
        raise ValueError(
            f"SHARED-ALGORITHM region '{region_name}' not found in '{filename}'. "
            "It was renamed or removed without updating authoring_scripts.py."
        )
    return _LEADING_MODIFIER.sub(r"\1static", match.group(1))
