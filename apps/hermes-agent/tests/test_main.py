import os
import socket
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
MAIN = APP / "package/cmd/main"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class MainLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.var = root / "var"
        self.etc = root / "etc"
        self.target = root / "target"
        for path in (self.home, self.var, self.etc, self.target):
            path.mkdir(parents=True)
        self.port = free_port()
        self.env = os.environ.copy()
        self.env.update({
            "TRIM_PKGHOME": str(self.home),
            "TRIM_PKGVAR": str(self.var),
            "TRIM_PKGETC": str(self.etc),
            "TRIM_APPDEST": str(self.target),
            "TRIM_SERVICE_PORT": str(self.port),
            "TRIM_USERNAME": os.environ.get("USER", "tester"),
            "PATH": os.environ.get("PATH", ""),
        })
        self.fixture = root / "runtime-fixture"
        self._install_stub_runtime(self.fixture)
        self._copy_stub_runtime()

    def _copy_stub_runtime(self):
        import shutil
        target = self.home / "runtime"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(self.fixture, target)

    def tearDown(self):
        subprocess.run(["bash", str(MAIN), "stop"], env=self.env, capture_output=True)
        self.tmp.cleanup()

    def _install_stub_runtime(self, runtime):
        bin_dir = runtime / "venv/bin"
        bin_dir.mkdir(parents=True)
        (runtime / ".ready").write_text(
            "version=0.22.5\ncommit=test\nweb_dist_sha256=test\npackaging_revision=r0\n"
        )
        stub_server = bin_dir / "stub_server.py"
        stub_server.write_text(
            "import http.server, sys\n"
            "args = sys.argv[1:]\n"
            "port = int(args[args.index('--port') + 1])\n"
            "http.server.HTTPServer(('127.0.0.1', port), http.server.SimpleHTTPRequestHandler).serve_forever()\n"
        )
        hermes = bin_dir / "hermes"
        hermes.write_text(
            "#!/bin/sh\n"
            "exec python3 \"$(dirname \"$0\")/stub_server.py\" \"$@\"\n"
        )
        hermes.chmod(hermes.stat().st_mode | stat.S_IXUSR)
        python = bin_dir / "python"
        python.write_text("#!/bin/sh\nexit 0\n")
        python.chmod(python.stat().st_mode | stat.S_IXUSR)

    def run_main(self, action):
        return subprocess.run(["bash", str(MAIN), action], env=self.env, text=True, capture_output=True)

    def test_start_status_stop(self):
        start = self.run_main("start")
        self.assertEqual(start.returncode, 0, start.stderr)
        self.assertTrue((self.var / "dashboard.pid").is_file())
        password = (self.etc / "password").read_text().strip()
        self.assertGreaterEqual(len(password), 20)
        self.assertEqual(stat.S_IMODE((self.etc / "password").stat().st_mode), 0o600)
        status = self.run_main("status")
        self.assertEqual(status.returncode, 0, status.stderr)
        stop = self.run_main("stop")
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertFalse((self.var / "dashboard.pid").exists())

    def test_port_conflict_fails(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", self.port))
            s.listen(1)
            result = self.run_main("start")
        self.assertNotEqual(result.returncode, 0)
        log = (self.var / "dashboard.log").read_text()
        self.assertIn("already in use", log)

    def test_start_repairs_missing_runtime(self):
        import shutil
        shutil.rmtree(self.home / "runtime")
        setup = self.target / "bin/hermes-setup"
        setup.parent.mkdir(parents=True)
        setup.write_text(
            "#!/bin/sh\n"
            "cp -a \"$RUNTIME_FIXTURE\" \"$TRIM_PKGHOME/runtime\"\n"
        )
        setup.chmod(setup.stat().st_mode | stat.S_IXUSR)
        self.env["RUNTIME_FIXTURE"] = str(self.fixture)
        result = self.run_main("start")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "runtime/venv/bin/hermes").exists())
