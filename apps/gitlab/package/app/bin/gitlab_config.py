#!/usr/bin/env python3
"""Validate GitLab settings and render the omnibus gitlab.rb file."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import socket
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

RESERVED_PORTS = {22, 80, 443}
LABEL_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$")
TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+\-/]+$")
DOMAIN_REJECTION = "domain must be a hostname or IPv4 address without scheme, port, or path"


@dataclass
class Settings:
    domain: str
    https_port: int
    http_port: int
    ssh_port: int
    timezone: str


def _valid_domain(domain: str) -> bool:
    if not domain or len(domain) > 253:
        return False
    if domain.lower() == "fnos":
        return False
    try:
        if ipaddress.ip_address(domain).version == 4:
            return True
    except ValueError:
        pass
    if any(char in domain for char in ("/", "\\", ":", " ", "\t", "\n", "'", '"')):
        return False
    if ".." in domain or domain.startswith(".") or domain.endswith("."):
        return False
    labels = domain.split(".")
    if len(labels) < 1:
        return False
    return all(1 <= len(label) <= 63 and LABEL_RE.match(label) for label in labels)


def _port_in_use(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def validate_settings(
    settings: Settings, previous: Settings | None = None, check_ports: bool = True
) -> list[str]:
    errors: list[str] = []
    if settings.domain and not _valid_domain(settings.domain):
        errors.append(f"invalid domain: {settings.domain!r}; {DOMAIN_REJECTION}")
    ports = {
        "HTTPS_PORT": settings.https_port,
        "HTTP_PORT": settings.http_port,
        "SSH_PORT": settings.ssh_port,
    }
    for name, port in ports.items():
        if not isinstance(port, int) or not 1 <= port <= 65535:
            errors.append(f"{name} must be an integer between 1 and 65535")
        elif port in RESERVED_PORTS:
            errors.append(f"{name} cannot use reserved fnOS port {port}")
    values = [settings.https_port, settings.http_port, settings.ssh_port]
    if len(set(values)) != len(values):
        errors.append("duplicate port: HTTPS_PORT, HTTP_PORT, and SSH_PORT must differ")
    if check_ports and not errors:
        previous_ports = (
            {
                "HTTPS_PORT": previous.https_port,
                "HTTP_PORT": previous.http_port,
                "SSH_PORT": previous.ssh_port,
            }
            if previous is not None
            else {}
        )
        for name, port in ports.items():
            if previous_ports.get(name) == port:
                continue
            if _port_in_use(port):
                errors.append(f"{name}={port} is already in use")
    if not settings.timezone or not TIMEZONE_RE.match(settings.timezone):
        errors.append("TIME_ZONE contains invalid characters")
    return errors


def render_gitlab_rb(settings: Settings) -> str:
    return f"""# Managed by the FnDepot GitLab application. Do not edit by hand.
external_url 'https://{settings.domain}:{settings.https_port}'
gitlab_rails['nginx']['listen_port'] = {settings.https_port}
gitlab_rails['nginx']['listen_https'] = true
gitlab_rails['nginx']['ssl_certificate'] = "/etc/gitlab/ssl/gitlab.crt"
gitlab_rails['nginx']['ssl_certificate_key'] = "/etc/gitlab/ssl/gitlab.key"
gitlab_rails['nginx']['redirect_http_to_https'] = true
gitlab_rails['nginx']['redirect_http_to_https_port'] = 80
gitlab_rails['gitlab_shell_ssh_port'] = {settings.ssh_port}
gitlab_rails['time_zone'] = '{settings.timezone}'
letsencrypt['enable'] = false
puma['worker_processes'] = 2
sidekiq['concurrency'] = 6
prometheus_monitoring['enable'] = false
gitlab_kas['enable'] = false
postgresql['shared_buffers'] = "512MB"
redis['maxmemory'] = "512mb"
"""


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        path.chmod(0o600)
        return False
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return True


def load_settings(path: Path) -> Settings | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    try:
        return Settings(
            domain=values.get("GITLAB_DOMAIN", ""),
            https_port=int(values.get("HTTPS_PORT", "8443")),
            http_port=int(values.get("HTTP_PORT", "8080")),
            ssh_port=int(values.get("SSH_PORT", "2224")),
            timezone=values.get("TIME_ZONE", "Asia/Shanghai"),
        )
    except (TypeError, ValueError):
        return None


def settings_to_env(settings: Settings) -> str:
    return (
        f"GITLAB_DOMAIN={settings.domain}\n"
        f"HTTPS_PORT={settings.https_port}\n"
        f"HTTP_PORT={settings.http_port}\n"
        f"SSH_PORT={settings.ssh_port}\n"
        f"TIME_ZONE={settings.timezone}\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", default=os.environ.get("GITLAB_DOMAIN", ""))
    parser.add_argument("--https-port", type=int, default=int(os.environ.get("HTTPS_PORT", "8443")))
    parser.add_argument("--http-port", type=int, default=int(os.environ.get("HTTP_PORT", "8080")))
    parser.add_argument("--ssh-port", type=int, default=int(os.environ.get("SSH_PORT", "2224")))
    parser.add_argument("--time-zone", default=os.environ.get("TIME_ZONE", "Asia/Shanghai"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--previous", default="")
    parser.add_argument("--skip-port-check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = Settings(
        domain=args.domain.strip(),
        https_port=args.https_port,
        http_port=args.http_port,
        ssh_port=args.ssh_port,
        timezone=args.time_zone.strip(),
    )
    previous = load_settings(Path(args.previous)) if args.previous else None
    errors = validate_settings(
        settings, previous=previous, check_ports=not args.skip_port_check
    )
    if errors:
        for error in errors:
            print(f"ERROR={error}", file=sys.stderr)
        return 2
    changed = write_if_changed(Path(args.output), render_gitlab_rb(settings))
    print(f"CONFIG_CHANGED={1 if changed else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
