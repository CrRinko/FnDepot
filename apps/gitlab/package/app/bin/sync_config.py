#!/usr/bin/env python3
"""Synchronize GitLab settings, certificate, and gitlab.rb for fnOS."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BIN_DIR))

import gitlab_config  # noqa: E402
import select_cert  # noqa: E402

DEFAULT_SETTINGS = gitlab_config.Settings(
    domain="", https_port=8443, http_port=8080, ssh_port=2224, timezone="Asia/Shanghai"
)
DEFAULT_STORE = Path(select_cert.DEFAULT_STORE)


class SyncError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class SyncResult:
    resolved_domain: str
    config_changed: bool
    cert_changed: bool
    cert_source: str
    settings: gitlab_config.Settings


def _int_env(env: dict[str, str], key: str, default: int) -> int:
    value = env.get(key)
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise SyncError(2, f"{key} must be an integer") from exc


def _settings_from_env(env: dict[str, str]) -> gitlab_config.Settings:
    return gitlab_config.Settings(
        domain=str(env.get("GITLAB_DOMAIN", "")).strip(),
        https_port=_int_env(env, "HTTPS_PORT", 8443),
        http_port=_int_env(env, "HTTP_PORT", 8080),
        ssh_port=_int_env(env, "SSH_PORT", 2224),
        timezone=str(env.get("TIME_ZONE", "Asia/Shanghai")).strip(),
    )


def _log(base: Path, mode: str, message: str) -> None:
    path = base / ("install.log" if mode != "runtime" else "runtime.log")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now(timezone.utc).isoformat()} [{mode}] {message}\n")
    except OSError:
        pass


def _validate_or_raise(settings, previous, check_ports: bool) -> None:
    errors = gitlab_config.validate_settings(
        settings, previous=previous, check_ports=check_ports
    )
    if errors:
        raise SyncError(2, "; ".join(errors))


def run(
    mode: str,
    base_dir: str | Path,
    env: dict[str, str] | None = None,
    store: str | Path | None = None,
    primary_ip: str | None = None,
) -> SyncResult:
    if mode not in {"install", "save", "upgrade", "runtime"}:
        raise SyncError(2, f"invalid mode: {mode}")
    env = dict(os.environ if env is None else env)
    base = Path(base_dir)
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SyncError(1, f"cannot create {base}: {exc}") from exc

    settings_path = base / "settings.env"
    previous = gitlab_config.load_settings(settings_path)
    env_has_values = any(key in env for key in ("HTTPS_PORT", "HTTP_PORT", "SSH_PORT"))
    candidate = _settings_from_env(env)
    if not env_has_values and previous is not None:
        candidate = previous

    try:
        _validate_or_raise(candidate, previous, check_ports=True)
    except SyncError:
        if mode == "runtime" and previous is not None:
            candidate = previous
            _validate_or_raise(candidate, None, check_ports=False)
        elif mode == "runtime":
            candidate = DEFAULT_SETTINGS
            _validate_or_raise(candidate, None, check_ports=False)
        else:
            raise

    store_path = Path(store or env.get("GITLAB_CERT_STORE") or DEFAULT_STORE)
    cert = select_cert.sync_from_store(
        store_path,
        candidate.domain,
        base / "config" / "ssl",
        base / "cert-source.json",
        primary_ip=primary_ip,
    )
    final = gitlab_config.Settings(
        domain=cert.domain,
        https_port=candidate.https_port,
        http_port=candidate.http_port,
        ssh_port=candidate.ssh_port,
        timezone=candidate.timezone,
    )
    _validate_or_raise(final, None, check_ports=False)
    config_changed = gitlab_config.write_if_changed(
        base / "config" / "gitlab.rb", gitlab_config.render_gitlab_rb(final)
    )
    gitlab_config.write_if_changed(settings_path, gitlab_config.settings_to_env(candidate))
    if config_changed or cert.changed:
        _log(
            base,
            mode,
            f"domain={final.domain} config_changed={int(config_changed)} "
            f"cert_changed={int(cert.changed)} source={cert.source}",
        )
    return SyncResult(
        resolved_domain=final.domain,
        config_changed=config_changed,
        cert_changed=cert.changed,
        cert_source=cert.source,
        settings=candidate,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["install", "save", "upgrade", "runtime"], default="runtime")
    parser.add_argument("--base", default=os.environ.get("TRIM_PKGVAR", ""))
    parser.add_argument("--store", default=os.environ.get("GITLAB_CERT_STORE", ""))
    parser.add_argument("--primary-ip", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.base:
        message = "TRIM_PKGVAR is not set"
        print(f"ERROR={message}", file=sys.stderr)
        _write_temp_log(message)
        return 1
    try:
        result = run(
            args.mode,
            args.base,
            env=os.environ,
            store=args.store or None,
            primary_ip=args.primary_ip or None,
        )
    except SyncError as exc:
        message = str(exc)
        print(f"ERROR={message}", file=sys.stderr)
        _write_temp_log(message)
        return exc.code
    print(f"RESOLVED_DOMAIN={result.resolved_domain}")
    print(f"CONFIG_CHANGED={1 if result.config_changed else 0}")
    print(f"CERT_CHANGED={1 if result.cert_changed else 0}")
    print(f"CERT_SOURCE={result.cert_source}")
    print(f"HTTPS_PORT={result.settings.https_port}")
    print(f"HTTP_PORT={result.settings.http_port}")
    print(f"SSH_PORT={result.settings.ssh_port}")
    print(f"TIME_ZONE={result.settings.timezone}")
    return 0


def _write_temp_log(message: str) -> None:
    path = os.environ.get("TRIM_TEMP_LOGFILE")
    if not path:
        return
    try:
        Path(path).write_text(message + "\n", encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
