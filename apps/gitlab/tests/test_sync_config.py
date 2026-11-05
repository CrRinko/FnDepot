from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "package" / "app" / "bin"
sys.path.insert(0, str(BIN))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gitlab_config  # noqa: E402
import select_cert  # noqa: E402
import sync_config  # noqa: E402
from test_select_cert import make_cert  # noqa: E402


class SyncConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.var = self.root / "var"
        self.var.mkdir()
        self.store = self.root / "certs.json"
        self.crt, self.key = make_cert(self.root, "le", "DNS:gitlab.example.com")
        self.write_store(
            [
                {
                    "domain": "gitlab.example.com",
                    "san": ["gitlab.example.com"],
                    "certificate": str(self.crt),
                    "fullchain": "",
                    "privateKey": str(self.key),
                    "validFrom": 0,
                    "validTo": int(time.time() * 1000) + 30 * 24 * 3600 * 1000,
                    "used": True,
                    "sum": "test",
                    "appFlag": 0,
                }
            ]
        )
        self.env = {
            "GITLAB_DOMAIN": "gitlab.example.com",
            "HTTPS_PORT": "8443",
            "HTTP_PORT": "8080",
            "SSH_PORT": "2224",
            "TIME_ZONE": "Asia/Shanghai",
            "GITLAB_CERT_STORE": str(self.store),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def write_store(self, entries):
        self.store.write_text(json.dumps(entries), encoding="utf-8")

    def run_sync(self, mode="install", env=None, primary_ip="10.0.0.9"):
        return sync_config.run(
            mode,
            self.var,
            env=self.env if env is None else env,
            store=self.store,
            primary_ip=primary_ip,
        )

    def test_install_writes_settings_config_and_certificate(self):
        result = self.run_sync("install")
        self.assertTrue(result.config_changed)
        self.assertTrue(result.cert_changed)
        self.assertEqual(result.resolved_domain, "gitlab.example.com")
        self.assertEqual(result.cert_source, "fnos")
        settings = (self.var / "settings.env").read_text(encoding="utf-8")
        self.assertIn("GITLAB_DOMAIN=gitlab.example.com", settings)
        rb = (self.var / "config/gitlab.rb").read_text(encoding="utf-8")
        self.assertIn("external_url 'https://gitlab.example.com:8443'", rb)
        self.assertTrue((self.var / "config/ssl/gitlab.crt").is_file())
        self.assertTrue((self.var / "cert-source.json").is_file())

    def test_second_install_is_idempotent(self):
        self.run_sync("install")
        result = self.run_sync("install")
        self.assertFalse(result.config_changed)
        self.assertFalse(result.cert_changed)

    def test_invalid_save_does_not_write_settings(self):
        self.run_sync("install")
        before = (self.var / "settings.env").read_bytes()
        env = dict(self.env, HTTPS_PORT="443")
        with self.assertRaises(sync_config.SyncError) as ctx:
            self.run_sync("save", env=env)
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual((self.var / "settings.env").read_bytes(), before)

    def test_runtime_invalid_env_falls_back_to_previous(self):
        self.run_sync("install")
        env = dict(self.env, HTTPS_PORT="443")
        result = self.run_sync("runtime", env=env)
        self.assertEqual(result.settings.https_port, 8443)
        self.assertEqual(result.resolved_domain, "gitlab.example.com")

    def test_empty_domain_uses_active_certificate_domain(self):
        env = dict(self.env, GITLAB_DOMAIN="")
        result = self.run_sync("install", env=env)
        self.assertEqual(result.resolved_domain, "gitlab.example.com")
        settings = (self.var / "settings.env").read_text(encoding="utf-8")
        self.assertIn("GITLAB_DOMAIN=\n", settings)

    def test_domain_change_without_matching_cert_uses_self_signed(self):
        self.run_sync("install")
        env = dict(self.env, GITLAB_DOMAIN="gitlab-test.example")
        result = self.run_sync("save", env=env)
        self.assertEqual(result.resolved_domain, "gitlab-test.example")
        self.assertEqual(result.cert_source, "self-signed")
        state = json.loads((self.var / "cert-source.json").read_text(encoding="utf-8"))
        self.assertEqual(state["source"], "self-signed")
        rb = (self.var / "config/gitlab.rb").read_text(encoding="utf-8")
        self.assertIn("external_url 'https://gitlab-test.example:8443'", rb)

    def test_malformed_store_keeps_existing_certificate(self):
        self.run_sync("install")
        self.store.write_text("{broken", encoding="utf-8")
        env = dict(self.env, GITLAB_DOMAIN="")
        result = self.run_sync("runtime", env=env)
        self.assertFalse(result.cert_changed)
        self.assertEqual(result.resolved_domain, "gitlab.example.com")

    def test_runtime_without_env_or_settings_uses_defaults(self):
        result = self.run_sync("runtime", env={})
        self.assertEqual(result.resolved_domain, "gitlab.example.com")
        self.assertEqual(result.settings.https_port, 8443)
        self.assertEqual(result.settings.http_port, 8080)
        self.assertEqual(result.settings.ssh_port, 2224)


if __name__ == "__main__":
    unittest.main()
