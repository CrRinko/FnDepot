#!/usr/bin/env python3
"""Build the Hermes Agent fnOS FPK.

The upstream source and web frontend are not vendored. This script downloads
the pinned source tarball, builds the official dashboard frontend with the
pinned Node runtime, verifies fnpack, assembles the FPK, and validates the
result.

Tested on Linux amd64 (Ubuntu 24.04) with Python 3.10+.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
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
SOURCE_COMMIT_FILE = APP_DIR / "SOURCE_COMMIT"
PROVENANCE_FILE = APP_DIR / "provenance.json"
CACHE_DIR = APP_DIR / ".cache"

FNPACK_VERSION = "1.2.3"
FNPACK_SHA256 = "54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93"
FNPACK_URL = f"https://static2.fnnas.com/fnpack/fnpack-{FNPACK_VERSION}-linux-amd64"
FNPACK_CACHE = (
    Path.home()
    / ".cache"
    / "fnos-hermes-agent-builder"
    / "fnpack"
    / FNPACK_VERSION
    / "linux-amd64"
    / "fnpack"
)

SOURCE_URL = "https://github.com/NousResearch/hermes-agent/archive/refs/tags/v0.22.5.tar.gz"
SOURCE_SHA256 = "a8f67e5ec14fea681acef6cc7ff1553f002bb6101fd2df22bfdd4b7eecc54eb2"
NODE_VERSION = "26.12.1"
NODE_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.xz"
NODE_SHA256 = "6170b2d474e1c626f43cff3adc118df9fe3b573258a4fc3d850c8dbc6b079bbd"

MAX_FPK_SIZE = 100 * 1024 * 1024


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


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        digest.update(b"\n")
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    log(f"downloading {url}")
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "fnos-hermes-agent-builder/1.0"}
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


def download_first(urls: list[str], destination: Path, expected_sha256: str) -> None:
    errors: list[str] = []
    for url in urls:
        try:
            download(url, destination, expected_sha256)
            return
        except Exception as exc:  # noqa: BLE001 - report the last failure
            errors.append(f"{url}: {exc}")
    raise BuildError("all download sources failed:\n" + "\n".join(errors))


def github_mirrors(url: str) -> list[str]:
    return [
        url,
        f"https://ghproxy.com/{url}",
        f"https://gh-proxy.com/{url}",
        f"https://mirror.ghproxy.com/{url}",
    ]


def node_mirrors(url: str) -> list[str]:
    mirror = url.replace("https://nodejs.org/dist/", "https://npmmirror.com/mirrors/node/")
    return [url, mirror]


def parse_manifest(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[key.strip()] = value
    return result


def parse_env(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise BuildError(f"{path} is not a PNG")
    return struct.unpack(">II", data[16:24])


def extract_single_root(tarball: Path, destination: Path) -> None:
    temporary = Path(tempfile.mkdtemp(prefix="hermes-agent-extract-"))
    try:
        with tarfile.open(tarball, "r:*") as archive:
            for member in archive.getmembers():
                name = member.name
                if name.startswith("/") or ".." in Path(name).parts:
                    raise BuildError(f"unsafe path in {tarball.name}: {name}")
            archive.extractall(temporary)
        entries = list(temporary.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise BuildError(f"{tarball.name} must contain exactly one top-level directory")
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entries[0]), destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    log("+ " + " ".join(str(part) for part in cmd))
    result = subprocess.run(
        [str(part) for part in cmd],
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise BuildError(
            f"command failed ({result.returncode}): {' '.join(str(part) for part in cmd)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def ensure_source_tarball(
    version: str, source_tarball: Path | None, expected_sha256: str
) -> Path:
    if source_tarball is not None:
        source = source_tarball.expanduser().resolve()
        if not source.is_file():
            raise BuildError(f"source tarball does not exist: {source}")
        if sha256_file(source) != expected_sha256:
            raise BuildError(f"source tarball checksum mismatch: {source}")
        return source

    cache = CACHE_DIR / "source" / f"hermes-agent-{version}.tar.gz"
    if cache.is_file() and sha256_file(cache) == expected_sha256:
        return cache
    download_first(github_mirrors(SOURCE_URL), cache, expected_sha256)
    return cache


def ensure_node() -> Path:
    node_dir = CACHE_DIR / "node" / NODE_VERSION
    node_bin = node_dir / "bin/node"
    if node_bin.is_file():
        return node_dir
    tarball = CACHE_DIR / "node" / f"node-v{NODE_VERSION}-linux-x64.tar.xz"
    if not tarball.is_file() or sha256_file(tarball) != NODE_SHA256:
        download_first(node_mirrors(NODE_URL), tarball, NODE_SHA256)
    extract_single_root(tarball, node_dir)
    if not node_bin.is_file():
        raise BuildError("Node archive has no bin/node")
    return node_dir


def build_web_dist(source_tarball: Path, version: str) -> tuple[Path, str]:
    source_dir = CACHE_DIR / "source" / f"hermes-agent-{version}"
    if not (source_dir / "pyproject.toml").is_file():
        extract_single_root(source_tarball, source_dir)

    node_dir = ensure_node()
    env = os.environ.copy()
    env["PATH"] = f"{node_dir / 'bin'}:{env.get('PATH', '')}"
    npm = node_dir / "bin/npm"
    if not npm.is_file():
        raise BuildError("Node archive has no bin/npm")

    try:
        run([str(npm), "ci", "--workspace", "web", "--no-audit", "--no-fund"], cwd=source_dir, env=env)
    except BuildError:
        log("npm ci failed; falling back to npm install")
        run([str(npm), "install", "--workspace", "web", "--no-audit", "--no-fund"], cwd=source_dir, env=env)
    run([str(npm), "run", "build", "-w", "web"], cwd=source_dir, env=env)

    web_dist = source_dir / "hermes_cli/web_dist"
    if not (web_dist / "index.html").is_file():
        raise BuildError("web build did not produce hermes_cli/web_dist/index.html")
    return web_dist, sha256_tree(web_dist)


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
    FNPACK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    download(FNPACK_URL, FNPACK_CACHE, FNPACK_SHA256)
    FNPACK_CACHE.chmod(0o755)
    return FNPACK_CACHE


def stage_package(
    version: str, commit: str, revision: str, web_dist: Path
) -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="hermes-agent-stage-"))
    stage = root / "stage"
    shutil.copytree(PACKAGE_DIR, stage)

    manifest_path = stage / "manifest"
    manifest = manifest_path.read_text(encoding="utf-8")
    manifest, count = re.subn(
        r"(?m)^version\s*=.*$", f"version               = {version}", manifest
    )
    if count != 1:
        raise BuildError("package/manifest must contain exactly one version line")
    manifest_path.write_text(manifest, encoding="utf-8")

    env_path = stage / "config/bootstrap/version.env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        f"APP_VERSION={version}\n"
        f"HERMES_VERSION={version}\n"
        f"SOURCE_COMMIT={commit}\n"
        f"PACKAGING_REVISION={revision}\n",
        encoding="utf-8",
    )

    stamp_path = stage / "app/install-stamp.json"
    if not stamp_path.is_file():
        raise BuildError("package/app/install-stamp.json is missing")
    stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
    if stamp.get("baseVersion") != version or stamp.get("commit") != commit:
        raise BuildError("install-stamp.json does not match VERSION/SOURCE_COMMIT")
    if stamp.get("updateMechanism") != "external" or stamp.get("distribution") != "fnos":
        raise BuildError("install-stamp.json must keep updateMechanism=external and distribution=fnos")

    web_destination = stage / "app/web_dist"
    if web_destination.exists():
        shutil.rmtree(web_destination)
    shutil.copytree(web_dist, web_destination)

    for path in list((stage / "cmd").iterdir()) + list((stage / "app/bin").iterdir()):
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o111)

    return root, stage


def run_fnpack(fnpack: Path, stage: Path, out_dir: Path, version: str, suffix: str) -> Path:
    log(f"building FPK with fnpack {FNPACK_VERSION}")
    result = subprocess.run(
        [str(fnpack), "build", "--directory", str(stage)],
        cwd=str(stage),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise BuildError(
            "fnpack build failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    candidates = sorted(stage.glob("*.fpk"))
    if len(candidates) != 1:
        raise BuildError(f"fnpack must produce exactly one FPK, found {len(candidates)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"hermes-agent-{version}-fnos-amd64"
    if suffix:
        name += f"-{suffix}"
    artifact = out_dir / f"{name}.fpk"
    shutil.move(str(candidates[0]), artifact)
    digest = sha256_file(artifact)
    artifact.with_name(artifact.name + ".sha256").write_text(
        f"{digest}  {artifact.name}\n", encoding="utf-8"
    )
    return artifact


def verify_fpk(artifact: Path, version: str) -> dict[str, object]:
    with tarfile.open(artifact, "r:gz") as outer:
        names = outer.getnames()
        for name in names:
            if name.startswith("/") or ".." in Path(name).parts:
                raise BuildError(f"unsafe FPK member: {name}")
        manifest_member = outer.getmember("manifest")
        manifest_stream = outer.extractfile(manifest_member)
        if manifest_stream is None:
            raise BuildError("FPK manifest is not readable")
        manifest = parse_manifest(manifest_stream.read().decode("utf-8-sig"))
        if manifest.get("appname") != "hermes-agent":
            raise BuildError(f"manifest appname is {manifest.get('appname')!r}")
        if manifest.get("version") != version:
            raise BuildError(f"manifest version is {manifest.get('version')!r}")
        if manifest.get("platform") != "x86":
            raise BuildError(f"manifest platform is {manifest.get('platform')!r}")
        if manifest.get("service_port") != "49375":
            raise BuildError(f"manifest service_port is {manifest.get('service_port')!r}")
        checksum = manifest.get("checksum")
        if not checksum:
            raise BuildError("manifest has no app.tgz checksum")

        app_member = outer.getmember("app.tgz")
        app_stream = outer.extractfile(app_member)
        if app_stream is None:
            raise BuildError("app.tgz is not readable")
        app_bytes = app_stream.read()
        actual_md5 = hashlib.md5(app_bytes).hexdigest()
        if actual_md5 != checksum:
            raise BuildError(f"app.tgz checksum mismatch: got {actual_md5}, expected {checksum}")

        with tarfile.open(fileobj=io.BytesIO(app_bytes), mode="r:gz") as inner:
            inner_names = set(inner.getnames())
            for required in ("web_dist/index.html", "install-stamp.json", "bin/hermes-setup"):
                if required not in inner_names:
                    raise BuildError(f"app.tgz is missing {required}")

        for icon, expected in (("ICON.PNG", 64), ("ICON_256.PNG", 256)):
            member = outer.extractfile(icon)
            if member is None:
                raise BuildError(f"missing {icon}")
            data = member.read(24)
            width, height = struct.unpack(">II", data[16:24])
            if (width, height) != (expected, expected):
                raise BuildError(f"{icon} must be {expected}x{expected}, got {width}x{height}")

    size = artifact.stat().st_size
    if size >= MAX_FPK_SIZE:
        raise BuildError(f"FPK is too large for a GitHub Release asset: {size} bytes")
    return {
        "name": artifact.name,
        "path": str(artifact),
        "size": size,
        "sha256": sha256_file(artifact),
        "app_tgz_md5": actual_md5,
    }


def privacy_scan() -> None:
    phone_re = re.compile(r"(?<!\d)\d{11,}(?!\d)")
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    private_ip_re = re.compile(
        r"\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    )
    allowed_emails = {"9782921+CrRinko@users.noreply.github.com"}
    excluded = {".cache", "dist", "__pycache__", "web_dist"}
    for path in APP_DIR.rglob("*"):
        if not path.is_file():
            continue
        if any(part in excluded for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in phone_re.findall(line):
                raise BuildError(f"privacy scan: phone-like number in {path}:{lineno}: {match}")
            for match in email_re.findall(line):
                if match not in allowed_emails:
                    raise BuildError(f"privacy scan: email in {path}:{lineno}: {match}")
            for match in private_ip_re.findall(line):
                raise BuildError(f"privacy scan: private IP in {path}:{lineno}: {match}")


def check_only() -> int:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    commit = SOURCE_COMMIT_FILE.read_text(encoding="utf-8").strip()
    provenance = json.loads(PROVENANCE_FILE.read_text(encoding="utf-8"))
    manifest = parse_manifest((PACKAGE_DIR / "manifest").read_text(encoding="utf-8"))
    version_env = parse_env(
        (PACKAGE_DIR / "config/bootstrap/version.env").read_text(encoding="utf-8")
    )
    stamp = json.loads(
        (PACKAGE_DIR / "app/install-stamp.json").read_text(encoding="utf-8")
    )

    checks = {
        "VERSION": version,
        "manifest version": manifest.get("version"),
        "version.env APP_VERSION": version_env.get("APP_VERSION"),
        "install-stamp baseVersion": stamp.get("baseVersion"),
        "provenance version": provenance.get("version"),
    }
    for label, value in checks.items():
        if value != version:
            raise BuildError(f"{label} is {value!r}, expected {version!r}")
    commit_checks = {
        "SOURCE_COMMIT": commit,
        "install-stamp commit": stamp.get("commit"),
        "provenance commit": provenance.get("upstream", {}).get("commit"),
    }
    for label, value in commit_checks.items():
        if value != commit:
            raise BuildError(f"{label} is {value!r}, expected {commit!r}")
    if manifest.get("appname") != "hermes-agent" or manifest.get("platform") != "x86":
        raise BuildError("manifest appname/platform mismatch")
    if manifest.get("service_port") != "49375":
        raise BuildError("manifest service_port must be 49375")
    if stamp.get("updateMechanism") != "external" or stamp.get("distribution") != "fnos":
        raise BuildError("install-stamp update mechanism mismatch")

    icons = {
        APP_DIR / "icon-256.png": 256,
        APP_DIR / "icon-64.png": 64,
        PACKAGE_DIR / "ICON_256.PNG": 256,
        PACKAGE_DIR / "ICON.PNG": 64,
        PACKAGE_DIR / "app/ui/images/icon_256.png": 256,
        PACKAGE_DIR / "app/ui/images/icon_64.png": 64,
    }
    for path, expected in icons.items():
        if png_size(path) != (expected, expected):
            raise BuildError(f"{path} must be {expected}x{expected}")

    scripts = list((PACKAGE_DIR / "cmd").iterdir()) + list((PACKAGE_DIR / "app/bin").iterdir())
    for path in scripts:
        if not path.is_file() or not os.access(path, os.X_OK):
            raise BuildError(f"script is missing or not executable: {path}")

    privacy_scan()
    print(f"hermes-agent {version} source={provenance['upstream']['source_sha256'][:8]}")
    return 0


def parse_args() -> argparse.Namespace:
    default_version = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.is_file() else ""
    default_commit = (
        SOURCE_COMMIT_FILE.read_text(encoding="utf-8").strip()
        if SOURCE_COMMIT_FILE.is_file()
        else ""
    )
    parser = argparse.ArgumentParser(
        description="Build the Hermes Agent fnOS FPK from the pinned upstream source."
    )
    parser.add_argument("--version", default=default_version, help="upstream version (default: VERSION)")
    parser.add_argument("--source-commit", default=default_commit, help="upstream commit")
    parser.add_argument("--source-tarball", type=Path, help="local upstream source tarball")
    parser.add_argument("--expected-sha256", default=SOURCE_SHA256, help="expected source SHA-256")
    parser.add_argument("--web-dist", type=Path, help="prebuilt hermes_cli/web_dist directory")
    parser.add_argument("--fnpack", type=Path, help="explicit fnpack binary")
    parser.add_argument("--out", type=Path, default=APP_DIR / "dist", help="output directory")
    parser.add_argument("--artifact-suffix", default="", help="artifact suffix, for example r1")
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    parser.add_argument("--check-only", action="store_true", help="validate local metadata only")
    parser.add_argument("--keep-staging", action="store_true", help="keep the temporary staging directory")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    version = args.version.strip()
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+_-]*", version):
        raise BuildError(f"invalid version: {version!r}")
    suffix = args.artifact_suffix.strip()
    if suffix and not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._-]*", suffix):
        raise BuildError(f"invalid artifact suffix: {suffix!r}")

    if args.check_only:
        return check_only()

    provenance = json.loads(PROVENANCE_FILE.read_text(encoding="utf-8"))
    source_sha = args.expected_sha256
    source_tarball = ensure_source_tarball(version, args.source_tarball, source_sha)
    source_digest = sha256_file(source_tarball)

    if args.web_dist is not None:
        web_dist = args.web_dist.expanduser().resolve()
        if not (web_dist / "index.html").is_file():
            raise BuildError(f"web_dist has no index.html: {web_dist}")
        web_digest = sha256_tree(web_dist)
    else:
        web_dist, web_digest = build_web_dist(source_tarball, version)

    fnpack = ensure_fnpack(args.fnpack)
    revision = suffix or "r0"
    stage_root, stage = stage_package(version, args.source_commit, revision, web_dist)
    try:
        artifact = run_fnpack(fnpack, stage, args.out, version, suffix)
        verification = verify_fpk(artifact, version)
    finally:
        if not args.keep_staging:
            shutil.rmtree(stage_root, ignore_errors=True)
        else:
            log(f"staging kept at {stage_root}")

    summary = {
        "ok": True,
        "version": version,
        "artifact": verification,
        "source": {
            "url": provenance["upstream"]["source_url"],
            "sha256": source_digest,
        },
        "web_dist": {"sha256": web_digest},
        "fnpack": {"version": FNPACK_VERSION, "sha256": sha256_file(fnpack)},
        "update": provenance.get("update"),
    }
    generated = APP_DIR / "dist" / "provenance.generated.json"
    generated.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"built {artifact.name} ({verification['size']} bytes, "
            f"sha256 {verification['sha256']})"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
