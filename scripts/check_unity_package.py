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


def run(command: list[str], step: str, managed_dir: Path) -> None:
    """
    Runs one gate command with the Unity path supplied through the environment.

    It cannot be passed as an MSBuild -p: argument: `dotnet format` rejects unknown arguments and
    exits with its usage text, so the format gate failed before inspecting a single file. MSBuild
    reads environment variables as properties, which both `build` and `format` honour.
    """
    print(f"==> {step}")
    environment = {**os.environ, "UnityManagedDir": str(managed_dir)}
    result = subprocess.run(command, cwd=REPO_ROOT, check=False, env=environment)
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
    parser.add_argument(
        "--format", action="store_true", help="Also verify C# whitespace formatting, not only compilation."
    )
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
    ]
    run(build, "Compiling unity-package/Editor", managed_dir)

    if args.format:
        # whitespace, not the full `dotnet format`: the default also runs analyzer fixes and exits
        # non-zero when it cannot auto-fix a diagnostic, which reports an analyzer finding as a
        # formatting failure. Analyzers are already enforced by the compile step above.
        verify = [
            "dotnet",
            "format",
            "whitespace",
            str(GATE_PROJECT),
            "--verify-no-changes",
            "--no-restore",
        ]
        run(verify, "Verifying C# formatting", managed_dir)

    print("Unity package compiles cleanly.")


if __name__ == "__main__":
    main()
