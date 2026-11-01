import json
import struct
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a PNG")
    return struct.unpack(">II", data[16:24])


class PackageMetadataTest(unittest.TestCase):
    def test_identity_files(self):
        self.assertEqual((APP / "VERSION").read_text().strip(), "0.22.5")
        self.assertEqual(
            (APP / "SOURCE_COMMIT").read_text().strip(),
            "bf0203a794a07aac3ff764972ab9087baa4e4f4e",
        )

    def test_manifest_identity(self):
        text = (APP / "package/manifest").read_text(encoding="utf-8")
        for expected in [
            "appname               = hermes-agent",
            "version               = 0.22.5",
            "platform              = x86",
            "service_port          = 49375",
            "maintainer            = CrRinko",
            "distributor           = CrRinko",
            "desktop_applaunchname = hermes-agent.main",
        ]:
            self.assertIn(expected, text)

    def test_icons(self):
        self.assertEqual(png_size(APP / "icon-256.png"), (256, 256))
        self.assertEqual(png_size(APP / "icon-64.png"), (64, 64))
        self.assertEqual(png_size(APP / "package/ICON_256.PNG"), (256, 256))
        self.assertEqual(png_size(APP / "package/ICON.PNG"), (64, 64))
        self.assertEqual(png_size(APP / "package/app/ui/images/icon_256.png"), (256, 256))
        self.assertEqual(png_size(APP / "package/app/ui/images/icon_64.png"), (64, 64))

    def test_install_stamp(self):
        stamp = json.loads((APP / "package/app/install-stamp.json").read_text())
        self.assertEqual(stamp["baseVersion"], "0.22.5")
        self.assertEqual(stamp["commit"], "bf0203a794a07aac3ff764972ab9087baa4e4f4e")
        self.assertEqual(stamp["updateMechanism"], "external")
        self.assertEqual(stamp["distribution"], "fnos")
        self.assertEqual(stamp["displayVersion"], "0.22.5")
