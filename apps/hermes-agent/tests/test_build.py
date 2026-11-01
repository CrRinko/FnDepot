import json
import subprocess
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
BUILD = APP / "scripts/build.py"


class BuildScriptTest(unittest.TestCase):
    def test_help(self):
        result = subprocess.run(["python3", str(BUILD), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fnOS", result.stdout)

    def test_check_only(self):
        result = subprocess.run(["python3", str(BUILD), "--check-only"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0.22.5", result.stdout)

    def test_provenance_pins(self):
        data = json.loads((APP / "provenance.json").read_text())
        self.assertEqual(data["upstream"]["version"], "0.22.5")
        self.assertEqual(data["upstream"]["commit"], "bf0203a794a07aac3ff764972ab9087baa4e4f4e")
        self.assertEqual(data["runtime"]["python"], "3.14.9")
        self.assertEqual(data["runtime"]["uv"], "0.13.5")
        self.assertEqual(data["runtime"]["node"], "26.12.1")
        self.assertEqual(data["update"]["mechanism"], "external")
        self.assertEqual(data["update"]["distribution"], "fnos")
