#!/usr/bin/env python3
"""Create the patched Hermes Agent source tarball used by build.py.

The only source changes are:
  * remove the Android-only ``psutil @ git+...`` pin from pyproject.toml
  * regenerate uv.lock with the official PyPI index

The resulting tarball is bundled in the FPK so the NAS never needs to build
that Android-only git dependency during ``uv sync``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SKIP_PARTS = {"__pycache__", "node_modules", ".venv", ".uv-cache", "dist", "build"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_single_root(tarball: Path, destination: Path) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="hermes-source-"))
    try:
        with tarfile.open(tarball, "r:*") as archive:
            archive.extractall(temporary)
        entries = list(temporary.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise RuntimeError(f"{tarball} must contain one top-level directory")
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entries[0]), destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def make_tarball(source: Path, version: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source)
            if any(part in SKIP_PARTS for part in rel.parts):
                continue
            if path.name.endswith(SKIP_SUFFIXES):
                continue
            archive.add(path, arcname=f"hermes-agent-{version}/{rel.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.22.5")
    parser.add_argument("--source-tarball", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True, help="uv 0.13.5 binary")
    parser.add_argument("--python", type=Path, required=True, help="Python 3.14 executable")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    version = args.version.strip()
    source_tarball = args.source_tarball.expanduser().resolve()
    if not source_tarball.is_file():
        raise SystemExit(f"source tarball not found: {source_tarball}")
    uv = args.uv.expanduser().resolve()
    python = args.python.expanduser().resolve()
    if not uv.is_file() or not python.is_file():
        raise SystemExit("--uv and --python must point to executable files")

    output = args.output
    if output is None:
        output = Path(__file__).resolve().parent.parent / ".cache" / f"hermes-agent-{version}-fnos.tar.gz"
    output = output.expanduser().resolve()

    work = Path(tempfile.mkdtemp(prefix="hermes-patch-"))
    try:
        source = work / f"hermes-agent-{version}"
        extract_single_root(source_tarball, source)

        pyproject = source / "pyproject.toml"
        lines = pyproject.read_text(encoding="utf-8").splitlines()
        filtered = [
            line for line in lines
            if "psutil @ git+https://github.com/giampaolo/psutil.git" not in line
        ]
        if len(filtered) == len(lines):
            raise SystemExit("Android psutil pin not found in pyproject.toml")
        pyproject.write_text("\n".join(filtered) + "\n", encoding="utf-8")

        env = os.environ.copy()
        env.pop("UV_INDEX_URL", None)
        env["UV_PYTHON"] = str(python)
        env["UV_CACHE_DIR"] = str(work / ".uv-cache")
        result = subprocess.run(
            [str(uv), "lock"],
            cwd=source,
            env=env,
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise SystemExit(
                "uv lock failed\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        lock = (source / "uv.lock").read_text(encoding="utf-8")
        if "giampaolo/psutil" in lock:
            raise SystemExit("uv.lock still contains the Android psutil git package")

        make_tarball(source, version, output)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    summary = {
        "ok": True,
        "version": version,
        "patched_source": {
            "path": str(output),
            "name": output.name,
            "size": output.stat().st_size,
            "sha256": sha256_file(output),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
