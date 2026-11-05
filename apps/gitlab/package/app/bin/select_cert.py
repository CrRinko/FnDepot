#!/usr/bin/env python3
"""Select a certificate from the fnOS certificate store for GitLab.

The preferred certificate is one whose domain/SAN matches the configured
domain. When no domain is configured, the active (``used``) non-fnOS
certificate is preferred, then the newest non-fnOS certificate. If nothing
usable exists, a self-signed certificate is generated for the resolved
domain.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_STORE = "/usr/trim/etc/network_cert_all.conf"
CERT_NAME = "gitlab.crt"
KEY_NAME = "gitlab.key"


@dataclass
class CertChoice:
    domain: str
    san: list[str]
    cert_path: Path
    key_path: Path
    valid_to: int
    used: bool = False


@dataclass
class InstallResult:
    changed: bool
    domain: str
    sha256: str
    source: str


def _now_ms(now: float | None) -> int:
    return int((now if now is not None else datetime.now(timezone.utc).timestamp()) * 1000)


def _valid_to(entry: dict) -> int:
    try:
        return int(entry.get("validTo") or 0)
    except (TypeError, ValueError):
        return 0


def _sans(entry: dict) -> list[str]:
    value = entry.get("san")
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _matches(pattern: str, domain: str) -> int | None:
    pattern = pattern.strip().lower().rstrip(".")
    domain = domain.strip().lower().rstrip(".")
    if not pattern or not domain:
        return None
    if pattern == domain:
        return 0
    if pattern.startswith("*."):
        suffix = pattern[1:]
        if domain.endswith(suffix) and domain.count(".") == pattern.count("."):
            return 1
    return None


def _entry_rank(entry: dict, domain: str) -> int | None:
    ranks = [rank for rank in (_matches(item, domain) for item in _sans(entry)) if rank is not None]
    if ranks:
        return min(ranks)
    if _matches(str(entry.get("domain") or ""), domain) is not None:
        return 2
    return None


def select_certificate(
    entries: list[dict], requested_domain: str, now: float | None = None
) -> CertChoice | None:
    now_ms = _now_ms(now)
    usable: list[tuple[int, int, int, dict]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if _valid_to(entry) <= now_ms:
            continue
        cert = str(entry.get("certificate") or "").strip()
        fullchain = str(entry.get("fullchain") or "").strip()
        key = str(entry.get("privateKey") or "").strip()
        if not cert or not key:
            continue
        used = bool(entry.get("used"))
        if requested_domain:
            rank = _entry_rank(entry, requested_domain)
            if rank is None:
                continue
            usable.append((rank, 0 if used else 1, -_valid_to(entry), entry))
        else:
            domain = str(entry.get("domain") or "").strip()
            if not domain or domain.lower() == "fnos":
                continue
            usable.append((0, 0 if used else 1, -_valid_to(entry), entry))
    if not usable:
        return None
    usable.sort(key=lambda item: (item[0], item[1], item[2]))
    entry = usable[0][3]
    domain = str(entry.get("domain") or "").strip()
    if not domain and requested_domain:
        domain = requested_domain
    return CertChoice(
        domain=domain,
        san=_sans(entry),
        cert_path=Path(fullchain or cert),
        key_path=Path(str(entry.get("privateKey")).strip()),
        valid_to=_valid_to(entry),
        used=bool(entry.get("used")),
    )


def resolve_domain(requested_domain: str, choice: CertChoice | None, primary_ip: str) -> str:
    if requested_domain:
        return requested_domain.strip().rstrip(".")
    if choice is not None and choice.domain and choice.domain.lower() != "fnos":
        return choice.domain.strip().rstrip(".")
    return primary_ip


def get_primary_ip() -> str:
    try:
        output = subprocess.run(
            ["hostname", "-I"], check=True, capture_output=True, text=True, timeout=5
        ).stdout
        for candidate in output.split():
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if address.version == 4 and not address.is_loopback:
                return str(address)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


def load_store(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("certificate store must be a JSON array")
    return [item for item in data if isinstance(item, dict)]


def _sha256(*files: Path) -> str:
    digest = hashlib.sha256()
    for path in files:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _write_state(
    state_path: Path,
    *,
    source: str,
    domain: str,
    digest: str,
    valid_to: int,
    source_domain: str = "",
    source_cert: str = "",
    source_key: str = "",
) -> None:
    payload = {
        "source": source,
        "domain": domain,
        "source_domain": source_domain,
        "source_certificate": source_cert,
        "source_private_key": source_key,
        "valid_to": valid_to,
        "sha256": digest,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    _atomic_write(
        state_path, (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode(), 0o600
    )


def _state_domain(state_path: Path) -> str:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("domain") or "")


def _dest_valid(dest_dir: Path) -> bool:
    cert = dest_dir / CERT_NAME
    key = dest_dir / KEY_NAME
    if not cert.is_file() or not key.is_file():
        return False
    result = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-checkend", "0"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _dest_hash(dest_dir: Path) -> str:
    return _sha256(dest_dir / CERT_NAME, dest_dir / KEY_NAME)


def install_choice(choice: CertChoice, dest_dir: Path, state_path: Path) -> InstallResult:
    cert_source = choice.cert_path
    if not cert_source.is_file() or not choice.key_path.is_file():
        raise FileNotFoundError(f"certificate source is incomplete: {cert_source}")
    cert_bytes = cert_source.read_bytes()
    key_bytes = choice.key_path.read_bytes()
    digest = hashlib.sha256(cert_bytes + key_bytes).hexdigest()
    cert_dest = dest_dir / CERT_NAME
    key_dest = dest_dir / KEY_NAME
    changed = True
    if cert_dest.is_file() and key_dest.is_file():
        if cert_dest.read_bytes() == cert_bytes and key_dest.read_bytes() == key_bytes:
            changed = False
    if changed:
        _atomic_write(cert_dest, cert_bytes, 0o600)
        _atomic_write(key_dest, key_bytes, 0o600)
        _write_state(
            state_path,
            source="fnos",
            domain=choice.domain,
            digest=digest,
            valid_to=choice.valid_to,
            source_domain=choice.domain,
            source_cert=str(choice.cert_path),
            source_key=str(choice.key_path),
        )
    return InstallResult(
        changed=changed,
        domain=choice.domain,
        sha256=digest,
        source="fnos",
    )


def generate_self_signed(
    domain: str, dest_dir: Path, state_path: Path, now: float | None = None
) -> InstallResult:
    try:
        is_ip = ipaddress.ip_address(domain).version == 4
    except ValueError:
        is_ip = False
    san = f"IP:{domain}" if is_ip else f"DNS:{domain}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gitlab-selfsigned-") as tmp:
        tmp_path = Path(tmp)
        cert = tmp_path / CERT_NAME
        key = tmp_path / KEY_NAME
        result = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-sha256",
                "-nodes",
                "-days",
                "3650",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-subj",
                f"/CN={domain}",
                "-addext",
                f"subjectAltName={san}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"openssl self-signed certificate failed: {result.stderr.strip()}")
        cert_bytes = cert.read_bytes()
        key_bytes = key.read_bytes()
    digest = hashlib.sha256(cert_bytes + key_bytes).hexdigest()
    cert_dest = dest_dir / CERT_NAME
    key_dest = dest_dir / KEY_NAME
    changed = True
    if (
        cert_dest.is_file()
        and key_dest.is_file()
        and cert_dest.read_bytes() == cert_bytes
        and key_dest.read_bytes() == key_bytes
        and _state_domain(state_path) == domain
    ):
        changed = False
    if changed:
        _atomic_write(cert_dest, cert_bytes, 0o600)
        _atomic_write(key_dest, key_bytes, 0o600)
        _write_state(state_path, source="self-signed", domain=domain, digest=digest, valid_to=0)
    return InstallResult(changed=changed, domain=domain, sha256=digest, source="self-signed")


def sync_from_store(
    store_path: Path,
    requested_domain: str,
    dest_dir: Path,
    state_path: Path,
    primary_ip: str | None = None,
    now: float | None = None,
) -> InstallResult:
    try:
        entries = load_store(store_path)
    except (OSError, ValueError, json.JSONDecodeError):
        entries = []
    choice = select_certificate(entries, requested_domain, now=now)
    resolved = resolve_domain(requested_domain, choice, primary_ip or get_primary_ip())
    if not requested_domain and choice is None:
        existing_domain = _state_domain(state_path)
        if existing_domain:
            resolved = existing_domain
    if choice is not None:
        try:
            result = install_choice(choice, dest_dir, state_path)
            if not requested_domain:
                result.domain = resolved
            return result
        except OSError:
            pass
    if _dest_valid(dest_dir):
        state_domain = _state_domain(state_path)
        if state_domain == resolved or (not state_domain and not requested_domain):
            return InstallResult(
                changed=False,
                domain=resolved,
                sha256=_dest_hash(dest_dir),
                source="existing",
            )
    return generate_self_signed(resolved, dest_dir, state_path, now=now)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=os.environ.get("GITLAB_CERT_STORE", DEFAULT_STORE))
    parser.add_argument("--dest-dir", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--domain", default=os.environ.get("GITLAB_DOMAIN", ""))
    parser.add_argument("--primary-ip", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = sync_from_store(
            Path(args.store),
            args.domain.strip(),
            Path(args.dest_dir),
            Path(args.state),
            primary_ip=args.primary_ip or None,
        )
    except Exception as exc:  # noqa: BLE001 - CLI must report a clear failure
        print(f"ERROR=certificate selection failed: {exc}", file=sys.stderr)
        return 1
    print(f"RESOLVED_DOMAIN={result.domain}")
    print(f"CERT_CHANGED={1 if result.changed else 0}")
    print(f"CERT_SOURCE={result.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
