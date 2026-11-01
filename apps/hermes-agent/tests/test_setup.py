import os
import subprocess
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
SETUP = APP / "package/app/bin/hermes-setup"


class SetupScriptTest(unittest.TestCase):
    def run_setup(self, *args, extra_env=None):
        env = os.environ.copy()
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", str(SETUP), *args],
            text=True,
            capture_output=True,
            env=env,
        )

    def test_check_prints_pins_and_skips_chown_as_non_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {
                "TRIM_APPDEST": str(root / "target"),
                "TRIM_PKGHOME": str(root / "home"),
                "TRIM_PKGVAR": str(root / "var"),
                "TRIM_USERNAME": os.environ.get("USER", "tester"),
            }
            (root / "target").mkdir()
            (root / "home").mkdir()
            (root / "var").mkdir()
            result = self.run_setup("--check", extra_env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("python=3.14.9", result.stdout)
            self.assertIn("uv=0.13.5", result.stdout)
            self.assertIn("node=26.12.1", result.stdout)
            self.assertIn("chown=skip", result.stdout)

    def test_missing_pkghome_fails(self):
        result = self.run_setup("--check", extra_env={"TRIM_PKGHOME": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TRIM_PKGHOME", result.stderr)

    def test_ready_fields_are_parsed(self):
        source = SETUP.read_text(encoding="utf-8")
        for field in ("version", "commit", "web_dist_sha256", "packaging_revision"):
            self.assertIn(field, source)

    def test_mirror_fallbacks_are_defined(self):
        source = SETUP.read_text(encoding="utf-8")
        for fragment in ("ghproxy", "gh-proxy", "npmmirror.com/mirrors/node"):
            self.assertIn(fragment, source)
