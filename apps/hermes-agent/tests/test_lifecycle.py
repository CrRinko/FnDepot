import os
import subprocess
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
CMD = APP / "package/cmd"


class LifecycleScriptsTest(unittest.TestCase):
    def test_install_init_has_no_side_effects(self):
        text = (CMD / "install_init").read_text(encoding="utf-8")
        for forbidden in ("mkdir", "chown", "password", "cat >"):
            self.assertNotIn(forbidden, text)
        result = subprocess.run(["bash", str(CMD / "install_init")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

    def test_install_callback_calls_setup(self):
        text = (CMD / "install_callback").read_text(encoding="utf-8")
        self.assertIn("hermes-setup", text)
        self.assertIn("${TRIM_APPDEST}/bin/hermes-setup", text)

    def test_upgrade_init_stops_service(self):
        text = (CMD / "upgrade_init").read_text(encoding="utf-8")
        self.assertIn("main", text)
        self.assertIn("stop", text)

    def test_scripts_are_bash_valid_and_executable(self):
        for name in ("install_init", "install_callback", "upgrade_init", "upgrade_callback",
                     "uninstall_init", "uninstall_callback", "config_init", "config_callback", "main"):
            path = CMD / name
            self.assertTrue(os.access(path, os.X_OK), f"{path} is not executable")
            result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_hermes_wrapper_uses_runtime(self):
        text = (APP / "package/app/bin/hermes").read_text(encoding="utf-8")
        self.assertIn("${RUNTIME}/venv/bin/hermes", text)
        self.assertIn("HERMES_HOME", text)
