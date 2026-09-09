from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from argparse import ArgumentParser
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "unity-package"
ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
UNITY_SEARCH_ROOTS = (
    Path.home() / "Unity" / "Hub" / "Editor",
    Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Unity" / "Hub" / "Editor",
    Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Unity" / "Hub" / "Editor",
    Path("/opt/unity/editors"),
    Path("/Applications/Unity/Hub/Editor"),
)


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def _editor_binary(version_dir: Path) -> Path:
    if os.name == "nt":
        return version_dir / "Editor" / "Unity.exe"
    mac_binary = version_dir / "Unity.app" / "Contents" / "MacOS" / "Unity"
    if mac_binary.is_file():
        return mac_binary
    return version_dir / "Editor" / "Unity"


def resolve_unity_editor(explicit: str | None) -> Path:
    for candidate in (explicit, os.environ.get("VISORA_UNITY_EDITOR")):
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve()
        if path.is_dir():
            path = _editor_binary(path)
        if not path.is_file():
            fail(f"Unity Editor executable '{path}' does not exist.")
        return path

    for root in UNITY_SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for version_dir in sorted(root.iterdir(), reverse=True):
            editor = _editor_binary(version_dir)
            if editor.is_file():
                return editor

    fail("No Unity Editor was found. Install Unity or set VISORA_UNITY_EDITOR to its executable.")


def infer_unity_version(editor: Path) -> str:
    version_pattern = re.compile(r"^\d+\.\d+\.\d+[abfp]\d+$")
    for part in reversed(editor.parts):
        if version_pattern.match(part):
            return part

    completed = subprocess.run(
        [str(editor), "-version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    version = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0 or not version_pattern.match(version):
        fail(f"Could not determine the Unity version for '{editor}'. Pass --unity-version explicitly.")
    return version


def create_test_project(project_root: Path, unity_version: str) -> None:
    (project_root / "Assets").mkdir(parents=True)
    (project_root / "Packages").mkdir()
    (project_root / "ProjectSettings").mkdir()

    manifest = {
        "dependencies": {
            "com.unity.test-framework": "1.8.0",
            "com.visora.editor": f"file:{PACKAGE_ROOT.resolve().as_posix()}",
        },
        "testables": ["com.visora.editor"],
    }
    (project_root / "Packages" / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (project_root / "ProjectSettings" / "ProjectVersion.txt").write_text(
        f"m_EditorVersion: {unity_version}\n", encoding="utf-8"
    )


def read_test_counts(results_path: Path) -> tuple[int, int]:
    if not results_path.is_file():
        fail(f"Unity did not produce test results at '{results_path}'.")
    root = ET.parse(results_path).getroot()
    total = int(root.attrib.get("testcasecount", root.attrib.get("total", "0")))
    failed = int(root.attrib.get("failed", "0"))
    return total, failed


def main() -> None:
    parser = ArgumentParser(description="Run Visora's Unity EditMode integration tests in a temporary project.")
    parser.add_argument("--unity-editor", help="Path to the Unity executable or version directory.")
    parser.add_argument("--unity-version", help="Version written to ProjectVersion.txt (normally inferred).")
    parser.add_argument("--timeout", type=int, default=900, help="Maximum Unity runtime in seconds.")
    args = parser.parse_args()

    editor = resolve_unity_editor(args.unity_editor)
    unity_version = args.unity_version or infer_unity_version(editor)
    ARTIFACTS_ROOT.mkdir(exist_ok=True)
    results_path = ARTIFACTS_ROOT / "unity-editmode-results.xml"
    log_path = ARTIFACTS_ROOT / "unity-editmode.log"
    results_path.unlink(missing_ok=True)
    log_path.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="visora-unity-tests-") as temp_dir:
        project_root = Path(temp_dir)
        create_test_project(project_root, unity_version)
        command = [
            str(editor),
            "-batchmode",
            "-nographics",
            "-projectPath",
            str(project_root),
            "-runTests",
            "-testPlatform",
            "EditMode",
            "-testResults",
            str(results_path),
            "-logFile",
            str(log_path),
        ]
        print(f"Unity Editor: {editor}")
        print("==> Running unity-package EditMode tests")
        try:
            completed = subprocess.run(command, cwd=REPO_ROOT, check=False, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            fail(f"Unity EditMode tests exceeded the {args.timeout}s timeout. See '{log_path}'.")

    total, failed = read_test_counts(results_path)
    if total == 0:
        fail(f"Unity reported zero discovered tests. See '{log_path}'.")
    if completed.returncode != 0 or failed:
        fail(
            f"Unity EditMode tests failed: {failed}/{total} failed, process exit {completed.returncode}. "
            f"Results: '{results_path}', log: '{log_path}'."
        )
    print(f"Unity EditMode tests passed: {total}/{total}.")


if __name__ == "__main__":
    main()
