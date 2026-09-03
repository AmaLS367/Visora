from __future__ import annotations

import os
import shutil
import subprocess
from argparse import ArgumentParser
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_PROJECT = REPO_ROOT / "tools" / "unity-compile-gate" / "Visora.Editor.Gate.csproj"
UNITY_HUB_EDITORS = Path.home() / "Unity" / "Hub" / "Editor"
UNITY_SEARCH_ROOTS = (UNITY_HUB_EDITORS, Path("/opt/unity/editors"), Path("/Applications/Unity/Hub/Editor"))


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def resolve_managed_dir(explicit: str | None) -> Path:
    """
    Locates the Managed directory of a Unity installation, holding UnityEngine.dll and UnityEditor.dll.

    The compile gate needs real Unity assemblies to reference, so an installation must be present.
    VISORA_UNITY_MANAGED_DIR overrides discovery for CI images with a non-standard layout.
    """
    candidates = [explicit, os.environ.get("VISORA_UNITY_MANAGED_DIR")]
    for candidate in candidates:
        if candidate:
            managed = Path(candidate)
            if not managed.is_dir():
                fail(f"Unity Managed directory '{managed}' does not exist.")
            return managed

    for root in UNITY_SEARCH_ROOTS:
        if not root.is_dir():
            continue
        for version_dir in sorted(root.iterdir(), reverse=True):
            managed = version_dir / "Editor" / "Data" / "Managed"
            if (managed / "UnityEditor.dll").is_file():
                return managed

    fail(
        "No Unity installation was found. Install Unity, or point VISORA_UNITY_MANAGED_DIR at the "
        "Editor/Data/Managed directory of one."
    )


def run(command: list[str], step: str) -> None:
    print(f"==> {step}")
    result = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if result.returncode != 0:
        fail(f"{step} failed with exit code {result.returncode}.")


def main() -> None:
    parser = ArgumentParser(
        description=(
            "Compiles the Visora Unity Editor package against real Unity assemblies. Unity would "
            "otherwise be the only thing that ever compiles this code, hiding C# errors until import."
        )
    )
    parser.add_argument("--unity-managed-dir", default=None, help="Path to <Unity>/Editor/Data/Managed.")
    parser.add_argument("--format", action="store_true", help="Also verify C# formatting instead of only compiling.")
    args = parser.parse_args()

    if shutil.which("dotnet") is None:
        fail("The .NET SDK is required for the Unity package compile gate but 'dotnet' is not on PATH.")

    managed_dir = resolve_managed_dir(args.unity_managed_dir)
    print(f"Unity assemblies: {managed_dir}")

    build = [
        "dotnet",
        "build",
        str(GATE_PROJECT),
        "--nologo",
        "--no-incremental",
        "-v",
        "q",
        f"-p:UnityManagedDir={managed_dir}",
    ]
    run(build, "Compiling unity-package/Editor")

    if args.format:
        verify = [
            "dotnet",
            "format",
            str(GATE_PROJECT),
            "--verify-no-changes",
            "--no-restore",
            f"-p:UnityManagedDir={managed_dir}",
        ]
        run(verify, "Verifying C# formatting")

    print("Unity package compiles cleanly.")


if __name__ == "__main__":
    main()
