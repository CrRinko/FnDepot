# FnDepot repo instructions

FnDepot V2 source. The GitHub repo URL is the source URL; clients read root `fnpack.json` (not `fndepot.json`).

## Layout and edit surfaces

- `fnpack.json` is the only source index. Keep `schema_version: "2"`, the app key exactly equal to the FPK `appname`, `platform: ["x86"]` for these packages, and `categories` from the fixed list below (max 2).
- Use fixed categories only: 影音娱乐、系统工具、编程开发、AI赋能、生活服务、智能智控、教育学习、游戏地带、硬件驱动.
- `packages.x86.size` is exact bytes and `sha256` is the 64-hex digest of the final FPK. The release key must equal the FPK manifest `version`.
- `icon_url` and `readme_url` are relative to the repo root; `download_url` is a GitHub Release asset URL.
- Follow the existing app shape: `run_as: "package"`, `install_type: ""`, `is_docker: false`, `service_port` as a string.
- `apps/<appname>/` is self-contained: `README.md` (FnDepot detail page), `BUILD.md`, `VERSION`, `SOURCE_COMMIT`, `provenance.json`, `package/` (fnOS skeleton), and `scripts/build.py`.
- `apps/opencode/package/manifest` and `app/README.txt` are package source. `build.py` rewrites the staged manifest version and placeholders; never edit generated FPKs or `dist/`.
- Root `README.md` is the source overview; `apps/opencode/README.md` is the app detail page. Keep both consistent with `fnpack.json`.
- Never commit `.fpk`/`.fpk.sha256`; they are Release assets (`.gitignore`). GitHub's 100 MB file limit also blocks the 121 MB FPK.

## Build and release

- Build host must be Linux amd64; on Windows use WSL Ubuntu. Python 3.10+.
- From `apps/opencode`: `python3 scripts/build.py`.
- It reads `VERSION`/`SOURCE_COMMIT`, downloads and verifies the official `@opencode/cli-linux-x64@<version>` npm tarball, pins/verifies fnpack 1.2.3, then verifies the manifest, `app.tgz` MD5, x86-64 ELF, and icons. Output goes to `apps/opencode/dist/` (ignored). There is no separate unit-test suite.
- Offline/reuse: `python3 scripts/build.py --tarball ... --expected-sha512 ... --fnpack ...`.
- Packaging-only change (same upstream version): `python3 scripts/build.py --artifact-suffix rN`; upload a new Release asset and update `fnpack.json` URL, `sha256`, and `size`. Do not overwrite an already-published version+arch asset.
- Publish: upload the `.fpk` and `.sha256` to GitHub Release tag `opencode-v<version>`, then update `fnpack.json`, `provenance.json`, and both READMEs. Metadata-only changes do not require rebuilding the FPK.

## fnOS lifecycle gotchas

- `cmd/install_init` runs before app directories exist and as the package user. Keep it side-effect free. Do not `mkdir` `TRIM_PKGETC`/`TRIM_PKGVAR`/`TRIM_PKGHOME` or write the password there; that fails with `Permission denied` and aborts installation.
- The password is created by `cmd/main` (`ensure_password`) on first start. Web UI username is `opencode`; there is no fixed default password. On the NAS: `sudo cat /var/apps/opencode/etc/password`.
- Keep `package/cmd/*` and `package/app/bin/opencode-server` executable; `.gitattributes` enforces LF. If adding a script, use `git update-index --chmod=+x`.
- Keep `OPENCODE_DISABLE_AUTOUPDATE=1` in `opencode-server`. Upgrades are delivered as new FPKs through FnDepot/fnOS app center; `/update` and `opencode upgrade` are unsupported and can install a second copy.

## Identity and releases

- App `maintainer` and `distributor` are `CrRinko` (https://github.com/CrRinko). Do not add personal usernames/emails or NAS host/volume IDs.
- Repo-local Git identity is `CrRinko <9782921+CrRinko@users.noreply.github.com>`; keep it.
- `fnpack.json` is the source of truth for release metadata. Current app is `opencode` 2.2.5 (packaging revision r3); tag is `opencode-v2.2.5`.

FnDepot V2 spec: https://github.com/EWEDLCM/FnDepot
