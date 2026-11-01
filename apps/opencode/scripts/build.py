#!/usr/bin/env python3
"""Build an OpenCode fnOS FPK from this repository's package skeleton.

The upstream OpenCode source is not vendored. This script downloads the
official @opencode/cli-linux-x64 npm artifact for the requested version,
verifies its npm integrity, and assembles the FPK with the verified fnpack
tool.

Tested on Linux amd64 (WSL Ubuntu 24.04).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

APP_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = APP_DIR / "package"
VERSION_FILE = APP_DIR / "VERSION"
SOURCE_COMMIT_FILE = APP_DIR / "SOURCE_COMMIT"

NPM_PACKAGE = "@opencode/cli-linux-x64"
FNPACK_VERSION = "1.2.3"
FNPACK_SHA256 = "54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93"
FNPACK_URL = "https://static2.fnnas.com/fnpack/fnpack-1.2.3-linux-amd64"
FNPACK_CACHE = Path.home() / ".cache" / "fnos-opencode-builder" / "fnpack" / FNPACK_VERSION / "linux-amd64" / "fnpack"


class BuildError(RuntimeError):
    pass


def log(message: str) -> None:
    print(message, file=sys.stderr)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_integrity(value: str) -> str:
    value = value.strip()
    if value.startswith("sha512-"):
        return value
    if value.startswith("sha512:"):
        return "sha512-" + value.split(":", 1)[1]
    return "sha512-" + value


def verify_integrity(path: Path, integrity: str) -> None:
    integrity = normalize_integrity(integrity)
    algorithm, encoded = integrity.split("-", 1)
    if algorithm != "sha512":
        raise BuildError(f"unsupported npm integrity algorithm: {algorithm}")
    expected = base64.b64decode(encoded)
    digest = hashlib.sha512()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.digest() != expected:
        raise BuildError(f"npm integrity mismatch for {path.name}")


def http_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "fnos-opencode-builder/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except OSError as exc:
        raise BuildError(f"failed to fetch {url}: {exc}") from exc


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "fnos-opencode-builder/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            total = int(response.headers.get("Content-Length", "0") or "0")
            done = 0
            last_report = 0
            with partial.open("wb") as stream:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    stream.write(chunk)
                    done += len(chunk)
                    if done - last_report >= 10 * 1024 * 1024:
                        if total:
                            log(f"  downloaded {done / 1048576:.1f}/{total / 1048576:.1f} MiB")
                        else:
                            log(f"  downloaded {done / 1048576:.1f} MiB")
                        last_report = done
        partial.replace(destination)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise BuildError(f"failed to download {url}: {exc}") from exc


def resolve_npm(version: str, package: str, tarball: str | None, expected: str | None) -> tuple[Path, str, dict]:
    metadata = None
    if tarball is None or expected is None:
        metadata = http_json(f"https://registry.npmjs.org/{package}/{version}")
        if not isinstance(metadata, dict):
            raise BuildError(f"npm registry returned invalid metadata for {package}@{version}")

    integrity = expected
    if integrity is None and metadata is not None:
        integrity = metadata.get("dist", {}).get("integrity")
    if not integrity:
        raise BuildError(
            "npm integrity is missing; pass --expected-sha512 for offline builds"
        )
    integrity = normalize_integrity(integrity)

    if tarball is not None:
        source = Path(tarball).expanduser().resolve()
        if not source.is_file():
            raise BuildError(f"npm tarball does not exist: {source}")
        verify_integrity(source, integrity)
        return source, integrity, metadata or {}

    if metadata is None:
        raise BuildError("npm metadata is required to resolve the tarball URL")
    url = metadata.get("dist", {}).get("tarball")
    if not isinstance(url, str) or not url:
        raise BuildError(f"npm metadata has no tarball URL for {package}@{version}")
    temporary = Path(tempfile.mkdtemp(prefix="opencode-npm-")) / "opencode.tgz"
    download(url, temporary)
    verify_integrity(temporary, integrity)
    return temporary, integrity, metadata


def extract_binary(tarball: Path, destination: Path) -> None:
    try:
        with tarfile.open(tarball, "r:gz") as archive:
            member = next(
                (item for item in archive.getmembers() if item.name == "package/bin/opencode"),
                None,
            )
            if member is None or not member.isfile():
                raise BuildError("npm tarball does not contain package/bin/opencode")
            source = archive.extractfile(member)
            if source is None:
                raise BuildError("npm tarball member package/bin/opencode is not readable")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as output:
                shutil.copyfileobj(source, output)
    except (tarfile.TarError, OSError) as exc:
        raise BuildError(f"failed to read npm tarball: {exc}") from exc
    destination.chmod(0o755)
    verify_elf(destination)


def verify_elf(path: Path, expected_machine: int = 62) -> None:
    with path.open("rb") as stream:
        header = stream.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise BuildError(f"{path.name} is not an ELF file")
    if header[4] != 2:
        raise BuildError(f"{path.name} is not a 64-bit ELF file")
    if header[5] != 1:
        raise BuildError(f"{path.name} is not little-endian")
    machine = struct.unpack_from("<H", header, 18)[0]
    if machine != expected_machine:
        raise BuildError(f"{path.name} has ELF machine {machine}, expected {expected_machine} (x86-64)")


def ensure_fnpack(explicit: str | None, allow_unverified: bool) -> Path:
    if platform.system() != "Linux" or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise BuildError("this builder currently requires a Linux amd64 host (use WSL on Windows)")

    candidate = Path(explicit).expanduser().resolve() if explicit else FNPACK_CACHE
    if candidate.is_file():
        digest = sha256_file(candidate)
        if digest == FNPACK_SHA256:
            candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return candidate
        if allow_unverified:
            log(f"warning: using unverified fnpack {candidate} sha256={digest}")
            return candidate
        raise BuildError(
            f"fnpack SHA-256 mismatch at {candidate}: got {digest}, expected {FNPACK_SHA256}"
        )

    if explicit:
        raise BuildError(f"fnpack binary does not exist: {candidate}")

    log(f"downloading fnpack {FNPACK_VERSION} to {candidate}")
    download(FNPACK_URL, candidate)
    digest = sha256_file(candidate)
    if digest != FNPACK_SHA256:
        candidate.unlink(missing_ok=True)
        raise BuildError(
            f"downloaded fnpack SHA-256 mismatch: got {digest}, expected {FNPACK_SHA256}"
        )
    candidate.chmod(candidate.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return candidate


def replace_placeholders(path: Path, values: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(key, value)
    path.write_text(text, encoding="utf-8")


def stage_package(version: str, binary: Path, integrity: str, binary_sha256: str, source_commit: str) -> tuple[Path, Path]:
    temporary = Path(tempfile.mkdtemp(prefix="opencode-fpk-"))
    stage = temporary / "stage"
    shutil.copytree(PACKAGE_DIR, stage)

    binary_target = stage / "app" / "bin" / "opencode"
    binary_target.unlink(missing_ok=True)
    shutil.copy2(binary, binary_target)
    binary_target.chmod(0o755)

    manifest_path = stage / "manifest"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest, count = re.subn(r"(?m)^version\s*=.*$", f"version               = {version}", manifest)
    if count != 1:
        raise BuildError("package/manifest must contain exactly one version line")
    manifest_path.write_text(manifest, encoding="utf-8")

    values = {
        "__VERSION__": version,
        "__NPM_INTEGRITY__": integrity,
        "__BINARY_SHA256__": binary_sha256,
        "__SOURCE_COMMIT__": source_commit,
    }
    for relative in ("app/README.txt", "app/PROVENANCE.txt"):
        path = stage / relative
        replace_placeholders(path, values)
        if "__" in path.read_text(encoding="utf-8"):
            raise BuildError(f"unresolved placeholder in {relative}")

    for path in (stage / "cmd").iterdir():
        if path.is_file():
            path.chmod(0o755)
    (stage / "app" / "bin" / "opencode-server").chmod(0o755)

    for path in list(stage.rglob("*")):
        if path.name in {".DS_Store", "Thumbs.db"}:
            path.unlink()

    for icon, expected in (("ICON.PNG", (64, 64)), ("ICON_256.PNG", (256, 256))):
        data = (stage / icon).read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise BuildError(f"{icon} is not a PNG file")
        width, height = struct.unpack(">II", data[16:24])
        if (width, height) != expected:
            raise BuildError(f"{icon} must be {expected[0]}x{expected[1]}, got {width}x{height}")

    return temporary, stage


def parse_manifest(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        fields[key.strip()] = value.strip()
    return fields


def run_fnpack(fnpack: Path, stage: Path, output: Path, version: str, suffix: str = "") -> Path:
    result = subprocess.run(
        [str(fnpack), "build", "--directory", str(stage)],
        cwd=stage,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise BuildError(
            "fnpack build failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    candidates = sorted(stage.glob("*.fpk"))
    if len(candidates) != 1:
        raise BuildError(f"fnpack must produce exactly one FPK, found {len(candidates)}")
    output.mkdir(parents=True, exist_ok=True)
    artifact_name = f"opencode-{version}-fnos-amd64"
    if suffix:
        artifact_name += f"-{suffix}"
    artifact = output / f"{artifact_name}.fpk"
    shutil.move(str(candidates[0]), artifact)
    digest = sha256_file(artifact)
    sidecar = artifact.with_name(artifact.name + ".sha256")
    sidecar.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
    return artifact


def safe_members(names: list[str], label: str) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise BuildError(f"{label} contains an unsafe path: {name}")
        if path.name in {".DS_Store", "Thumbs.db"}:
            raise BuildError(f"{label} contains host metadata: {name}")


def verify_fpk(artifact: Path, version: str, binary_sha256: str) -> dict:
    with tarfile.open(artifact, "r:gz") as outer:
        outer_names = outer.getnames()
        safe_members(outer_names, "outer FPK")
        manifest_member = outer.getmember("manifest")
        manifest_stream = outer.extractfile(manifest_member)
        if manifest_stream is None:
            raise BuildError("outer manifest is not readable")
        manifest = parse_manifest(manifest_stream.read().decode("utf-8-sig"))
        if manifest.get("appname") != "opencode":
            raise BuildError(f"manifest appname is {manifest.get('appname')!r}, expected opencode")
        if manifest.get("version") != version:
            raise BuildError(f"manifest version is {manifest.get('version')!r}, expected {version}")
        if manifest.get("platform") != "x86":
            raise BuildError(f"manifest platform is {manifest.get('platform')!r}, expected x86")
        checksum = manifest.get("checksum")
        if not checksum:
            raise BuildError("manifest has no app.tgz checksum")

        app_tgz_member = outer.getmember("app.tgz")
        app_tgz_stream = outer.extractfile(app_tgz_member)
        if app_tgz_stream is None:
            raise BuildError("outer app.tgz is not readable")
        with tempfile.NamedTemporaryFile(prefix="opencode-app-", suffix=".tgz", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        md5 = hashlib.md5()
        try:
            with app_tgz_stream, temporary_path.open("wb") as output:
                while True:
                    chunk = app_tgz_stream.read(1024 * 1024)
                    if not chunk:
                        break
                    md5.update(chunk)
                    output.write(chunk)
            if md5.hexdigest() != checksum:
                raise BuildError(
                    f"app.tgz checksum mismatch: got {md5.hexdigest()}, expected {checksum}"
                )

            with tarfile.open(temporary_path, "r:gz") as inner:
                inner_names = inner.getnames()
                safe_members(inner_names, "inner app.tgz")
                binary_member = inner.getmember("bin/opencode")
                binary_stream = inner.extractfile(binary_member)
                if binary_stream is None:
                    raise BuildError("inner bin/opencode is not readable")
                with tempfile.NamedTemporaryFile(prefix="opencode-bin-", delete=False) as temporary_binary:
                    binary_path = Path(temporary_binary.name)
                digest = hashlib.sha256()
                try:
                    with binary_stream, binary_path.open("wb") as output:
                        while True:
                            chunk = binary_stream.read(1024 * 1024)
                            if not chunk:
                                break
                            digest.update(chunk)
                            output.write(chunk)
                    if digest.hexdigest() != binary_sha256:
                        raise BuildError(
                            f"packaged binary SHA-256 mismatch: got {digest.hexdigest()}, "
                            f"expected {binary_sha256}"
                        )
                    verify_elf(binary_path)
                finally:
                    binary_path.unlink(missing_ok=True)

                for icon, expected in (("ICON.PNG", 64), ("ICON_256.PNG", 256)):
                    data = outer.extractfile(icon).read(24)
                    width, height = struct.unpack(">II", data[16:24])
                    if (width, height) != (expected, expected):
                        raise BuildError(f"{icon} must be {expected}x{expected}, got {width}x{height}")
        finally:
            temporary_path.unlink(missing_ok=True)

    return {
        "outer_member_count": len(outer_names),
        "inner_member_count": len(inner_names),
        "app_tgz_md5": md5.hexdigest(),
        "manifest_checksum": checksum,
        "binary_sha256": binary_sha256,
        "architecture": "amd64",
    }


def parse_args() -> argparse.Namespace:
    default_version = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.is_file() else ""
    default_commit = SOURCE_COMMIT_FILE.read_text(encoding="utf-8").strip() if SOURCE_COMMIT_FILE.is_file() else ""
    parser = argparse.ArgumentParser(description="Build the OpenCode fnOS FPK")
    parser.add_argument("--version", default=default_version, help="OpenCode version (default: VERSION)")
    parser.add_argument("--npm-package", default=NPM_PACKAGE, help="npm package that contains the Linux binary")
    parser.add_argument("--tarball", help="local npm tarball instead of downloading")
    parser.add_argument("--expected-sha512", help="expected npm sha512 integrity for offline builds")
    parser.add_argument("--fnpack", help="explicit fnpack binary")
    parser.add_argument("--allow-unverified-fnpack", action="store_true", help="accept an explicitly trusted fnpack")
    parser.add_argument("--out", default=str(APP_DIR / "dist"), help="output directory")
    parser.add_argument("--artifact-suffix", default="", help="artifact name suffix, for example r2")
    parser.add_argument("--source-commit", default=default_commit, help="upstream commit for provenance")
    parser.add_argument("--keep-staging", action="store_true", help="keep the temporary staging directory")
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = args.version.strip()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+_-]*", version):
        raise BuildError(f"invalid version: {version!r}")
    suffix = args.artifact_suffix.strip()
    if suffix and not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*", suffix):
        raise BuildError(f"invalid artifact suffix: {suffix!r}")

    temporary_root = None
    try:
        tarball, integrity, metadata = resolve_npm(
            version,
            args.npm_package,
            args.tarball,
            args.expected_sha512,
        )
        binary_temp = Path(tempfile.mkdtemp(prefix="opencode-bin-")) / "opencode"
        extract_binary(tarball, binary_temp)
        binary_sha256 = sha256_file(binary_temp)
        fnpack = ensure_fnpack(args.fnpack, args.allow_unverified_fnpack)

        temporary_root, stage = stage_package(
            version,
            binary_temp,
            integrity,
            binary_sha256,
            args.source_commit or f"see upstream tag v{version}",
        )
        artifact = run_fnpack(fnpack, stage, Path(args.out), version, suffix)
        verification = verify_fpk(artifact, version, binary_sha256)
        summary = {
            "ok": True,
            "version": version,
            "architecture": "amd64",
            "artifact_suffix": suffix,
            "artifact": {
                "path": str(artifact),
                "name": artifact.name,
                "size": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
            },
            "npm": {
                "package": args.npm_package,
                "integrity": integrity,
                "tarball": metadata.get("dist", {}).get("tarball") if metadata else None,
            },
            "binary": {"sha256": binary_sha256},
            "fnpack": {
                "version": FNPACK_VERSION,
                "path": str(fnpack),
                "sha256": sha256_file(fnpack),
            },
            "verification": verification,
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if temporary_root is not None and not args.keep_staging:
            shutil.rmtree(temporary_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
