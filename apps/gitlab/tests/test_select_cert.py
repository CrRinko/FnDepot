from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "package" / "app" / "bin"
sys.path.insert(0, str(BIN))

import select_cert  # noqa: E402


def make_cert(directory: Path, name: str, san: str):
    key = directory / f"{name}.key"
    crt = directory / f"{name}.crt"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-nodes",
            "-days",
            "2",
            "-keyout",
            str(key),
            "-out",
            str(crt),
            "-subj",
            f"/CN={name}",
            "-addext",
            f"subjectAltName={san}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return crt, key


def entry(domain, san, crt, key, valid_to, used=False, fullchain=""):
    return {
        "domain": domain,
        "san": san,
        "certificate": str(crt),
        "fullchain": str(fullchain) if fullchain else "",
        "privateKey": str(key),
        "validFrom": 0,
        "validTo": valid_to,
        "used": used,
        "sum": "test",
        "appFlag": 0,
    }


class SelectCertificateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now_ms = int(time.time() * 1000)
        self.future = self.now_ms + 30 * 24 * 3600 * 1000
        self.past = self.now_ms - 1000

    def tearDown(self):
        self.tmp.cleanup()

    def cert(self, name, san):
        return make_cert(self.root, name, san)

    def test_exact_san_beats_used_non_matching(self):
        a_crt, a_key = self.cert("a", "DNS:a.example.com")
        b_crt, b_key = self.cert("b", "DNS:b.example.com")
        entries = [
            entry("b.example.com", ["b.example.com"], b_crt, b_key, self.future, used=True),
            entry("a.example.com", ["a.example.com"], a_crt, a_key, self.future),
        ]
        choice = select_cert.select_certificate(entries, "a.example.com", now=self.now_ms / 1000)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.domain, "a.example.com")

    def test_wildcard_matches_one_label_only(self):
        crt, key = self.cert("wild", "DNS:*.example.com")
        entries = [entry("*.example.com", ["*.example.com"], crt, key, self.future)]
        self.assertIsNotNone(
            select_cert.select_certificate(entries, "gitlab.example.com", now=self.now_ms / 1000)
        )
        self.assertIsNone(
            select_cert.select_certificate(entries, "a.b.example.com", now=self.now_ms / 1000)
        )

    def test_fullchain_is_preferred_over_leaf(self):
        crt, key = self.cert("le", "DNS:le.example.com")
        fullchain = self.root / "fullchain.crt"
        fullchain.write_bytes(crt.read_bytes())
        entries = [
            entry(
                "le.example.com",
                ["le.example.com"],
                crt,
                key,
                self.future,
                used=True,
                fullchain=fullchain,
            )
        ]
        choice = select_cert.select_certificate(
            entries, "le.example.com", now=self.now_ms / 1000
        )
        self.assertIsNotNone(choice)
        self.assertEqual(choice.cert_path, fullchain)

    def test_wildcard_only_store_is_not_used_as_external_domain(self):
        crt, key = self.cert("wild", "DNS:*.example.com")
        entries = [
            entry("*.example.com", ["*.example.com"], crt, key, self.future, used=True)
        ]
        self.assertIsNone(
            select_cert.select_certificate(entries, "", now=self.now_ms / 1000)
        )
        store = self.root / "wild.json"
        store.write_text(json.dumps(entries), encoding="utf-8")
        dest = self.root / "dest"
        state = self.root / "cert-source.json"
        result = select_cert.sync_from_store(
            store, "", dest, state, primary_ip="192.0.2.10"
        )
        self.assertEqual(result.source, "self-signed")
        self.assertEqual(result.domain, "192.0.2.10")

    def test_expired_is_skipped(self):
        crt, key = self.cert("old", "DNS:old.example.com")
        entries = [entry("old.example.com", ["old.example.com"], crt, key, self.past)]
        self.assertIsNone(
            select_cert.select_certificate(entries, "old.example.com", now=self.now_ms / 1000)
        )

    def test_empty_request_prefers_used_non_fnos(self):
        le_crt, le_key = self.cert("le", "DNS:le.example.com")
        fn_crt, fn_key = self.cert("fn", "DNS:fnOS")
        entries = [
            entry("fnOS", ["fnOS"], fn_crt, fn_key, self.future, used=True),
            entry("le.example.com", ["le.example.com"], le_crt, le_key, self.future, used=True),
        ]
        choice = select_cert.select_certificate(entries, "", now=self.now_ms / 1000)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.domain, "le.example.com")

    def test_fnos_only_returns_no_choice(self):
        fn_crt, fn_key = self.cert("fn", "DNS:fnOS")
        entries = [entry("fnOS", ["fnOS"], fn_crt, fn_key, self.future, used=True)]
        self.assertIsNone(select_cert.select_certificate(entries, "", now=self.now_ms / 1000))

    def test_install_choice_copies_and_is_idempotent(self):
        crt, key = self.cert("le", "DNS:le.example.com")
        choice = select_cert.CertChoice(
            domain="le.example.com",
            san=["le.example.com"],
            cert_path=crt,
            key_path=key,
            valid_to=self.future,
            used=True,
        )
        dest = self.root / "dest"
        state = self.root / "cert-source.json"
        first = select_cert.install_choice(choice, dest, state)
        self.assertTrue(first.changed)
        self.assertEqual(first.source, "fnos")
        self.assertTrue((dest / "gitlab.crt").is_file())
        self.assertTrue((dest / "gitlab.key").is_file())
        self.assertEqual((dest / "gitlab.key").stat().st_mode & 0o777, 0o600)
        self.assertTrue(state.is_file())
        second = select_cert.install_choice(choice, dest, state)
        self.assertFalse(second.changed)

    def test_malformed_store_keeps_existing_destination(self):
        crt, key = self.cert("le", "DNS:le.example.com")
        choice = select_cert.CertChoice(
            domain="le.example.com",
            san=["le.example.com"],
            cert_path=crt,
            key_path=key,
            valid_to=self.future,
            used=True,
        )
        dest = self.root / "dest"
        state = self.root / "cert-source.json"
        select_cert.install_choice(choice, dest, state)
        before = (dest / "gitlab.crt").read_bytes()
        store = self.root / "broken.json"
        store.write_text("{not-json", encoding="utf-8")
        result = select_cert.sync_from_store(store, "le.example.com", dest, state)
        self.assertFalse(result.changed)
        self.assertEqual((dest / "gitlab.crt").read_bytes(), before)
        self.assertIn(result.source, {"existing", "fnos"})

    def test_malformed_store_empty_request_keeps_existing_domain(self):
        crt, key = self.cert("le", "DNS:le.example.com")
        choice = select_cert.CertChoice(
            domain="le.example.com",
            san=["le.example.com"],
            cert_path=crt,
            key_path=key,
            valid_to=self.future,
            used=True,
        )
        dest = self.root / "dest"
        state = self.root / "cert-source.json"
        select_cert.install_choice(choice, dest, state)
        store = self.root / "broken.json"
        store.write_text("{not-json", encoding="utf-8")
        result = select_cert.sync_from_store(
            store, "", dest, state, primary_ip="10.0.0.9"
        )
        self.assertFalse(result.changed)
        self.assertEqual(result.domain, "le.example.com")

    def test_domain_change_without_matching_cert_generates_self_signed(self):
        crt, key = self.cert("le", "DNS:le.example.com")
        choice = select_cert.CertChoice(
            domain="le.example.com",
            san=["le.example.com"],
            cert_path=crt,
            key_path=key,
            valid_to=self.future,
            used=True,
        )
        dest = self.root / "dest"
        state = self.root / "cert-source.json"
        select_cert.install_choice(choice, dest, state)
        empty_store = self.root / "empty.json"
        empty_store.write_text("[]", encoding="utf-8")
        result = select_cert.sync_from_store(
            empty_store, "gitlab-test.example", dest, state
        )
        self.assertTrue(result.changed)
        self.assertEqual(result.source, "self-signed")
        self.assertEqual(result.domain, "gitlab-test.example")
        subject = subprocess.run(
            ["openssl", "x509", "-in", str(dest / "gitlab.crt"), "-noout", "-subject"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertIn("gitlab-test.example", subject)


if __name__ == "__main__":
    unittest.main()
