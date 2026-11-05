from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "package" / "app" / "bin"
sys.path.insert(0, str(BIN))

import gitlab_config  # noqa: E402


class GitlabConfigTests(unittest.TestCase):
    def settings(self, **overrides):
        values = {
            "domain": "gitlab.example.com",
            "https_port": 8443,
            "http_port": 8080,
            "ssh_port": 2224,
            "timezone": "Asia/Shanghai",
        }
        values.update(overrides)
        return gitlab_config.Settings(**values)

    def test_render_contains_required_keys(self):
        text = gitlab_config.render_gitlab_rb(self.settings())
        self.assertIn("external_url 'https://gitlab.example.com:8443'", text)
        self.assertIn("gitlab_rails['nginx']['listen_port'] = 8443", text)
        self.assertIn("gitlab_rails['nginx']['listen_https'] = true", text)
        self.assertIn("ssl_certificate'] = \"/etc/gitlab/ssl/gitlab.crt\"", text)
        self.assertIn("ssl_certificate_key'] = \"/etc/gitlab/ssl/gitlab.key\"", text)
        self.assertIn("redirect_http_to_https'] = true", text)
        self.assertIn("redirect_http_to_https_port'] = 80", text)
        self.assertIn("gitlab_rails['gitlab_shell_ssh_port'] = 2224", text)
        self.assertIn("gitlab_rails['time_zone'] = 'Asia/Shanghai'", text)
        self.assertIn("letsencrypt['enable'] = false", text)
        self.assertIn("puma['worker_processes'] = 2", text)
        self.assertIn("sidekiq['concurrency'] = 6", text)
        self.assertIn("prometheus_monitoring['enable'] = false", text)
        self.assertIn("gitlab_kas['enable'] = false", text)
        self.assertIn('postgresql[\'shared_buffers\'] = "512MB"', text)
        self.assertIn('redis[\'maxmemory\'] = "512mb"', text)

    def test_rejects_scheme_slash_and_fnos_domain(self):
        for domain in (
            "https://gitlab.example.com",
            "gitlab.example.com/path",
            "../evil",
            "has space",
            "fnOS",
            "",
        ):
            errors = gitlab_config.validate_settings(self.settings(domain=domain))
            if domain == "":
                self.assertEqual(errors, [])
            else:
                self.assertTrue(errors, domain)

    def test_accepts_ipv4(self):
        self.assertEqual(
            gitlab_config.validate_settings(self.settings(domain="192.0.2.10")), []
        )

    def test_rejects_reserved_ports(self):
        for field in ("https_port", "http_port", "ssh_port"):
            errors = gitlab_config.validate_settings(
                self.settings(**{field: 443}), check_ports=False
            )
            self.assertTrue(errors, field)

    def test_rejects_duplicate_ports(self):
        errors = gitlab_config.validate_settings(
            self.settings(https_port=8443, http_port=8443), check_ports=False
        )
        self.assertTrue(any("重复" in error or "duplicate" in error for error in errors), errors)

    def test_rejects_port_in_use(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        try:
            errors = gitlab_config.validate_settings(
                self.settings(https_port=port), check_ports=True
            )
            self.assertTrue(any(str(port) in error for error in errors), errors)
        finally:
            sock.close()

    def test_same_port_as_previous_is_allowed(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        try:
            previous = self.settings(https_port=port)
            errors = gitlab_config.validate_settings(
                self.settings(https_port=port), previous=previous, check_ports=True
            )
            self.assertEqual(errors, [])
        finally:
            sock.close()

    def test_write_if_changed_returns_change_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gitlab.rb"
            text = gitlab_config.render_gitlab_rb(self.settings())
            self.assertTrue(gitlab_config.write_if_changed(path, text))
            self.assertFalse(gitlab_config.write_if_changed(path, text))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_timezone_rejects_quotes_and_newlines(self):
        for timezone in ("Asia/Shanghai'", "Asia/Shanghai\nx", ""):
            errors = gitlab_config.validate_settings(
                self.settings(timezone=timezone), check_ports=False
            )
            self.assertTrue(errors, timezone)

    def test_load_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.env"
            path.write_text(
                "GITLAB_DOMAIN=gitlab.example.com\nHTTPS_PORT=8443\nHTTP_PORT=8080\n"
                "SSH_PORT=2224\nTIME_ZONE=Asia/Shanghai\n",
                encoding="utf-8",
            )
            loaded = gitlab_config.load_settings(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.domain, "gitlab.example.com")
            self.assertEqual(loaded.https_port, 8443)


if __name__ == "__main__":
    unittest.main()
