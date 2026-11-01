# Hermes Agent fnOS 应用实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `CrRinko/FnDepot` 中新增 `hermes-agent` 应用，安装上游 Hermes Agent v0.22.5，并通过 fnOS 应用中心直接打开官方 `hermes dashboard`。

**Architecture:** FPK 只包含 fnOS 生命周期脚本、预构建的 `web_dist`、图标和版本元数据。安装时由 `hermes-setup` 下载并校验 Hermes 源码、Python 3.14.9、uv、Node、ripgrep，创建 venv，执行 `uv sync --extra all --locked`。首次启动生成随机密码，写入 `config.yaml` 的 `dashboard.basic_auth`，启动 `hermes dashboard --host 0.0.0.0 --port 49375 --skip-build`。

**Tech Stack:** Bash、Python 3.10+（构建脚本）、Python 3.14.9（运行时）、uv 0.13.5、Node 26.12.1（仅构建前端）、fnpack 1.2.3、GitHub CLI。

**Spec:** `docs/superpowers/specs/2026-11-01-hermes-agent-fnos-package-design.md`

## Global Constraints

- `appname = hermes-agent`，`version = 0.22.5`，`platform = x86`，`service_port = 49375`。
- 上游 commit：`bf0203a794a07aac3ff764972ab9087baa4e4f4e`；源码 tarball SHA-256：`a8f67e5ec14fea681acef6cc7ff1553f002bb6101fd2df22bfdd4b7eecc54eb2`。
- Python `3.14.9+20261021` linux-x64 SHA-256：`dfa4c5a40c47f338f41658017be550c72247c391e6bfb1fa4da03ebc8451abdf`。
- uv `0.13.5` linux-x64 SHA-256：`f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f`。
- Node `26.12.1` linux-x64 SHA-256：`6170b2d474e1c626f43cff3adc118df9fe3b573258a4fc3d850c8dbc6b079bbd`。
- ripgrep `15.2.0` linux-x64 SHA-256：`33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c`。
- fnpack `1.2.3` SHA-256：`54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93`。
- FPK 必须小于 100 MB；不提交 `.fpk`、源码 tarball、`node_modules`、`web_dist`、`dist/`、`.cache/`。
- 提交作者固定为 `CrRinko <9782921+CrRinko@users.noreply.github.com>`；不添加 co-author。
- 新增文件不得包含真实手机号、邮箱、即时通讯群、NAS 内网 IP、主机名、卷 ID、token、API key、个人 handle。
- 上游 Hermes Agent 为 MIT；本仓库新增打包代码为 MIT；不复制社区 GPL 包代码。
- Dashboard 认证是“用户名 + 密码登录页 + 签名 Cookie”，不是 HTTP Basic；`--insecure` 不能绕过。
- **内置更新必须禁用**：`install-stamp.json` 使用 `updateMechanism=external` + `distribution=fnos`；`hermes update` / dashboard 更新动作必须拒绝，升级只走 FnDepot + fnOS 应用中心。
- `cmd/install_init` 必须无副作用：不创建目录、不 chown、不写密码。
- `cmd/install_callback` / `cmd/upgrade_callback` 同时兼容 root 和包用户；非 root 时不得执行 `chown`。
- 数据权威目录是 `${TRIM_PKGHOME}/data`；运行时目录是 `${TRIM_PKGHOME}/runtime`；卸载不主动删除 `data/`。

## Review Focus

1. **非回环 dashboard 认证**：未登录访问 `/` 必须到登录页或被拒绝；错误密码返回 401；正确密码拿到会话 Cookie 后能打开 dashboard。测试放在 Task 7。
2. **安装中断后恢复**：`install_callback` 未完成时，`cmd/main start` 必须能补装并启动，而不是留下半成品。测试放在 Task 3 和 Task 7。
3. **端口冲突**：49375 已被占用时，`main start` 必须失败并写清晰日志，不能杀掉占用者。测试放在 Task 3。
4. **升级/重装保留数据**：重复运行 `hermes-setup` 不得删除 `${TRIM_PKGHOME}/data` 下的 config、.env、sessions、skills。测试放在 Task 7。
5. **打包修订 rN 更新前端**：上游版本不变但 `web_dist` 变化时，`.ready` 的 hash 比较必须触发前端替换，而不是整包跳过。测试放在 Task 2 和 Task 7。
6. **内置更新必须被拒绝**：`hermes update --check` 必须退出 2，dashboard 更新动作必须返回拒绝信息；不能出现应用内升级覆盖 FPK 运行时。测试放在 Task 7。

---

### Task 1: 应用身份、图标与 fnOS 骨架

**Files:**
- Create: `apps/hermes-agent/VERSION`
- Create: `apps/hermes-agent/SOURCE_COMMIT`
- Create: `apps/hermes-agent/package/manifest`
- Create: `apps/hermes-agent/package/config/privilege`
- Create: `apps/hermes-agent/package/config/resource`
- Create: `apps/hermes-agent/package/config/bootstrap/version.env`
- Create: `apps/hermes-agent/package/app/install-stamp.json`
- Create: `apps/hermes-agent/package/app/ui/config`
- Create: `apps/hermes-agent/package/ICON.PNG`
- Create: `apps/hermes-agent/package/ICON_256.PNG`
- Create: `apps/hermes-agent/package/app/ui/images/icon_256.png`
- Create: `apps/hermes-agent/package/app/ui/images/icon_64.png`
- Create: `apps/hermes-agent/icon-256.png`
- Create: `apps/hermes-agent/icon-64.png`
- Create: `apps/hermes-agent/tests/test_package.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: 无。
- Produces: 固定的应用身份、图标尺寸、`install-stamp.json` 字段；后续任务的测试会读取这些文件。

- [ ] **Step 1: 写失败的元数据测试**

创建 `apps/hermes-agent/tests/test_package.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest apps.hermes-agent.tests.test_package -v`（如果模块路径不可用，先运行 `python3 -m unittest discover -s apps/hermes-agent/tests -v`）
Expected: FAIL，提示 `VERSION` 或 `manifest` 不存在。

- [ ] **Step 3: 创建身份与元数据文件**

`apps/hermes-agent/VERSION`：

```text
0.22.5
```

`apps/hermes-agent/SOURCE_COMMIT`：

```text
bf0203a794a07aac3ff764972ab9087baa4e4f4e
```

`apps/hermes-agent/package/manifest`：

```ini
appname               = hermes-agent
version               = 0.22.5
display_name          = Hermes Agent
desc                  = "Hermes Agent 官方 AI Agent，提供官方 Web Dashboard。首次启动后用户名 hermes，密码随机生成。SSH 登录 NAS 后以 root 权限执行 sudo cat /var/apps/hermes-agent/etc/password 获取密码。仅支持 x86 设备。"
platform              = x86
source                = thirdparty
maintainer            = CrRinko
maintainer_url        = https://github.com/CrRinko
distributor           = CrRinko
distributor_url       = https://github.com/CrRinko
desktop_uidir         = ui
desktop_applaunchname = hermes-agent.main
ctl_stop              = true
service_port          = 49375
checkport             = true
```

`apps/hermes-agent/package/config/privilege`：

```json
{
  "defaults": {
    "run-as": "package"
  },
  "username": "hermes-agent",
  "groupname": "hermes-agent"
}
```

`apps/hermes-agent/package/config/resource`：

```json
{
  "data-share": {
    "shares": [
      {
        "name": "hermes-agent"
      }
    ]
  },
  "usr-local-linker": {
    "bin": [
      "bin/hermes"
    ]
  }
}
```

`apps/hermes-agent/package/config/bootstrap/version.env`：

```text
APP_VERSION=0.22.5
HERMES_VERSION=0.22.5
SOURCE_COMMIT=bf0203a794a07aac3ff764972ab9087baa4e4f4e
PACKAGING_REVISION=r0
```

`apps/hermes-agent/package/app/install-stamp.json`：

```json
{
  "schemaVersion": 2,
  "commit": "bf0203a794a07aac3ff764972ab9087baa4e4f4e",
  "commitDate": 1761187425,
  "branch": "v0.22.5",
  "builtAt": "2026-11-01T00:00:00+00:00",
  "dirty": false,
  "source": "fndepot",
  "distribution": "fnos",
  "updateMechanism": "external",
  "baseVersion": "0.22.5",
  "displayVersion": "0.22.5",
  "distance": 0,
  "payload": "bootstrap",
  "tag": null
}
```

`apps/hermes-agent/package/app/ui/config`：

```json
{
  ".url": {
    "hermes-agent.main": {
      "title": "Hermes Agent",
      "icon": "images/icon_{0}.png",
      "type": "url",
      "protocol": "http",
      "port": "49375",
      "url": "/",
      "allUsers": false,
      "control": {
        "accessPerm": "readonly"
      }
    }
  }
}
```

- [ ] **Step 4: 生成图标**

从上游 v0.22.5 的 `apps/desktop/assets/icon-mac.png`（1024×1024，MIT）生成：

```bash
mkdir -p /tmp/opencode/hermes-icons
ffmpeg -y -loglevel error -i /tmp/opencode/hermes-agent-src/apps/desktop/assets/icon-mac.png \
  -vf scale=256:256 /tmp/opencode/hermes-icons/icon-256.png
ffmpeg -y -loglevel error -i /tmp/opencode/hermes-agent-src/apps/desktop/assets/icon-mac.png \
  -vf scale=64:64 /tmp/opencode/hermes-icons/icon-64.png
cp /tmp/opencode/hermes-icons/icon-256.png apps/hermes-agent/icon-256.png
cp /tmp/opencode/hermes-icons/icon-64.png apps/hermes-agent/icon-64.png
cp apps/hermes-agent/icon-256.png apps/hermes-agent/package/ICON_256.PNG
cp apps/hermes-agent/icon-64.png apps/hermes-agent/package/ICON.PNG
mkdir -p apps/hermes-agent/package/app/ui/images
cp apps/hermes-agent/icon-256.png apps/hermes-agent/package/app/ui/images/icon_256.png
cp apps/hermes-agent/icon-64.png apps/hermes-agent/package/app/ui/images/icon_64.png
```

- [ ] **Step 5: 更新 `.gitignore`**

在 `.gitignore` 末尾加入：

```gitignore
# Hermes Agent build inputs and generated frontend
apps/hermes-agent/.cache/
apps/hermes-agent/dist/
apps/hermes-agent/package/app/web_dist/
apps/hermes-agent/node_modules/
apps/hermes-agent/**/node_modules/
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: `PackageMetadataTest` 全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add apps/hermes-agent .gitignore
git commit -m "feat(hermes-agent): add app identity and fnOS package skeleton"
```

---

### Task 2: `hermes-setup` 运行时安装器

**Files:**
- Create: `apps/hermes-agent/package/app/bin/hermes-setup`
- Create: `apps/hermes-agent/tests/test_setup.py`

**Interfaces:**
- Consumes: `package/app/install-stamp.json`、`VERSION`、`SOURCE_COMMIT`、`package/app/web_dist/`（由构建脚本放入 FPK）。
- Produces:
  - `${TRIM_PKGHOME}/runtime/.ready`，字段 `version`、`commit`、`web_dist_sha256`、`packaging_revision`、`installed_at`。
  - `${TRIM_PKGHOME}/runtime/venv/bin/hermes`。
  - `${TRIM_PKGHOME}/runtime/hermes-agent-0.22.5/`（含 `install-stamp.json` 和 `hermes_cli/web_dist/`）。
  - 退出码 0 表示运行时可用；非 0 表示失败并写 `TRIM_TEMP_LOGFILE`。

- [ ] **Step 1: 写失败的安装器测试**

创建 `apps/hermes-agent/tests/test_setup.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: FAIL，`hermes-setup` 不存在。

- [ ] **Step 3: 实现 `hermes-setup`**

实现要求：

- Shebang `#!/bin/bash`，`set -Eeuo pipefail`。
- 常量：
  ```bash
  VERSION="0.22.5"
  PYTHON_VERSION="3.14.9"
  PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.14.9+20261021-x86_64-unknown-linux-gnu-install_only.tar.gz"
  PYTHON_SHA256="dfa4c5a40c47f338f41658017be550c72247c391e6bfb1fa4da03ebc8451abdf"
  UV_VERSION="0.13.5"
  UV_URL="https://github.com/astral-sh/uv/releases/download/0.13.5/uv-x86_64-unknown-linux-gnu.tar.gz"
  UV_SHA256="f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f"
  NODE_VERSION="26.12.1"
  NODE_URL="https://nodejs.org/dist/v26.12.1/node-v26.12.1-linux-x64.tar.xz"
  NODE_SHA256="6170b2d474e1c626f43cff3adc118df9fe3b573258a4fc3d850c8dbc6b079bbd"
  RG_VERSION="15.2.0"
  RG_URL="https://github.com/BurntSushi/ripgrep/releases/download/15.2.0/ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz"
  RG_SHA256="33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c"
  SOURCE_URL="https://github.com/NousResearch/hermes-agent/archive/refs/tags/v0.22.5.tar.gz"
  SOURCE_SHA256="a8f67e5ec14fea681acef6cc7ff1553f002bb6101fd2df22bfdd4b7eecc54eb2"
  ```
- 函数接口（测试会读取源码/调用）：
  - `log()`
  - `fail()`
  - `toast()`
  - `sha256_file(path)`
  - `download(url, destination, expected_sha256)`
  - `github_mirrors(url)`：返回 direct + ghproxy/gh-proxy/mirror.ghproxy 前缀 URL。
  - `node_mirrors(url)`：返回 nodejs.org + npmmirror 镜像 URL。
  - `download_first(urls, destination, expected_sha256)`
  - `read_ready()`：解析 `${RUNTIME}/.ready` 到 `READY_VERSION` 等变量。
  - `ready_matches()`：version/commit 匹配且 venv 存在。
  - `web_dist_hash()`：对 `${SRC}/hermes_cli/web_dist` 目录计算稳定 hash：`find ... -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum`。
  - `copy_web_dist()`：`rm -rf "${SRC}/hermes_cli/web_dist"; cp -a "${TRIM_APPDEST}/web_dist" "${SRC}/hermes_cli/web_dist"`。
  - `install_stamp()`：`cp "${TRIM_APPDEST}/install-stamp.json" "${SRC}/install-stamp.json"`。
  - `ensure_python()`, `ensure_uv()`, `ensure_node()`, `ensure_ripgrep()`。
  - `sync_venv()`：创建 venv 并执行 `uv sync --extra "${HERMES_SETUP_EXTRAS:-all}" --locked`。
  - `fix_permissions()`：`id -u` 为 0 时 chown；否则打印 `chown=skip`。
  - `write_ready()`。
  - `main()`：解析 `--check`、`--force`、`--version`、`--commit`。
- 从 `${TRIM_APPDEST}/config/bootstrap/version.env` 读取 `PACKAGING_REVISION`（默认 `r0`），写入 `.ready`；打包修订 rN 时由构建脚本写入。
- `--check` 只做本地校验和打印：
  ```text
  version=0.22.5
  commit=bf0203...
  python=3.14.9
  uv=0.13.5
  node=26.12.1
  ripgrep=15.2.0
  packaging_revision=r0
  chown=skip|root
  ```
  不下载、不创建 runtime。
- 脚本末尾使用 `if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi`，便于测试 source 函数。
- `download_first` 必须对每个候选 URL 使用 `curl -fL --retry 3 --connect-timeout 15`，写 `.part`，校验 sha256，失败删除 `.part` 并尝试下一个。
- `github_mirrors` 至少包含：
  ```text
  $url
  https://ghproxy.com/$url
  https://gh-proxy.com/$url
  https://mirror.ghproxy.com/$url
  ```
- `node_mirrors` 至少包含：
  ```text
  https://nodejs.org/dist/v26.12.1/node-v26.12.1-linux-x64.tar.xz
  https://npmmirror.com/mirrors/node/v26.12.1/node-v26.12.1-linux-x64.tar.xz
  ```
- `sync_venv` 环境：
  ```bash
  UV_PROJECT_ENVIRONMENT="$VENV"
  UV_PYTHON="$RUNTIME/python/bin/python3"
  UV_CACHE_DIR="$RUNTIME/.uv-cache"
  UV_CONCURRENT_DOWNLOADS=16
  UV_CONCURRENT_INSTALLS=8
  ```
- 失败时 `trap` 写 `TRIM_TEMP_LOGFILE`：`Hermes Agent 运行时安装失败，详见 ${TRIM_PKGVAR}/install.log`。
- 日志同时写 stderr 和 `${TRIM_PKGVAR}/install.log`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: `SetupScriptTest` 全部 PASS。

- [ ] **Step 5: Shell 语法检查**

Run:
```bash
bash -n apps/hermes-agent/package/app/bin/hermes-setup
```
Expected: 无输出，退出 0。

- [ ] **Step 6: 提交**

```bash
git add apps/hermes-agent/package/app/bin/hermes-setup apps/hermes-agent/tests/test_setup.py
git commit -m "feat(hermes-agent): add runtime installer"
```

---

### Task 3: `cmd/main` 生命周期与 dashboard 认证

**Files:**
- Create: `apps/hermes-agent/package/cmd/main`
- Create: `apps/hermes-agent/tests/test_main.py`

**Interfaces:**
- Consumes: `${TRIM_PKGHOME}/runtime/venv/bin/hermes`、`${TRIM_APPDEST}/bin/hermes-setup`、`${TRIM_PKGETC}/password`。
- Produces:
  - `main start`：创建密码和 `config.yaml`，启动 dashboard，写 `${TRIM_PKGVAR}/dashboard.pid`。
  - `main stop`：停止进程组，删除 PID。
  - `main status`：运行中返回 0，否则 3。
  - `ensure_password`、`ensure_dashboard_config`、`port_in_use`、`start_process`、`stop_process`、`status_process` 可在测试中 source。

- [ ] **Step 1: 写失败的生命周期测试**

创建 `apps/hermes-agent/tests/test_main.py`：

```python
import os
import socket
import stat
import subprocess
import tempfile
import time
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: FAIL，`package/cmd/main` 不存在。

- [ ] **Step 3: 实现 `cmd/main`**

实现要求：

- Shebang `#!/bin/bash`，`set -u`（不要 `set -e`，生命周期函数自己处理错误）。
- 路径：
  ```bash
  PORT="${TRIM_SERVICE_PORT:-49375}"
  DATA_DIR="${TRIM_PKGHOME}/data"
  RUNTIME="${TRIM_PKGHOME}/runtime"
  VENV="${RUNTIME}/venv"
  HERMES="${VENV}/bin/hermes"
  LOG_FILE="${TRIM_PKGVAR}/dashboard.log"
  PID_FILE="${TRIM_PKGVAR}/dashboard.pid"
  PASSWORD_FILE="${TRIM_PKGETC}/password"
  SETUP="${TRIM_APPDEST}/bin/hermes-setup"
  ```
- `log_msg()` 写 `${LOG_FILE}`。
- `ensure_runtime()`：如果 `${RUNTIME}/.ready` 或 `${HERMES}` 缺失，调用 `"${SETUP}"`；失败返回 1。
- `ensure_password()`：`umask 077`；`mkdir -p "$(dirname "${PASSWORD_FILE}")"`；`head -c 32 /dev/urandom | base64 | tr -d '\n'`；`chmod 600`。
- `ensure_dashboard_config()`：
  ```bash
  HERMES_PASSWORD="$(cat "${PASSWORD_FILE}")" \
  HERMES_WORKDIR="${WORKDIR}" \
  HOME="${DATA_DIR}" HERMES_HOME="${DATA_DIR}" \
  "${VENV}/bin/python" - <<'PY'
  import os, secrets
  from hermes_cli.config import load_config, save_config
  from hermes_cli.plugins_cmd import ensure_basic_auth_plugin_enabled_in_config
  from plugins.dashboard_auth.basic import hash_password
  cfg = load_config()
  basic = cfg.setdefault("dashboard", {}).setdefault("basic_auth", {})
  basic["username"] = "hermes"
  basic["password_hash"] = hash_password(os.environ["HERMES_PASSWORD"])
  basic["password"] = ""
  if not str(basic.get("secret", "") or "").strip():
      basic["secret"] = secrets.token_urlsafe(32)
  ensure_basic_auth_plugin_enabled_in_config(cfg)
  terminal = cfg.setdefault("terminal", {})
  if not str(terminal.get("cwd", "") or "").strip():
      terminal["cwd"] = os.environ["HERMES_WORKDIR"]
  save_config(cfg)
  PY
  ```
- `WORKDIR`：`${TRIM_DATA_SHARE_PATHS%%:*}`；为空则 `${DATA_DIR}/workspace`。
- `port_in_use()`：`(exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null`。
- `start_process()`：
  - 如果 `status_process` 为真，返回 0。
  - `ensure_runtime`；失败写日志并返回 1。
  - `mkdir -p "${DATA_DIR}" "${TRIM_PKGVAR}" "${WORKDIR}"`。
  - `ensure_password`；`ensure_dashboard_config`；失败返回 1。
  - 如果 `port_in_use`，`log_msg "port ${PORT} is already in use"`，返回 1。
  - 启动：
    ```bash
    rm -f "${PID_FILE}"
    setsid env HOME="${DATA_DIR}" HERMES_HOME="${DATA_DIR}" \
      PATH="${VENV}/bin:${RUNTIME}/node/bin:${RUNTIME}/bin:/usr/local/bin:/usr/bin:/bin" \
      nohup "${HERMES}" dashboard --host 0.0.0.0 --port "${PORT}" --no-open --skip-build \
      >> "${LOG_FILE}" 2>&1 &
    ```
  - 写 `$!` 到 PID_FILE。
  - 最多 60 秒轮询 `port_in_use` 和 `kill -0`；失败则 `kill -TERM -- -"$pid"`，删除 PID，返回 1。
- `status_process()`：PID 文件存在、`kill -0`、`port_in_use`；否则删除 stale PID 并返回 1。
- `stop_process()`：
  - 读 PID；`kill -TERM -- -"${pid}"`（进程组）。
  - 最多 20 秒等待进程消失；再 `kill -KILL -- -"${pid}"`。
  - 删除 PID。
- 脚本末尾使用 `if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then case "${1:-}" in start) ... ;; stop) ... ;; status) ... ;; esac; fi`，便于测试 source 函数。

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: `MainLifecycleTest` 全部 PASS。

- [ ] **Step 5: Shell 语法检查**

Run: `bash -n apps/hermes-agent/package/cmd/main`
Expected: 退出 0。

- [ ] **Step 6: 提交**

```bash
git add apps/hermes-agent/package/cmd/main apps/hermes-agent/tests/test_main.py
git commit -m "feat(hermes-agent): add dashboard lifecycle and auth setup"
```

---

### Task 4: fnOS 生命周期回调与 CLI 包装器

**Files:**
- Create: `apps/hermes-agent/package/cmd/install_init`
- Create: `apps/hermes-agent/package/cmd/install_callback`
- Create: `apps/hermes-agent/package/cmd/upgrade_init`
- Create: `apps/hermes-agent/package/cmd/upgrade_callback`
- Create: `apps/hermes-agent/package/cmd/uninstall_init`
- Create: `apps/hermes-agent/package/cmd/uninstall_callback`
- Create: `apps/hermes-agent/package/cmd/config_init`
- Create: `apps/hermes-agent/package/cmd/config_callback`
- Create: `apps/hermes-agent/package/app/bin/hermes`
- Create: `apps/hermes-agent/tests/test_lifecycle.py`

**Interfaces:**
- Consumes: `cmd/main`、`app/bin/hermes-setup`。
- Produces: fnOS 生命周期回调；`hermes` CLI 包装器。

- [ ] **Step 1: 写失败的回调测试**

创建 `apps/hermes-agent/tests/test_lifecycle.py`：

```python
import os
import subprocess
import tempfile
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: FAIL，回调文件不存在。

- [ ] **Step 3: 实现回调与包装器**

`cmd/install_init`：

```bash
#!/bin/bash
# fnOS runs install_init before app directories exist and as the package user.
# Keep this script side-effect free.
set -u
echo "[hermes-agent] install_init: no-op" >&2
exit 0
```

`cmd/install_callback`：

```bash
#!/bin/bash
set -u
SETUP="${TRIM_APPDEST}/bin/hermes-setup"
if [ ! -x "${SETUP}" ]; then
    echo "hermes-setup not found: ${SETUP}" >&2
    exit 1
fi
exec "${SETUP}"
```

`cmd/upgrade_init`：

```bash
#!/bin/bash
set -u
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"${SCRIPT_DIR}/main" stop 2>/dev/null || true
exit 0
```

`cmd/upgrade_callback`：

```bash
#!/bin/bash
set -u
SETUP="${TRIM_APPDEST}/bin/hermes-setup"
if [ ! -x "${SETUP}" ]; then
    echo "hermes-setup not found: ${SETUP}" >&2
    exit 1
fi
exec "${SETUP}"
```

`cmd/uninstall_init`：

```bash
#!/bin/bash
set -u
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"${SCRIPT_DIR}/main" stop 2>/dev/null || true
exit 0
```

`cmd/uninstall_callback`、`cmd/config_init`、`cmd/config_callback`：

```bash
#!/bin/bash
set -u
exit 0
```

`app/bin/hermes`：

```bash
#!/bin/bash
set -e
TRIM_PKGHOME="${TRIM_PKGHOME:-/vol1/@apphome/hermes-agent}"
DATA_DIR="${TRIM_PKGHOME}/data"
RUNTIME="${TRIM_PKGHOME}/runtime"
export HOME="${DATA_DIR}"
export HERMES_HOME="${DATA_DIR}"
export PATH="${RUNTIME}/venv/bin:${RUNTIME}/node/bin:${RUNTIME}/bin:${PATH}"
exec "${RUNTIME}/venv/bin/hermes" "$@"
```

- [ ] **Step 4: 设置可执行位**

```bash
chmod +x apps/hermes-agent/package/cmd/* apps/hermes-agent/package/app/bin/hermes apps/hermes-agent/package/app/bin/hermes-setup
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: `LifecycleScriptsTest` 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add apps/hermes-agent/package/cmd apps/hermes-agent/package/app/bin/hermes apps/hermes-agent/tests/test_lifecycle.py
git commit -m "feat(hermes-agent): add fnOS lifecycle callbacks and CLI wrapper"
```

---

### Task 5: `scripts/build.py` 构建脚本

**Files:**
- Create: `apps/hermes-agent/scripts/build.py`
- Create: `apps/hermes-agent/tests/test_build.py`
- Create: `apps/hermes-agent/provenance.json`

**Interfaces:**
- Consumes: `VERSION`、`SOURCE_COMMIT`、`package/`、`package/app/install-stamp.json`、`package/app/web_dist/`（可选）。
- Produces: `dist/hermes-agent-<version>-fnos-amd64[-rN].fpk`、`.sha256`、`dist/provenance.generated.json`。

- [ ] **Step 1: 写失败的构建测试**

创建 `apps/hermes-agent/tests/test_build.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: FAIL，`build.py` 或 `provenance.json` 不存在。

- [ ] **Step 3: 创建 `provenance.json`**

```json
{
  "appname": "hermes-agent",
  "version": "0.22.5",
  "upstream": {
    "repo": "https://github.com/NousResearch/hermes-agent",
    "tag": "v0.22.5",
    "version": "0.22.5",
    "commit": "bf0203a794a07aac3ff764972ab9087baa4e4f4e",
    "source_url": "https://github.com/NousResearch/hermes-agent/archive/refs/tags/v0.22.5.tar.gz",
    "source_sha256": "a8f67e5ec14fea681acef6cc7ff1553f002bb6101fd2df22bfdd4b7eecc54eb2",
    "license": "MIT"
  },
  "runtime": {
    "python": "3.14.9",
    "python_sha256": "dfa4c5a40c47f338f41658017be550c72247c391e6bfb1fa4da03ebc8451abdf",
    "uv": "0.13.5",
    "uv_sha256": "f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f",
    "node": "26.12.1",
    "node_sha256": "6170b2d474e1c626f43cff3adc118df9fe3b573258a4fc3d850c8dbc6b079bbd",
    "ripgrep": "15.2.0",
    "ripgrep_sha256": "33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c"
  },
  "toolchain": {
    "fnpack": "1.2.3",
    "fnpack_sha256": "54b97fa7b70968c4d05c79840f5daeff508957d0bb2062fdb0376d00d9615c93"
  },
  "update": {
    "mechanism": "external",
    "distribution": "fnos",
    "owner": "FnDepot"
  },
  "fpk": null
}
```

- [ ] **Step 4: 实现 `build.py`**

实现要求：

- Python 3.10+，只用标准库。
- 常量与 `provenance.json` 一致；`--check-only` 校验：
  - `VERSION` == `package/manifest` 的 version == `package/config/bootstrap/version.env` 的 `APP_VERSION` == `package/app/install-stamp.json` 的 `baseVersion`。
  - `SOURCE_COMMIT` == `install-stamp.json` 的 commit == `provenance.json` 的 upstream commit。
  - 图标尺寸 256/64。
  - 所有 `package/cmd/*` 和 `package/app/bin/*` 存在且可执行。
  - 不包含 `.fpk`、`.git`、`node_modules`、真实手机号/邮箱/内网 IP（简单正则）。
  - 打印 `hermes-agent 0.22.5 source=<sha256-prefix>`。
- `--web-dist PATH`：使用现成目录；否则：
  1. 下载/解压 Node 26.12.1 到 `.cache/node/26.12.1/`。
  2. 解压源码 tarball 到临时目录。
  3. `npm ci --workspace web --no-audit --no-fund`；失败回退 `npm install --workspace web --no-audit --no-fund`。
  4. `npm run build -w web`。
  5. 校验 `hermes_cli/web_dist/index.html`。
  6. 打 tar.gz 并计算 sha256。
- 下载源码 tarball：`--source-tarball` 或 `SOURCE_URL`；校验 `SOURCE_SHA256`。
- 下载 fnpack 1.2.3 到缓存并校验；支持 `--fnpack`。
- staging：
  - 复制 `package/` 到临时目录。
  - 替换 `manifest` 的 version 行。
  - 写 `config/bootstrap/version.env`，其中 `PACKAGING_REVISION` 取 `--artifact-suffix` 的值（为空则 `r0`）。
  - 复制 `install-stamp.json` 到 `app/install-stamp.json`（已存在，校验）。
  - 复制 `web_dist` 到 `app/web_dist`。
  - 确保 `app/bin/hermes-setup`、`cmd/*` 可执行。
- `fnpack build --directory <stage>`，输出到 `dist/`。
- `verify_fpk`：
  - 外层 tar.gz 的 `manifest` appname/version/platform/service_port。
  - `app.tgz` 的 MD5 与 manifest checksum 一致。
  - `app.tgz` 内包含 `web_dist/index.html`、`install-stamp.json`、`bin/hermes-setup`。
  - `ICON.PNG` 64×64、`ICON_256.PNG` 256×256。
  - FPK 大小 < 100 MB。
- 输出 JSON 摘要：`ok`、`version`、`artifact`（path/name/size/sha256）、`source`（sha256）、`web_dist`（sha256）、`fnpack`（version/sha256）。
- `--artifact-suffix rN` 修改文件名，不改 manifest version。
- `--json` 输出摘要；默认也输出人类可读摘要。
- `--keep-staging` 保留临时目录。

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: `BuildScriptTest` 全部 PASS。

- [ ] **Step 6: 语法检查**

Run: `python3 -m py_compile apps/hermes-agent/scripts/build.py`
Expected: 退出 0。

- [ ] **Step 7: 提交**

```bash
git add apps/hermes-agent/scripts/build.py apps/hermes-agent/tests/test_build.py apps/hermes-agent/provenance.json
git commit -m "feat(hermes-agent): add FPK build pipeline"
```

---

### Task 6: 构建 `web_dist` 与 FPK

**Files:**
- Modify: `apps/hermes-agent/provenance.json`（填入 `web_dist` 和 `fpk` 信息）
- Generated (ignored): `apps/hermes-agent/dist/*.fpk`、`.sha256`、`provenance.generated.json`

**Interfaces:**
- Consumes: Task 5 的 `build.py`。
- Produces: 可安装的 FPK 和校验值；`provenance.json` 的 `fpk` 字段。

- [ ] **Step 1: 运行完整构建**

```bash
cd apps/hermes-agent
python3 scripts/build.py --json | tee /tmp/opencode/hermes-build.json
```

Expected: 生成 `dist/hermes-agent-0.22.5-fnos-amd64.fpk` 和 `.sha256`；JSON 中 `ok: true`。

- [ ] **Step 2: 验证 FPK 内容**

```bash
python3 - <<'PY'
import json, tarfile
from pathlib import Path
fpk = Path('dist/hermes-agent-0.22.5-fnos-amd64.fpk')
with tarfile.open(fpk, 'r:gz') as outer:
    print('outer:', outer.getnames())
    manifest = outer.extractfile('manifest').read().decode()
    print(manifest[:400])
PY
```

Expected: manifest 包含 `appname = hermes-agent`、`version = 0.22.5`、`platform = x86`、`service_port = 49375`；`app.tgz` 存在。

- [ ] **Step 3: 记录 `web_dist` 和 FPK 信息**

从 `dist/provenance.generated.json` 读取 `source.sha256`、`web_dist.sha256`、`artifact.sha256`、`artifact.size`、`artifact.name`，更新 `apps/hermes-agent/provenance.json` 的 `web_dist` 和 `fpk` 字段。`fpk.release_url` 暂填：

```text
https://github.com/CrRinko/FnDepot/releases/tag/hermes-agent-v0.22.5
```

`download_url` 暂填：

```text
https://github.com/CrRinko/FnDepot/releases/download/hermes-agent-v0.22.5/hermes-agent-0.22.5-fnos-amd64.fpk
```

- [ ] **Step 4: 运行全量静态测试**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: 全部 PASS。

- [ ] **Step 5: 提交构建元数据**

```bash
git add apps/hermes-agent/provenance.json
git commit -m "build(hermes-agent): record 0.22.5 artifact provenance"
```

---

### Task 7: 运行时 smoke test（安装、认证、升级保留）

**Files:**
- Create: `apps/hermes-agent/tests/smoke_runtime.sh`（可选，手动运行）
- Modify: 如发现问题，修复对应脚本

**Interfaces:**
- Consumes: Task 6 的 FPK 或 `hermes-setup`。
- Produces: 验证运行时安装、dashboard 登录、数据保留、前端替换。

- [ ] **Step 1: 在临时目录安装运行时**

```bash
export SMOKE=/tmp/opencode/hermes-smoke
rm -rf "$SMOKE"
mkdir -p "$SMOKE"/{target,home,var,etc}
cp -a apps/hermes-agent/package/app/. "$SMOKE/target/"
export TRIM_APPDEST="$SMOKE/target"
export TRIM_PKGHOME="$SMOKE/home"
export TRIM_PKGVAR="$SMOKE/var"
export TRIM_PKGETC="$SMOKE/etc"
export TRIM_USERNAME="$(id -un)"
export HERMES_SETUP_EXTRAS=web
bash "$SMOKE/target/bin/hermes-setup"
```

Expected: 生成 `$SMOKE/home/runtime/venv/bin/hermes`；`hermes --version` 输出 `0.22.5`。

验证内置更新被拒绝：

```bash
set +e
HOME="$SMOKE/home/data" HERMES_HOME="$SMOKE/home/data" \
  "$SMOKE/home/runtime/venv/bin/hermes" update --check \
  > "$SMOKE/var/update-check.log" 2>&1
UPDATE_CODE=$?
set -e
test "$UPDATE_CODE" -eq 2
grep -qiE 'fnos|managed by its install method' "$SMOKE/var/update-check.log"
```

Expected: 退出码 2，日志包含 `fnos` 或 `managed by its install method`。

- [ ] **Step 2: 启动 dashboard 并验证登录**

```bash
PORT=49376
HOME="$SMOKE/home/data" HERMES_HOME="$SMOKE/home/data" \
  "$SMOKE/home/runtime/venv/bin/hermes" dashboard \
  --host 127.0.0.1 --port "$PORT" --no-open --skip-build \
  > "$SMOKE/var/smoke-dashboard.log" 2>&1 &
PID=$!
for i in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/login" >/dev/null 2>&1 && break
  sleep 1
done
# 未认证：期望 200 登录页或 302
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:$PORT/"
# 错误密码：期望 401
curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -d '{"provider":"basic","username":"hermes","password":"wrong"}' \
  "http://127.0.0.1:$PORT/auth/password-login"
# 正确密码：期望 200，并写 cookie
PASSWORD=$(cat "$SMOKE/etc/password")
curl -s -c "$SMOKE/var/cookies.txt" -o /dev/null -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  -d "{\"provider\":\"basic\",\"username\":\"hermes\",\"password\":\"$PASSWORD\"}" \
  "http://127.0.0.1:$PORT/auth/password-login"
curl -s -b "$SMOKE/var/cookies.txt" -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:$PORT/"
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
```

Expected：第一个请求 200/302；错误密码 401；正确密码 200；带 cookie 的请求 200。

- [ ] **Step 3: 验证数据保留**

```bash
mkdir -p "$SMOKE/home/data/sessions"
printf 'sentinel\n' > "$SMOKE/home/data/sessions/smoke-sentinel.txt"
bash "$SMOKE/target/bin/hermes-setup"
test -f "$SMOKE/home/data/sessions/smoke-sentinel.txt"
```

Expected: sentinel 仍存在。

- [ ] **Step 4: 验证已有 model/provider 配置不被覆盖**

```bash
cat > "$SMOKE/home/data/config.yaml" <<'YAML'
model:
  provider: test-provider
  default: test-model
providers:
  test-provider:
    base_url: http://127.0.0.1:1/v1
    api_key: test-key
YAML
TRIM_APPDEST="$SMOKE/target" \
TRIM_PKGHOME="$SMOKE/home" \
TRIM_PKGVAR="$SMOKE/var" \
TRIM_PKGETC="$SMOKE/etc" \
TRIM_DATA_SHARE_PATHS="$SMOKE/home/data/workspace" \
bash -c 'source apps/hermes-agent/package/cmd/main; ensure_dashboard_config'
grep -q 'test-provider' "$SMOKE/home/data/config.yaml"
grep -q 'test-model' "$SMOKE/home/data/config.yaml"
grep -q 'username: hermes' "$SMOKE/home/data/config.yaml"
```

Expected: 三个 `grep` 都退出 0；`ensure_dashboard_config` 只追加/更新 `dashboard` 和空的 `terminal.cwd`，不覆盖已有 model/provider。

- [ ] **Step 5: 验证 `web_dist` 替换**

```bash
printf '<html>rN-marker</html>\n' > "$SMOKE/target/web_dist/index.html"
bash "$SMOKE/target/bin/hermes-setup"
grep -q 'rN-marker' "$SMOKE/home/runtime/hermes-agent-0.22.5/hermes_cli/web_dist/index.html"
```

Expected: `grep` 退出 0，`.ready` 的 `web_dist_sha256` 更新。

- [ ] **Step 6: 修复问题并提交**

如果 smoke test 暴露问题，修复对应文件并运行 `python3 -m unittest discover -s apps/hermes-agent/tests -v`，然后：

```bash
git add -A apps/hermes-agent
git commit -m "fix(hermes-agent): address runtime smoke test findings"
```

---

### Task 8: FnDepot 元数据、README 与发布

**Files:**
- Modify: `fnpack.json`
- Modify: `README.md`
- Create: `apps/hermes-agent/README.md`
- Create: `apps/hermes-agent/BUILD.md`
- Create: `apps/hermes-agent/NOTICE`
- Modify: `apps/hermes-agent/provenance.json`
- Modify: `apps/hermes-agent/tests/test_package.py`（增加 `fnpack.json` 一致性测试）

**Interfaces:**
- Consumes: Task 6 的 FPK 名称、size、sha256。
- Produces: FnDepot 可读取的元数据、应用详情页、构建说明、Release。

- [ ] **Step 1: 增加 `fnpack.json` 一致性测试**

在 `test_package.py` 中增加：

```python
class FnDepotEntryTest(unittest.TestCase):
    def test_hermes_entry_matches_artifact(self):
        fnpack = json.loads((REPO / "fnpack.json").read_text())
        app = fnpack["apps"]["hermes-agent"]
        self.assertEqual(app["platform"], ["x86"])
        self.assertEqual(app["service_port"], "49375")
        self.assertEqual(app["maintainer"], "CrRinko")
        release = app["releases"]["0.22.5"]
        package = release["packages"]["x86"]
        artifact = APP / "dist/hermes-agent-0.22.5-fnos-amd64.fpk"
        if artifact.is_file():
            import hashlib
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(package["sha256"], digest)
            self.assertEqual(package["size"], artifact.stat().st_size)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m unittest discover -s apps/hermes-agent/tests -v`
Expected: FAIL，`fnpack.json` 没有 `hermes-agent`。

- [ ] **Step 3: 更新 `fnpack.json`**

在 `apps` 对象中加入 `hermes-agent`（保持 `opencode` 不变）：

```json
"hermes-agent": {
  "display_name": "Hermes Agent",
  "desc": "Hermes Agent 官方 AI Agent，提供官方 Web Dashboard。首次启动后用户名 hermes，密码随机生成。SSH 登录 NAS 后以 root 权限执行 sudo cat /var/apps/hermes-agent/etc/password 获取密码。仅支持 x86 设备。",
  "i18n": {
    "en-US": {
      "display_name": "Hermes Agent",
      "desc": "Official Hermes Agent AI assistant with its official web dashboard. Username: hermes. The password is generated on first start; run sudo cat /var/apps/hermes-agent/etc/password as root on the NAS to read it. x86 devices only."
    }
  },
  "platform": ["x86"],
  "categories": ["AI赋能", "系统工具"],
  "icon_url": "apps/hermes-agent/icon-256.png",
  "readme_url": "apps/hermes-agent/README.md",
  "bug_report_url": "https://github.com/CrRinko/FnDepot/issues",
  "maintainer": "CrRinko",
  "maintainer_url": "https://github.com/CrRinko",
  "distributor": "CrRinko",
  "distributor_url": "https://github.com/CrRinko",
  "run_as": "package",
  "install_type": "",
  "is_docker": false,
  "service_port": "49375",
  "releases": {
    "0.22.5": {
      "changelog": "首发：基于上游 Hermes Agent v0.22.5，官方 dashboard，随机密码登录，安装时创建 Python 3.14 运行时。",
      "i18n": {
        "en-US": {
          "changelog": "Initial release based on upstream Hermes Agent v0.22.5 with the official dashboard, generated password login, and an install-time Python 3.14 runtime."
        }
      },
      "updated_at": "2026-11-01T00:00:00+08:00",
      "packages": {
        "x86": {
          "download_url": "https://github.com/CrRinko/FnDepot/releases/download/hermes-agent-v0.22.5/hermes-agent-0.22.5-fnos-amd64.fpk",
          "sha256": "<build output sha256>",
          "size": 0
        }
      }
    }
  }
}
```

把 `<build output sha256>` 和 `size` 替换为 Task 6 的实际值。

- [ ] **Step 4: 更新根 `README.md`**

在应用表格中加入：

```markdown
| [Hermes Agent](apps/hermes-agent/README.md) | 0.22.5 | x86 | AI赋能 / 系统工具 |
```

在 OpenCode 章节后加入 Hermes 章节，包含：

- 安装包 Release 链接。
- Web UI：`http://<NAS-IP>:49375`，用户名 `hermes`。
- 密码：首次启动随机生成，`sudo cat /var/apps/hermes-agent/etc/password`。
- 文件大小和 SHA-256。
- 首次安装时间约 10–20 分钟。
- 升级通过 FnDepot，不使用应用内自更新。

- [ ] **Step 5: 创建 `apps/hermes-agent/README.md`**

包含：

- 版本与来源表（上游 repo/tag/commit、源码 SHA-256、Python/uv/Node/ripgrep 版本）。
- 安装与访问。
- 登录：用户名 `hermes`，密码路径，`sudo cat` 命令。
- 数据路径：`/vol1/@apphome/hermes-agent/data`、日志、密码。
- 安全：监听 `0.0.0.0:49375`，密码登录页 + Cookie，不要把端口直接暴露公网。
- 升级：只通过 FnDepot + 应用中心。`install-stamp.json` 的 `updateMechanism=external` + `distribution=fnos` 让 `hermes update` 和 dashboard 更新动作拒绝执行；解释这是为了保持 FPK 运行时一致。
- 卸载：停止服务，保留 `data/`；手动删除命令。
- 说明：第三方打包，不是 Nous Research 官方发布；上游 MIT。

- [ ] **Step 6: 创建 `apps/hermes-agent/BUILD.md`**

包含：

- 构建环境：Linux amd64、Python 3.10+、Node 26.12.1/npm、网络。
- `python3 scripts/build.py`。
- 离线/复用：`--source-tarball`、`--web-dist`、`--fnpack`、`--artifact-suffix rN`。
- 发布：`gh release create hermes-agent-v0.22.5 ...`，上传 `.fpk` 和 `.sha256`，更新 `fnpack.json`/`provenance.json`/README。
- 版本升级步骤：更新 `VERSION`、`SOURCE_COMMIT`、`provenance.json`、`install-stamp.json`、`version.env`，重新构建。
- 打包修订：`--artifact-suffix rN`，不要覆盖已发布资产。
- 内置更新：保持 `install-stamp.json` 的 `updateMechanism=external` 和 `distribution=fnos`，不要在打包时改成 `self`；升级只由 FnDepot/应用中心交付。

- [ ] **Step 7: 创建 `apps/hermes-agent/NOTICE`**

```text
Hermes Agent is developed by Nous Research and licensed under the MIT License.
https://github.com/NousResearch/hermes-agent

This fnOS package is an independent third-party packaging by CrRinko.
The fnOS lifecycle scripts, build script, and documentation in this directory
are licensed under the MIT License. No source code from any GPL-licensed
community fnOS package is included.
```

- [ ] **Step 8: 更新 `provenance.json` 的 `fpk` 字段**

填入 Task 6 的 `name`、`sha256`、`size`、`release_url`、`download_url`。

- [ ] **Step 9: 运行测试和隐私检查**

```bash
python3 -m unittest discover -s apps/hermes-agent/tests -v
python3 -m json.tool fnpack.json >/dev/null
python3 -m json.tool apps/hermes-agent/provenance.json >/dev/null
git diff --check
grep -RInE '(@s\.whatsapp\.net|[0-9]{11,}|192\.168\.|10\.[0-9]+\.[0-9]+\.[0-9]+)' \
  apps/hermes-agent fnpack.json README.md || true
```

Expected: 测试 PASS；JSON 合法；grep 只命中占位符或没有命中。

- [ ] **Step 10: 提交**

```bash
git add fnpack.json README.md apps/hermes-agent
git commit -m "feat(hermes-agent): publish 0.22.5 FnDepot metadata"
```

- [ ] **Step 11: 创建 GitHub Release 并上传**

```bash
export PATH="$HOME/.local/bin:$PATH"
gh release create hermes-agent-v0.22.5 \
  apps/hermes-agent/dist/hermes-agent-0.22.5-fnos-amd64.fpk \
  apps/hermes-agent/dist/hermes-agent-0.22.5-fnos-amd64.fpk.sha256 \
  --title "Hermes Agent 0.22.5" \
  --notes "Hermes Agent v0.22.5 for fnOS (x86_64). Official dashboard, generated password login."
```

Expected: `gh release view hermes-agent-v0.22.5 --json assets` 列出两个资产。

- [ ] **Step 12: 验证 Release 资产**

```bash
gh release view hermes-agent-v0.22.5 --json assets --jq '.assets[].name'
curl -sI -L https://github.com/CrRinko/FnDepot/releases/download/hermes-agent-v0.22.5/hermes-agent-0.22.5-fnos-amd64.fpk | head -5
```

Expected: 资产名正确；HTTP 200。

- [ ] **Step 13: 推送**

```bash
git push origin main
```

Expected: 推送成功。

---

### Task 9: 最终验证与代码审查

**Files:**
- Modify: 如有问题，修复对应文件

**Interfaces:**
- Consumes: 所有前置任务。
- Produces: 可交付的仓库状态和 Release。

- [ ] **Step 1: 运行全部静态测试**

```bash
python3 -m unittest discover -s apps/hermes-agent/tests -v
bash -n apps/hermes-agent/package/cmd/*
bash -n apps/hermes-agent/package/app/bin/*
python3 -m py_compile apps/hermes-agent/scripts/build.py
```

Expected: 全部通过。

- [ ] **Step 2: 校验 `fnpack.json` 与 FPK**

```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path
app = json.loads(Path('fnpack.json').read_text())['apps']['hermes-agent']
pkg = app['releases']['0.22.5']['packages']['x86']
fpk = Path('apps/hermes-agent/dist/hermes-agent-0.22.5-fnos-amd64.fpk')
assert pkg['size'] == fpk.stat().st_size, (pkg['size'], fpk.stat().st_size)
assert pkg['sha256'] == hashlib.sha256(fpk.read_bytes()).hexdigest()
print('fnpack.json matches FPK')
PY
```

Expected: `fnpack.json matches FPK`。

- [ ] **Step 3: 隐私与身份检查**

```bash
git log -3 --format='%h %an <%ae> %s'
git status --short
grep -RInE '(@s\.whatsapp\.net|192\.168\.|10\.[0-9]+\.[0-9]+\.[0-9]+)' \
  apps/hermes-agent fnpack.json README.md || true
```

Expected: 作者为 `CrRinko <9782921+CrRinko@users.noreply.github.com>`；工作区干净；没有隐私命中。

- [ ] **Step 4: 请求最终代码审查**

使用 `superpowers:requesting-code-review`，重点检查：

- `install_init` 是否真的无副作用。
- `hermes-setup` 的非 root 路径是否可能 `chown`。
- `cmd/main` 是否会在端口冲突时误杀进程。
- `ensure_dashboard_config` 是否会覆盖已有的 model/provider 配置。
- `install-stamp.json` 的 `updateMechanism=external` + `distribution=fnos` 是否真的让 `hermes update` 和 dashboard 更新动作拒绝执行。
- `fnpack.json` 的 size/sha256 是否与 Release 资产一致。

- [ ] **Step 5: 处理审查意见并提交**

按审查意见修复，重新运行 Task 9 Step 1-3，提交：

```bash
git add -A
git commit -m "fix(hermes-agent): address final review findings"
git push origin main
```
