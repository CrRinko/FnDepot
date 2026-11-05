#!/usr/bin/env python3
"""Build and validate the GitLab fnOS Docker application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
PACKAGE_DIR = APP_DIR / "package"
VERSION_FILE = APP_DIR / "VERSION"
APP_VERSION_FILE = APP_DIR / "APP_VERSION"
PROVENANCE_FILE = APP_DIR / "provenance.json"

FNPACK_VERSION = "1.2.3"
FNPACK_SHA256 = "54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93"
FNPACK_URL = f"https://static2.fnnas.com/fnpack/fnpack-{FNPACK_VERSION}-linux-amd64"
FNPACK_CACHE = (
    Path.home()
    / ".cache"
    / "fnos-gitlab-builder"
    / "fnpack"
    / FNPACK_VERSION
    / "linux-amd64"
    / "fnpack"
)

APPNAME = "gitlab"
IMAGE = "gitlab/gitlab-ce:19.5.3-ce.0"
CMD_SCRIPTS = [
    "main",
    "install_init",
    "install_callback",
    "upgrade_init",
    "upgrade_callback",
    "uninstall_init",
    "uninstall_callback",
    "config_init",
    "config_callback",
]

MAX_FPK_SIZE = 1024 * 1024


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


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[key.strip()] = value
    return result


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise BuildError(f"not a PNG: {path}")
    return struct.unpack(">II", data[16:24])


def download(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    log(f"downloading {url}")
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "fnos-gitlab-builder/1.0"}
        )
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as stream:
            shutil.copyfileobj(response, stream, length=1024 * 1024)
        actual = sha256_file(partial)
        if actual != expected_sha256:
            raise BuildError(f"checksum mismatch for {url}: got {actual}")
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def ensure_fnpack(explicit: Path | None) -> Path:
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        if not candidate.is_file():
            raise BuildError(f"fnpack does not exist: {candidate}")
        if sha256_file(candidate) != FNPACK_SHA256:
            raise BuildError(f"fnpack checksum mismatch: {candidate}")
        return candidate
    if FNPACK_CACHE.is_file() and sha256_file(FNPACK_CACHE) == FNPACK_SHA256:
        return FNPACK_CACHE
    download(FNPACK_URL, FNPACK_CACHE, FNPACK_SHA256)
    FNPACK_CACHE.chmod(0o755)
    return FNPACK_CACHE


def privacy_scan() -> None:
    phone_re = re.compile(r"(?<!\d)\d{11,}(?!\d)")
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    private_ip_re = re.compile(
        r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    )
    excluded = {".cache", "dist", "__pycache__", "tests"}
    for path in APP_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if any(part in excluded for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            line = re.sub(r"\b[0-9a-fA-F]{32,}\b", "", line)
            for match in phone_re.findall(line):
                raise BuildError(f"privacy scan: phone-like number in {path}:{lineno}: {match}")
            for match in email_re.findall(line):
                raise BuildError(f"privacy scan: email in {path}:{lineno}: {match}")
            for match in private_ip_re.findall(line):
                raise BuildError(f"privacy scan: private IP in {path}:{lineno}: {match}")
            if "PRIVATE KEY" in line or "BEGIN CERTIFICATE" in line:
                raise BuildError(f"privacy scan: key/certificate material in {path}:{lineno}")


def require_file(path: Path) -> None:
    if not path.is_file():
        raise BuildError(f"missing required file: {path}")


def check_scripts() -> None:
    for name in CMD_SCRIPTS:
        path = PACKAGE_DIR / "cmd" / name
        require_file(path)
        if not os.access(path, os.X_OK):
            raise BuildError(f"script is not executable: {path}")
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        if result.returncode != 0:
            raise BuildError(f"bash syntax error in {path}: {result.stderr}")
    bin_dir = PACKAGE_DIR / "app" / "bin"
    if bin_dir.is_dir():
        for path in bin_dir.iterdir():
            if path.is_file() and not os.access(path, os.X_OK):
                raise BuildError(f"script is not executable: {path}")
            if path.suffix == ".py":
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(path)],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise BuildError(f"python syntax error in {path}: {result.stderr}")


def check_only() -> int:
    for required in (VERSION_FILE, APP_VERSION_FILE, PROVENANCE_FILE):
        require_file(required)
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    app_version = APP_VERSION_FILE.read_text(encoding="utf-8").strip()
    provenance = json.loads(PROVENANCE_FILE.read_text(encoding="utf-8"))
    manifest = parse_manifest((PACKAGE_DIR / "manifest").read_text(encoding="utf-8"))
    resource = json.loads((PACKAGE_DIR / "config/resource").read_text(encoding="utf-8"))
    ui = json.loads((PACKAGE_DIR / "app/ui/config").read_text(encoding="utf-8"))

    if version != "19.5.3" or app_version != "19.5.3":
        raise BuildError(f"VERSION/APP_VERSION must be 19.5.3, got {version}/{app_version}")
    if provenance.get("app_version") != app_version or provenance.get("version") != version:
        raise BuildError("provenance.json versions do not match VERSION/APP_VERSION")
    expected_manifest = {
        "appname": APPNAME,
        "version": app_version,
        "platform": "x86",
        "service_port": "8443",
        "checkport": "false",
        "desktop_applaunchname": "gitlab.main",
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            raise BuildError(f"manifest {key} is {manifest.get(key)!r}, expected {expected!r}")
    projects = resource.get("docker-project", {}).get("projects", [])
    if projects != [{"name": "gitlab", "path": "docker"}]:
        raise BuildError(f"unexpected docker-project: {projects!r}")

    compose = (PACKAGE_DIR / "app/docker/docker-compose.yaml").read_text(encoding="utf-8")
    if not re.search(r"(?m)^name:\s*gitlab\s*$", compose):
        raise BuildError("compose must start with project name gitlab")
    if f"image: {IMAGE}" not in compose:
        raise BuildError(f"compose must use {IMAGE}")
    if ":latest" in compose:
        raise BuildError("compose must not use the latest tag")
    if "gitlab.main" not in ui.get(".url", {}):
        raise BuildError("app/ui/config must define gitlab.main")
    entry = ui[".url"]["gitlab.main"]
    if entry.get("port") != "${HTTP_PORT}" or entry.get("protocol") != "http":
        raise BuildError("app/ui/config must use ${HTTP_PORT} over http for the redirect entry")

    check_scripts()
    for wizard in ("install", "config", "uninstall"):
        path = PACKAGE_DIR / "wizard" / wizard
        require_file(path)
        json.loads(path.read_text(encoding="utf-8"))

    icons = {
        APP_DIR / "icon-64.png": 64,
        APP_DIR / "icon-256.png": 256,
        PACKAGE_DIR / "ICON.PNG": 64,
        PACKAGE_DIR / "ICON_256.PNG": 256,
        PACKAGE_DIR / "app/ui/images/icon_64.png": 64,
        PACKAGE_DIR / "app/ui/images/icon_256.png": 256,
    }
    for path, expected in icons.items():
        require_file(path)
        if png_size(path) != (expected, expected):
            raise BuildError(f"{path} must be {expected}x{expected}")

    privacy_scan()
    print(f"{APPNAME} {app_version} check ok")
    return 0


def run_fnpack(fnpack: Path, stage: Path, out_dir: Path, app_version: str, suffix: str) -> Path:
    log(f"building FPK with fnpack {FNPACK_VERSION}")
    result = subprocess.run(
        [str(fnpack), "build", "--directory", str(stage)],
        cwd=str(stage),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise BuildError(f"fnpack build failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    candidates = sorted(stage.glob("*.fpk"))
    if len(candidates) != 1:
        raise BuildError(f"fnpack must produce exactly one FPK, found {len(candidates)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{APPNAME}-{app_version}-fnos-amd64"
    if suffix:
        name += f"-{suffix}"
    artifact = out_dir / f"{name}.fpk"
    shutil.move(str(candidates[0]), artifact)
    artifact.with_name(artifact.name + ".sha256").write_text(
        f"{sha256_file(artifact)}  {artifact.name}\n", encoding="utf-8"
    )
    return artifact


def verify_fpk(artifact: Path, app_version: str) -> dict[str, object]:
    if artifact.stat().st_size > MAX_FPK_SIZE:
        raise BuildError(f"FPK is unexpectedly large: {artifact.stat().st_size} bytes")
    with tarfile.open(artifact, "r:gz") as outer:
        names = outer.getnames()
        for name in names:
            if name.startswith("/") or ".." in Path(name).parts:
                raise BuildError(f"unsafe FPK member: {name}")
        manifest_data = outer.extractfile("manifest")
        if manifest_data is None:
            raise BuildError("FPK manifest is not readable")
        manifest = parse_manifest(manifest_data.read().decode("utf-8-sig"))
        if manifest.get("appname") != APPNAME:
            raise BuildError(f"FPK appname is {manifest.get('appname')!r}")
        if manifest.get("version") != app_version:
            raise BuildError(f"FPK version is {manifest.get('version')!r}")
        app_data = outer.extractfile("app.tgz")
        if app_data is None:
            raise BuildError("FPK app.tgz is not readable")
        app_bytes = app_data.read()
        if md5_file_bytes(app_bytes) != manifest.get("checksum"):
            raise BuildError("FPK checksum does not match app.tgz")
    required_outer = ["manifest", "app.tgz", "ICON.PNG", "ICON_256.PNG"]
    required_outer += [f"cmd/{name}" for name in CMD_SCRIPTS]
    required_outer += [f"config/{name}" for name in ("privilege", "resource")]
    required_outer += [f"wizard/{name}" for name in ("install", "config", "uninstall")]
    for name in required_outer:
        if name not in names:
            raise BuildError(f"FPK is missing {name}")
    with tarfile.open(fileobj=__import__("io").BytesIO(app_bytes), mode="r:gz") as inner:
        inner_names = inner.getnames()
        required_inner = ["docker/docker-compose.yaml", "ui/config", "ui/images/icon_64.png", "ui/images/icon_256.png"]
        for name in required_inner:
            if name not in inner_names:
                raise BuildError(f"app.tgz is missing {name}")
        for name in inner_names + names:
            if name.endswith((".key", ".crt", ".pem")) or name.endswith("settings.env"):
                raise BuildError(f"secret material in FPK: {name}")
            if "/.git/" in f"/{name}" or name.startswith("tests/") or "__pycache__" in name:
                raise BuildError(f"unexpected build content in FPK: {name}")
    return {
        "name": artifact.name,
        "path": str(artifact),
        "size": artifact.stat().st_size,
        "sha256": sha256_file(artifact),
        "app_tgz_md5": manifest.get("checksum"),
    }


def md5_file_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def stage_package(app_version: str, revision: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="gitlab-fpk-stage-"))
    stage = root / "stage"
    shutil.copytree(PACKAGE_DIR, stage)
    manifest_path = stage / "manifest"
    text = manifest_path.read_text(encoding="utf-8")
    text, count = re.subn(r"(?m)^version\s*=.*$", f"version               = {app_version}", text)
    if count != 1:
        raise BuildError("manifest must contain exactly one version line")
    manifest_path.write_text(text, encoding="utf-8")
    return root


def build(args: argparse.Namespace) -> int:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    app_version = (args.app_version or APP_VERSION_FILE.read_text(encoding="utf-8").strip()).strip()
    if app_version != version and not app_version.startswith(version + "."):
        raise BuildError(f"app version {app_version!r} does not match upstream {version!r}")
    suffix = args.artifact_suffix.strip()
    if suffix and not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*", suffix):
        raise BuildError(f"invalid artifact suffix: {suffix!r}")
    revision = suffix or "r0"

    provenance = json.loads(PROVENANCE_FILE.read_text(encoding="utf-8"))
    if provenance.get("image", {}).get("tag") != "19.5.3-ce.0":
        raise BuildError("provenance image tag mismatch")
    fnpack = ensure_fnpack(args.fnpack)
    stage_root = stage_package(app_version, revision)
    stage = stage_root / "stage"
    try:
        artifact = run_fnpack(fnpack, stage, args.out, app_version, suffix)
        verification = verify_fpk(artifact, app_version)
    finally:
        if not args.keep_staging:
            shutil.rmtree(stage_root, ignore_errors=True)
        else:
            log(f"staging kept at {stage_root}")
    summary = {
        "ok": True,
        "appname": APPNAME,
        "app_version": app_version,
        "upstream_version": version,
        "image": provenance["image"],
        "artifact": verification,
        "fnpack": {"version": FNPACK_VERSION, "sha256": sha256_file(fnpack)},
    }
    generated = APP_DIR / "dist" / "provenance.generated.json"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else f"built {artifact.name}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--app-version", default="")
    parser.add_argument("--artifact-suffix", default="")
    parser.add_argument("--out", type=Path, default=APP_DIR / "dist")
    parser.add_argument("--fnpack", type=Path)
    parser.add_argument("--keep-staging", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_only:
        return check_only()
    return build(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
