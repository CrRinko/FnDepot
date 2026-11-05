# GitLab fnOS Docker App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package GitLab CE 19.5.3 as an fnOS Docker application with editable external domain/HTTPS port, reuse of fnOS certificates, and real-NAS verified lifecycle.

**Architecture:** A tiny FPK contains an fnOS Docker compose project (`gitlab`) plus Python helpers that select a certificate from fnOS's certificate store, render `/etc/gitlab/gitlab.rb`, and synchronize settings. The official `gitlab/gitlab-ce:19.5.3-ce.0` image is pulled by the app center; data lives in `${TRIM_PKGVAR}`. `cmd/main` runs as root and reconciles configuration/certificates before starting or restarting the container.

**Tech Stack:** fnOS fnpack 1.2.3, Bash lifecycle scripts, Python 3.11 (`unittest`, `json`, `ssl`, `subprocess`), Docker Compose v2, GitLab CE 19.5.3.

**Spec:** `docs/superpowers/specs/2026-11-05-gitlab-fnos-docker-app-design.md`

## Global Constraints

- GitLab CE `19.5.3`; image `gitlab/gitlab-ce:19.5.3-ce.0`; amd64 digest `sha256:60fc37e470aca439ead4b6e3ed8f578d9e85c954b84b611b5f323a32a9e47615`.
- `appname=gitlab`; app version `19.5.3`; platform `x86`; `is_docker=true`; `service_port=8443`; `checkport=false`; `os_min_version=1.2.0800`.
- Defaults: `HTTPS_PORT=8443`, `HTTP_PORT=8080`, `SSH_PORT=2224`, `TIME_ZONE=Asia/Shanghai`; `GITLAB_DOMAIN` defaults to empty and auto-detects the fnOS certificate domain, else the NAS IP.
- Never write the test NAS domain, Tailscale/IP, private keys, certificates, or passwords into the repo or FPK.
- Ports 80, 443, and 22 are reserved by fnOS and must always be rejected.
- Data lives in `${TRIM_PKGVAR}` (`/vol1/@appdata/gitlab`); uninstall keeps data by default.
- Use GitLab 19.2+ nginx keys: `gitlab_rails['nginx'][...]`, not deprecated top-level `nginx[...]`.
- `letsencrypt['enable'] = false`; Puma 2 workers; Sidekiq 6; Prometheus and KAS disabled; compose `mem_limit: 8g`, `shm_size: 256m`.
- FPK must stay image-free (tens of KB); the app center pulls the image.
- All changes happen on branch `feat/gitlab-app` in `/home/zhaoge/.local/share/opencode/worktree/aa3037/hermes-agent`.

## Review Focus

- A settings save with an occupied, duplicate, or reserved port must not break the running GitLab; the app keeps the last known-good config.
- Changing `GITLAB_DOMAIN` to a hostname without a matching fnOS certificate must generate a self-signed certificate for that hostname, never serve a mismatched Let's Encrypt certificate.
- A missing, unreadable, malformed, or expired fnOS certificate store must fall back without crashing and must not serve an expired certificate.
- The app center may start the compose project before callbacks; a root-owned `${TRIM_PKGVAR}/config` must be repaired by `cmd/main`, and `install_callback` must not fail installation.
- The HTTP→HTTPS redirect must target the configured domain and HTTPS port, not the NAS IP; otherwise the desktop icon is unusable.

---

### Task 1: Repository skeleton, icon, and build verifier

**Files:**
- Create: `apps/gitlab/VERSION`, `apps/gitlab/APP_VERSION`, `apps/gitlab/provenance.json`
- Create: `apps/gitlab/package/manifest`
- Create: `apps/gitlab/package/config/privilege`, `apps/gitlab/package/config/resource`
- Create: `apps/gitlab/package/app/docker/docker-compose.yaml`
- Create: `apps/gitlab/package/app/ui/config`
- Create: `apps/gitlab/package/app/ui/images/icon_64.png`, `icon_256.png`
- Create: `apps/gitlab/package/ICON.PNG`, `ICON_256.PNG`
- Create: `apps/gitlab/icon-64.png`, `apps/gitlab/icon-256.png`
- Create: `apps/gitlab/package/cmd/{main,install_init,install_callback,upgrade_init,upgrade_callback,uninstall_init,uninstall_callback,config_init,config_callback}` (stubs for now)
- Create: `apps/gitlab/package/wizard/install`, `wizard/config`, `wizard/uninstall` (minimal valid JSON for now)
- Create: `apps/gitlab/scripts/build.py`
- Test: `apps/gitlab/scripts/build.py --check-only`, `apps/gitlab/dist/*.fpk`

**Interfaces:**
- Produces: `apps/gitlab/scripts/build.py` with `--check-only`, `--json`, `--app-version` (default from `APP_VERSION`), `--artifact-suffix`; `python3 -m unittest` test root at `apps/gitlab/tests`.
- Produces: `package/manifest` fields consumed by fnpack; `config/resource` project name `gitlab`; `app/ui/config` entry id `gitlab.main`.

- [ ] **Step 1: Download/prepare the GitLab tanuki icon and resize it**

Use the official GitLab press-kit tanuki PNG. If the network is unavailable, generate a simple 256×256 tanuki-like placeholder with the text "GitLab" and note it in `BUILD.md`. Produce 64×64 and 256×256 PNGs at the six paths above. Verify with Python/Pillow or a PNG IHDR check that each is the expected square size.

- [ ] **Step 2: Write the failing build check**

Run: `cd apps/gitlab && python3 scripts/build.py --check-only`
Expected: FAIL with a message that `package/manifest` or a required file is missing (the script may not exist yet; first create a minimal `build.py` that only checks paths and exits 1).

- [ ] **Step 3: Create the package skeleton**

`manifest`:

```ini
appname               = gitlab
version               = 19.5.3
display_name          = GitLab
desc                  = GitLab 官方代码托管与 DevOps 平台，使用官方 Docker 镜像，支持自定义访问域名和 HTTPS。首次启动需要拉取约 1.65GB 镜像。
platform              = x86
source                = thirdparty
maintainer            = CrRinko
maintainer_url        = https://github.com/CrRinko
distributor           = CrRinko
distributor_url       = https://github.com/CrRinko
os_min_version        = 1.2.0800
desktop_uidir         = ui
desktop_applaunchname = gitlab.main
service_port          = 8443
checkport             = false
ctl_stop              = true
disable_authorization_path = true
```

`config/privilege`:

```json
{
  "defaults": {"run-as": "package"},
  "username": "docker-gitlab",
  "groupname": "docker-gitlab",
  "join-groups": ["docker"]
}
```

`provenance.json`:

```json
{
  "appname": "gitlab",
  "app_version": "19.5.3",
  "version": "19.5.3",
  "upstream": {
    "repo": "https://gitlab.com/gitlab-org/gitlab",
    "tag": "v19.5.3",
    "version": "19.5.3",
    "license": "MIT"
  },
  "image": {
    "name": "gitlab/gitlab-ce",
    "tag": "19.5.3-ce.0",
    "digest": "sha256:60fc37e470aca439ead4b6e3ed8f578d9e85c954b84b611b5f323a32a9e47615"
  },
  "update": {"mechanism": "external", "distribution": "fnos", "owner": "FnDepot"},
  "fpk": {
    "revision": "r0",
    "name": "gitlab-19.5.3-fnos-amd64.fpk",
    "sha256": "",
    "size": 0
  }
}
```

`config/resource`:

```json
{"docker-project": {"projects": [{"name": "gitlab", "path": "docker"}]}}
```

`app/docker/docker-compose.yaml`:

```yaml
name: gitlab
services:
  gitlab:
    image: gitlab/gitlab-ce:19.5.3-ce.0
    container_name: gitlab
    restart: unless-stopped
    hostname: gitlab
    shm_size: "256m"
    mem_limit: 8g
    environment:
      TZ: ${TIME_ZONE:-Asia/Shanghai}
    ports:
      - "${HTTPS_PORT:-8443}:${HTTPS_PORT:-8443}"
      - "${HTTP_PORT:-8080}:80"
      - "${SSH_PORT:-2224}:22"
    volumes:
      - "${TRIM_PKGVAR}/config:/etc/gitlab"
      - "${TRIM_PKGVAR}/logs:/var/log/gitlab"
      - "${TRIM_PKGVAR}/data:/var/opt/gitlab"
```

`app/ui/config`:

```json
{
  ".url": {
    "gitlab.main": {
      "title": "GitLab",
      "icon": "images/icon_{0}.png",
      "type": "url",
      "protocol": "http",
      "port": "${HTTP_PORT}",
      "url": "/",
      "allUsers": false
    }
  }
}
```

`wizard/install`, `wizard/config`, `wizard/uninstall`: write `[]` for now; Task 5 fills them. `cmd/*`: minimal `#!/bin/bash\nexit 0` with executable bit.

- [ ] **Step 4: Implement `scripts/build.py --check-only`**

Checks:

- `VERSION` and `APP_VERSION` are `19.5.3` and match `provenance.json`.
- Manifest has `appname=gitlab`, version `19.5.3`, `platform=x86`, `service_port=8443`, `checkport=false`, `desktop_applaunchname=gitlab.main`.
- `config/resource` project name is `gitlab`; compose starts with `name: gitlab` and uses the pinned image, no `latest`.
- `app/ui/config` contains `gitlab.main` and `${HTTP_PORT}`.
- All nine `cmd/*` and `app/bin/*` files are executable; `bash -n` passes.
- Wizard files are valid JSON.
- Icons are 64×64 and 256×256.
- Privacy scan: no private IPv4, email, `PRIVATE KEY`, `BEGIN CERTIFICATE`, or literal test-NAS domain; allow GitLab URLs and `gitlab@` email examples only if needed.
- `CONFIG` contains no `latest`.

Run: `cd apps/gitlab && python3 scripts/build.py --check-only`
Expected: PASS with `gitlab 19.5.3 check ok`.

- [ ] **Step 5: Implement the full build**

`python3 scripts/build.py` stages `package/`, overwrites `manifest` version with `APP_VERSION`, downloads/verifies fnpack `1.2.3` (same URL/sha as the Hermes app), runs `fnpack build`, and writes `dist/gitlab-19.5.3-fnos-amd64.fpk` plus `.sha256`. Verify the outer tar contains `manifest`, `app.tgz`, `ICON.PNG`, `ICON_256.PNG`; verify the manifest `checksum` equals the MD5 of `app.tgz`; verify no `.crt`, `.key`, `settings.env`, `.git`, or `tests` inside `app.tgz`.

Run: `cd apps/gitlab && python3 scripts/build.py --json`
Expected: `"ok": true`, artifact size under 200 KB.

- [ ] **Step 6: Commit**

```bash
git add apps/gitlab
git commit -m "feat(gitlab): scaffold fnOS Docker package"
```

---

### Task 2: Certificate selection with fnOS store and self-signed fallback

**Files:**
- Create: `apps/gitlab/package/app/bin/select_cert.py`
- Create: `apps/gitlab/tests/test_select_cert.py`

**Interfaces:**
- Produces: `select_certificate(entries: list[dict], requested_domain: str, now: float | None = None) -> CertChoice | None`
- Produces: `resolve_domain(requested_domain: str, choice: CertChoice | None, primary_ip: str) -> str`
- Produces: `install_choice(choice: CertChoice, dest_dir: Path, state_path: Path) -> InstallResult`
- Produces: `generate_self_signed(domain: str, dest_dir: Path, state_path: Path) -> InstallResult`
- Produces CLI: `python3 select_cert.py --store PATH --dest-dir PATH --state PATH [--domain NAME]`; stdout `RESOLVED_DOMAIN=...` and `CERT_CHANGED=0|1`.
- `CertChoice`: `domain`, `san: list[str]`, `cert_path`, `key_path`, `valid_to: int`, `used: bool`.
- `InstallResult`: `changed: bool`, `domain: str`, `sha256: str`, `source: str`.

- [ ] **Step 1: Write failing tests**

`apps/gitlab/tests/test_select_cert.py` with `unittest`. Generate test certs in `setUp` using `openssl req -x509 -newkey rsa:2048 -nodes -subj /CN=... -addext subjectAltName=...`. Build a fixture store JSON. Assertions:

- exact SAN match wins over `used: true` non-match.
- wildcard `*.example.com` matches `gitlab.example.com` but not `a.b.example.com`.
- expired entries are skipped.
- empty requested domain picks `used: true` non-`fnOS`.
- empty requested domain with only `fnOS` falls back to self-signed for the supplied primary IP.
- requested domain with no match generates self-signed for that exact domain (SAN `DNS:...`).
- `install_choice` copies fullchain and key, sets mode 0600, writes `cert-source.json`, and reports `changed=true` on first run, `false` on identical second run.
- malformed store with an existing destination keeps the existing cert and reports `changed=false`.

Run: `cd apps/gitlab && python3 -m unittest tests.test_select_cert -v`
Expected: FAIL with `ModuleNotFoundError` or missing functions.

- [ ] **Step 2: Implement `select_cert.py`**

Rules from spec §8.1. Use only stdlib (`json`, `os`, `ssl`, `subprocess`, `hashlib`, `pathlib`, `socket`, `argparse`). Validate that each path is absolute; ignore entries with missing cert/key. `validTo` is milliseconds; treat `<= now*1000` as expired. Match SAN case-insensitively; exact first, then single-label wildcard. Domain fallback: requested → selected cert domain (if not `fnOS`) → primary IP (`hostname -I` first address). Copy `fullchain` if non-empty else `certificate`; copy key; write state JSON with `source`, `source_domain`, `valid_to`, `sha256`, `installed_at`; chmod 0600. Use temp files and `os.replace`. Self-signed via `openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes -keyout ... -out ... -subj /CN=<domain> -addext subjectAltName=DNS:<domain>` (or `IP:<ip>`); escape only validated hostnames/IPs.

CLI prints exactly:

```text
RESOLVED_DOMAIN=<domain>
CERT_CHANGED=0|1
CERT_SOURCE=fnos|self-signed
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd apps/gitlab && python3 -m unittest tests.test_select_cert -v`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/gitlab/package/app/bin/select_cert.py apps/gitlab/tests/test_select_cert.py
git commit -m "feat(gitlab): select fnOS certificates with self-signed fallback"
```

---

### Task 3: Settings validation and gitlab.rb rendering

**Files:**
- Create: `apps/gitlab/package/app/bin/gitlab_config.py`
- Create: `apps/gitlab/tests/test_gitlab_config.py`

**Interfaces:**
- Produces: `Settings` dataclass (`domain: str`, `https_port: int`, `http_port: int`, `ssh_port: int`, `timezone: str`).
- Produces: `validate_settings(settings: Settings, previous: Settings | None = None, check_ports: bool = True) -> list[str]`.
- Produces: `render_gitlab_rb(settings: Settings) -> str`.
- Produces: `write_if_changed(path: Path, content: str) -> bool`.
- Produces CLI: `python3 gitlab_config.py --domain D --https-port P --http-port P --ssh-port P --time-zone TZ --output PATH [--previous PATH]`; stdout `CONFIG_CHANGED=0|1`.

- [ ] **Step 1: Write failing tests**

Assertions:

- valid settings render an `external_url 'https://<domain>:<https_port>'`, `gitlab_rails['nginx']['listen_port'] = <port>`, `ssl_certificate`/`ssl_certificate_key` paths `/etc/gitlab/ssl/gitlab.crt|key`, `redirect_http_to_https = true`, `gitlab_shell_ssh_port`, `time_zone`, `letsencrypt['enable'] = false`, Puma/Sidekiq/Prometheus/KAS/PostgreSQL/Redis lines.
- domain with `https://`, `/`, `..`, spaces, or an invalid hostname is rejected.
- IPv4 domain is accepted; `IP:` SAN is handled by the cert script.
- ports 80, 443, 22 are rejected; duplicate ports are rejected; range 1–65535 enforced.
- a changed port that is in use is rejected; the same port as `previous` is allowed even if the app currently owns it.
- `write_if_changed` returns false for identical content and true when content changes; the file is replaced atomically.
- timezone with quotes/newlines is rejected; `Asia/Shanghai` accepted.

Run: `cd apps/gitlab && python3 -m unittest tests.test_gitlab_config -v`
Expected: FAIL with missing module.

- [ ] **Step 2: Implement `gitlab_config.py`**

Use `socket.connect_ex(("127.0.0.1", port)) == 0` for in-use detection; skip a port when `previous` has the same value. Validate hostname with a conservative regex (`[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?`), reject labels >63 chars, total >253, and IPv4 octets >255. Reject `"fnOS"` as a configured domain. Timezone regex `[A-Za-z0-9_+\-/]+`. Render with single-quoted Ruby strings; escape `'` is impossible after validation.

- [ ] **Step 3: Run tests**

Run: `cd apps/gitlab && python3 -m unittest tests.test_gitlab_config -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/gitlab/package/app/bin/gitlab_config.py apps/gitlab/tests/test_gitlab_config.py
git commit -m "feat(gitlab): validate settings and render gitlab.rb"
```

---

### Task 4: Sync orchestration, lifecycle scripts, and host-level tests

**Files:**
- Create: `apps/gitlab/package/app/bin/sync_config.py`
- Replace: `apps/gitlab/package/cmd/*`
- Create: `apps/gitlab/tests/test_sync_config.py`
- Create: `apps/gitlab/tests/test_lifecycle.sh`

**Interfaces:**
- Consumes: `select_cert.py` and `gitlab_config.py` functions.
- Produces: `sync_config.py --mode install|save|upgrade|runtime`; reads `TRIM_PKGVAR`, `TRIM_APPDEST`, `GITLAB_DOMAIN`, `HTTPS_PORT`, `HTTP_PORT`, `SSH_PORT`, `TIME_ZONE`, `GITLAB_CERT_STORE`; writes `${TRIM_PKGVAR}/settings.env`, `${TRIM_PKGVAR}/config/gitlab.rb`, `${TRIM_PKGVAR}/config/ssl/*`, `${TRIM_PKGVAR}/cert-source.json`; stdout keys `RESOLVED_DOMAIN`, `CONFIG_CHANGED`, `CERT_CHANGED`, `HTTPS_PORT`, `HTTP_PORT`, `SSH_PORT`, `TIME_ZONE`.
- Produces: `cmd/main` behavior start/stop/status as spec §9.5.

- [ ] **Step 1: Write failing sync tests**

`test_sync_config.py` with temp `TRIM_PKGVAR`, fixture store, fake `/usr/trim` path via `GITLAB_CERT_STORE`, assertions:

- install mode with valid env writes settings.env, gitlab.rb, cert files, state; stdout has `CONFIG_CHANGED=1`.
- save mode with an invalid port exits non-zero, writes an error message, and does not modify settings.env.
- runtime mode with invalid env falls back to the previous settings.env and exits 0 with the old values.
- runtime mode with no settings.env and no env uses defaults and auto-detects the fixture cert domain.
- a second identical run prints `CONFIG_CHANGED=0`, `CERT_CHANGED=0`.
- changing the domain to a domain with no fixture cert generates a self-signed cert and prints the new resolved domain.
- `GITLAB_CERT_STORE` pointing to a malformed file with existing certs keeps them and exits 0.

`test_lifecycle.sh` sets temp `TRIM_APPDEST` to a copy of `package/app`, temp `TRIM_PKGVAR`, runs `cmd/install_callback`, then asserts files exist; runs `cmd/config_callback` with an invalid port and asserts non-zero; runs `bash -n` on every `cmd/*`.

Run: `cd apps/gitlab && python3 -m unittest tests.test_sync_config -v && bash tests/test_lifecycle.sh`
Expected: FAIL.

- [ ] **Step 2: Implement `sync_config.py`**

Pipeline:

1. Load env; if empty, load `settings.env`.
2. In runtime mode, if env invalid, load `settings.env`; if still invalid, use defaults (`domain=""`, `8443/8080/2224`, `Asia/Shanghai`).
3. In install/save/upgrade mode, invalid env is fatal: write `TRIM_TEMP_LOGFILE` and exit 1.
4. Validate with `previous` loaded from `settings.env` (skip same-port in-use checks).
5. Call `select_cert` with the requested domain and the configured store; get resolved domain.
6. Render `gitlab.rb` with the resolved domain and ports; write atomically.
7. In install/save/upgrade mode, write `settings.env` with the user's inputs (domain may be empty) after success.
8. Print the stdout keys.

- [ ] **Step 3: Implement lifecycle scripts**

`install_callback`:

```bash
#!/bin/bash
set -u
python3 "${TRIM_APPDEST}/bin/sync_config.py" --mode install || {
  echo "GitLab 配置初始化失败，详见 ${TRIM_PKGVAR}/install.log" >"${TRIM_TEMP_LOGFILE}"
  exit 1
}
```

If `${TRIM_PKGVAR}` is not writable by the package user, still exit 0 after logging (the root-side `cmd/main` repairs). `config_callback` uses `--mode save` and must not call Docker. `upgrade_callback` uses `--mode upgrade`. `install_init`, `config_init`, `upgrade_init` are `exit 0`. `uninstall_init` runs `docker compose -p gitlab stop` best-effort. `uninstall_callback` implements keep/delete with the gitea pattern (clear contents, do not unlink the platform directory).

`cmd/main`:

- `start`: call `sync_config --mode runtime`, export ports, `docker compose -p gitlab -f "${TRIM_APPDEST}/docker/docker-compose.yaml" up -d`, check container.
- `stop`: `docker compose -p gitlab stop`.
- `status`: root ensures `${TRIM_PKGVAR}/config`, `config/ssl`, and `settings.env` are writable by `${TRIM_USERNAME:-docker-gitlab}` (do not recursively chown `data`/`logs`); sync; if `CONFIG_CHANGED=1`, `up -d` then `docker restart gitlab`; elif `CERT_CHANGED=1` and container running, `docker exec gitlab gitlab-ctl hup nginx`; else `up -d` if not running; copy `config/initial_root_password` to `${TRIM_PKGVAR}/initial_root_password.txt` (0600) if absent; exit 0 if running else 3.
- Write failures to `${TRIM_TEMP_LOGFILE}`.
- Use `docker compose` only when `command -v docker` exists; otherwise exit 1 with a clear message.

- [ ] **Step 4: Run tests and syntax checks**

Run: `cd apps/gitlab && python3 -m unittest tests.test_sync_config -v && bash tests/test_lifecycle.sh && bash -n package/cmd/*`
Expected: PASS; lifecycle test creates/validates files and invalid save fails.

- [ ] **Step 5: Commit**

```bash
git add apps/gitlab/package/app/bin/sync_config.py apps/gitlab/package/cmd apps/gitlab/tests
git commit -m "feat(gitlab): synchronize settings and lifecycle"
```

---

### Task 5: Wizards, manifest copy, and user documentation

**Files:**
- Replace: `apps/gitlab/package/wizard/install`, `wizard/config`, `wizard/uninstall`
- Modify: `apps/gitlab/package/manifest` description
- Create: `apps/gitlab/README.md`, `apps/gitlab/BUILD.md`, `apps/gitlab/NOTICE`
- Modify: `apps/gitlab/scripts/build.py` (wizard/UI checks)
- Test: `python3 scripts/build.py --check-only`

- [ ] **Step 1: Write the failing check**

Extend `build.py --check-only` to require these exact wizard fields:

- install/config: `GITLAB_DOMAIN`, `HTTPS_PORT`, `HTTP_PORT`, `SSH_PORT`, `TIME_ZONE`.
- install/config include a `tips` item mentioning certificate reuse.
- uninstall: `wizard_data_action` with `keep` and `delete`.
- Defaults: empty domain, `8443`, `8080`, `2224`, `Asia/Shanghai`.
- Port fields use the full 1–65535 regex.
- `app/ui/config` uses `${HTTP_PORT}` and `protocol=http`.

Run: `cd apps/gitlab && python3 scripts/build.py --check-only`
Expected: FAIL with a wizard/field message.

- [ ] **Step 2: Write the wizard JSON**

Use the fn-gitea field style. `GITLAB_DOMAIN` is optional (`required` omitted or false) with help text: "只填域名，不带 https:// 和端口；留空自动使用 fnOS 当前证书域名，没有证书时使用 NAS IP。" `HTTPS_PORT` default `8443`, `HTTP_PORT` `8080`, `SSH_PORT` `2224`, `TIME_ZONE` `Asia/Shanghai`. Add a `tips` item: "应用会读取 fnOS 证书库，优先使用与域名匹配的证书；没有匹配证书时生成自签名证书。" Duplicate the same fields in `wizard/config`. `wizard/uninstall` uses a `select` with `wizard_data_action` default `keep` and options `keep`/`delete`.

- [ ] **Step 3: Write README/BUILD/NOTICE**

README must cover: what it is, image version, requirements (fnOS 1.2.0800, 4GB+ RAM, 2GB+ disk for image plus data), install, default URL, how domain/HTTPS/SSH ports are configured, certificate priority and fallback, how to add a matching fnOS certificate, initial root password path `${TRIM_PKGVAR}/initial_root_password.txt` (and GitLab's original), HTTP 8080 redirect, 443 limitation, backup command, upgrade path (sequential GitLab versions), uninstall data behavior, security notes. No test NAS domain/IP.

BUILD.md: fnpack 1.2.3, build command, check command, artifact name, test commands. NOTICE: GitLab is a trademark of GitLab Inc.; this is an unofficial community package; MIT for packaging scripts.

- [ ] **Step 4: Run the check**

Run: `cd apps/gitlab && python3 scripts/build.py --check-only`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/gitlab
git commit -m "docs(gitlab): add wizards and user documentation"
```

---

### Task 6: Full FPK build and static verification

**Files:**
- Modify: `apps/gitlab/scripts/build.py` (if verification gaps)
- Output: `apps/gitlab/dist/gitlab-19.5.3-fnos-amd64.fpk`, `.sha256`, `provenance.generated.json`

- [ ] **Step 1: Build**

Run: `cd apps/gitlab && python3 scripts/build.py --json`
Expected: `"ok": true`; artifact under 200 KB; `app_tgz_md5` recorded.

- [ ] **Step 2: Inspect the FPK**

Run a Python one-liner/script that opens the outer tar and `app.tgz` and asserts:

- manifest `version=19.5.3`, `appname=gitlab`, `service_port=8443`, `checkport=false`, `checksum` equals MD5 of `app.tgz`.
- `app.tgz` contains `docker/docker-compose.yaml`, `ui/config`, all nine `cmd/*`, both `bin/*.py`, and all wizard JSON.
- No `.crt`, `.key`, `settings.env`, `initial_root_password`, `.git`, `tests`, or `__pycache__`.
- No string matching the test NAS domain or Tailscale IP.
- `docker-compose.yaml` image is exactly `gitlab/gitlab-ce:19.5.3-ce.0`.

- [ ] **Step 3: Commit any build fixes**

```bash
git add apps/gitlab
git commit -m "fix(gitlab): tighten FPK verification"
```

(Only if files changed; the artifact itself is ignored.)

---

### Task 7: Install on the real NAS and verify HTTPS/certificate

**Files:** none in repo unless fixes are needed.

- [ ] **Step 1: Upload and install the FPK**

Use the existing fnos-cli profile and SSH access. Upload `dist/gitlab-19.5.3-fnos-amd64.fpk` to `/vol1/1000/Documents/` and install via `fnos-cli app install-fpk --remote-path ... --volume-id 1 --yes`. The app is new (`gitlab`), so no "already installed" conflict. Monitor the install task; the image pull may take several minutes.

- [ ] **Step 2: Verify container and ports**

On the NAS:

```bash
docker compose ls
docker ps --filter name=gitlab
ss -ltnp | grep -E ':(8443|8080|2224)\b'
stat -c '%U:%G %A %n' /vol1/@appdata/gitlab /vol1/@appdata/gitlab/config /vol1/@appdata/gitlab/config/gitlab.rb
cat /vol1/@appdata/gitlab/settings.env
head -40 /vol1/@appdata/gitlab/config/gitlab.rb
cat /vol1/@appdata/gitlab/cert-source.json
docker exec gitlab gitlab-ctl status
```

Expected: project `gitlab`, container running, ports 8443/8080/2224, resolved domain is the test NAS domain, cert source is `fnos`, `gitlab-ctl status` shows `run: ...`; `config`/`config/ssl`/`settings.env` are writable by `docker-gitlab` (or repaired by `cmd/main`), while `data`/`logs` remain container-managed.

- [ ] **Step 3: Verify HTTPS certificate and redirect**

```bash
curl -sSI --resolve <nas-domain>:8443:<nas-ip> https://<nas-domain>:8443/users/sign_in | head
curl -sSI http://127.0.0.1:8080/ | head
openssl s_client -connect 127.0.0.1:8443 -servername <nas-domain> </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -dates
```

Expected: `200`/`302` login, `301` redirect with `Location: https://<nas-domain>:8443/...`, certificate subject matches the domain and issuer is Let's Encrypt (not the fnOS self-signed cert). Also test `curl --cacert` or `verify_result=0` from the host.

- [ ] **Step 4: Verify the desktop entry**

Open the GitLab icon from the fnOS desktop (or inspect the generated entry URL in the app center/app config detail). Expected: it opens `http://<NAS-IP>:8080/`, then redirects to `https://<nas-domain>:8443/` with a valid certificate. If the entry port is literally `${HTTP_PORT}` or the redirect targets the IP, implement the documented fallback: set `app/ui/config` to `protocol: https`, `port: ${HTTPS_PORT}` and document the custom-URL setting.

- [ ] **Step 5: Verify SSH and initial password**

```bash
ssh -p 2224 -o StrictHostKeyChecking=no git@<nas-domain> 2>&1 | head
sudo cat /vol1/@appdata/gitlab/initial_root_password.txt
```

Expected: GitLab SSH welcome/banner; a non-empty password file with mode 600. Log in to the web UI with `root` and the password; do not print the password in logs/chat.

- [ ] **Step 6: Fix and repeat if needed**

If the image pull, certificate selection, redirect, or app entry fails, fix the package, rebuild, reinstall, and repeat steps 2–5. Do not claim completion until all pass.

- [ ] **Step 7: Commit fixes**

```bash
git add apps/gitlab
git commit -m "fix(gitlab): address real-NAS install findings"
```

---

### Task 8: Settings changes, certificate renewal, and lifecycle

**Files:** none in repo unless fixes are needed.

- [ ] **Step 1: Change HTTPS port**

Inspect the current fields with `fnos-cli ... app config detail gitlab`, then set `HTTPS_PORT=8444` with `fnos-cli ... app config set --fields '{"HTTPS_PORT":"8444"}' gitlab --yes` (or the App Center UI). Confirm `config_callback` succeeds, the container is recreated, `https://<nas-domain>:8444` works, and 8443 is closed. Then restore `8443` the same way. If `config set` does not trigger `config_callback`/restart, run `fnos-cli ... app restart gitlab --yes` and record the actual behavior.

- [ ] **Step 2: Change domain to one without a certificate**

Set `GITLAB_DOMAIN` to a test hostname with no fnOS cert (e.g., `gitlab-test.invalid`). Confirm the app generates a self-signed certificate for that hostname, does not serve the Let's Encrypt cert, and the container starts. Then clear the domain to restore auto-detection and confirm the Let's Encrypt cert is used again.

- [ ] **Step 3: Invalid settings do not break the app**

Set `HTTPS_PORT=443` (reserved) and save. Expect a clear error, `settings.env` unchanged, the existing container still running on 8443. Repeat with an occupied port (e.g., 5666). Restore defaults.

- [ ] **Step 4: Certificate renewal fixture**

Use `GITLAB_CERT_STORE` with a fixture JSON pointing to a temp copy of the certificate/key. Run `cmd/main status` with the fixture, replace the fixture cert with a newly generated one, run status again, and confirm the app copies it and calls `gitlab-ctl hup nginx` (check `cert-source.json` hash and container logs). Do not modify the real fnOS certificate.

- [ ] **Step 5: Lifecycle**

Stop/start via App Center; confirm data persists and the container returns. Build a packaging revision `19.5.3.1` (same image) with a docs-only change, install it, confirm the container is recreated and repositories/users persist. Test uninstall with `keep` and `delete` on a throwaway install if feasible; otherwise verify the scripts and document the untested path.

- [ ] **Step 6: Commit fixes**

```bash
git add apps/gitlab
git commit -m "fix(gitlab): address lifecycle and settings findings"
```

---

### Task 9: Publish to FnDepot and GitHub Release

**Files:**
- Modify: `fnpack.json` (add `gitlab`)
- Modify: `README.md` (root app table and section)
- Modify: `apps/gitlab/provenance.json` (FPK sha/size, image digest)
- Create/update: `apps/gitlab/README.md` release links
- Test: remote `fnpack.json`, Release asset digest

- [ ] **Step 1: Build the final artifact and record values**

Run `python3 scripts/build.py --json`; record `size`, `sha256`, `app_tgz_md5`. Update `provenance.json` and the app README with the artifact name, size, sha256, and release URL.

- [ ] **Step 2: Add the app to `fnpack.json`**

Use the existing app shape: `is_docker: true`, `run_as: "package"`, `install_type: ""`, `service_port: "8443"`, categories `["编程开发","系统工具"]`, `platform: ["x86"]`, icon/readme paths, release key `19.5.3`, download URL `https://github.com/CrRinko/FnDepot/releases/download/gitlab-v19.5.3/gitlab-19.5.3-fnos-amd64.fpk`, sha256/size from the build.

- [ ] **Step 3: Update root README**

Add GitLab to the app table and a section with the release link, web URL/ports, domain/HTTPS settings, initial password path, image size, and data location. Use placeholders, not the test NAS domain.

- [ ] **Step 4: Commit, tag, release**

Commit the metadata, push `feat/gitlab-app`, merge/push to `main` per the repo flow, create tag `gitlab-v19.5.3`, and `gh release create` with the FPK and `.sha256`. Verify `gh release view --json assets` reports the same sha256 digest and size as the local artifact.

- [ ] **Step 5: Verify the public source**

Fetch `https://raw.githubusercontent.com/CrRinko/FnDepot/main/fnpack.json`, confirm the GitLab entry points to the release and the sha256/size match. Confirm the asset HEAD returns 200 with the expected content length.

---

### Self-Review Checklist (run after implementing)

- [ ] Every spec section §1–§14 maps to a task above.
- [ ] Certificate priority, wildcard, expired, and fallback cases are covered by tests.
- [ ] Invalid settings cannot overwrite `settings.env` or break a running container.
- [ ] `cmd/main` repairs root-owned data directories and is idempotent.
- [ ] The HTTP redirect target uses the configured domain/port; if not, the HTTPS-entry fallback is implemented and documented.
- [ ] No personal domain/IP, private key, certificate, or password is in the repo/FPK.
- [ ] Real-NAS tests produce command output evidence before any completion claim.
