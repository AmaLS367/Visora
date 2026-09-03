from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from tarfile import open as open_tarfile
from typing import NoReturn
from zipfile import ZipFile

LICENSE_EXPRESSION = "License-Expression: Apache-2.0"


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def require_single_artifact(dist_dir: Path, pattern: str) -> Path:
    artifacts = sorted(dist_dir.glob(pattern))
    if len(artifacts) != 1:
        fail(f"Expected exactly one {pattern} artifact in {dist_dir}, found {len(artifacts)}.")
    return artifacts[0]


def validate_wheel(wheel: Path) -> None:
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_path = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        if metadata_path is None:
            fail("Wheel does not contain core metadata.")

        metadata = archive.read(metadata_path).decode("utf-8")
        if LICENSE_EXPRESSION not in metadata:
            fail("Wheel metadata does not declare Apache-2.0.")
        if "License-File: LICENSE" not in metadata:
            fail("Wheel metadata does not declare the distributed LICENSE file.")
        if "backend/py.typed" not in names:
            fail("Wheel does not contain the PEP 561 py.typed marker.")
        if not any(name.endswith("/LICENSE") for name in names):
            fail("Wheel does not contain the LICENSE file.")


def validate_sdist(sdist: Path) -> None:
    with open_tarfile(sdist, "r:gz") as archive:
        names = archive.getnames()
        if not any(name.endswith("/LICENSE") for name in names):
            fail("Source distribution does not contain the LICENSE file.")
        if not any(name.endswith("/backend/py.typed") for name in names):
            fail("Source distribution does not contain the PEP 561 py.typed marker.")


def main() -> None:
    parser = ArgumentParser(description="Validate Visora distribution metadata and required artifacts.")
    parser.add_argument("--dist-dir", default="dist", help="Directory containing the wheel and source distribution.")
    dist_dir = Path(parser.parse_args().dist_dir)

    validate_wheel(require_single_artifact(dist_dir, "*.whl"))
    validate_sdist(require_single_artifact(dist_dir, "*.tar.gz"))
    print("Distribution metadata and required artifacts are valid.")


if __name__ == "__main__":
    main()
