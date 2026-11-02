# 构建 Hermes Agent FPK

本目录保存 Hermes Agent 的 fnOS 包源码与构建脚本。上游源码不直接提交到仓库；构建时下载官方 `v0.22.5` tarball，生成补丁源码，再用固定版本 fnpack 组装 FPK。应用版本写在 `APP_VERSION`（当前 `0.22.5.3`），上游版本写在 `VERSION`（当前 `0.22.5`）。

## 环境

- Linux amd64（Windows 建议 WSL Ubuntu）
- Python 3.10+
- 构建补丁源码需要 **Python 3.14** 和 **uv 0.13.5**
- 构建前端需要 **Node 26.12.1**（`build.py` 会自动下载）
- 可访问 GitHub、npm、PyPI 和 `static2.fnnas.com`

## 一键构建

```bash
cd apps/hermes-agent

# 1. 下载上游源码（首次）
curl -fL -o /tmp/hermes-agent-0.22.5.tar.gz \
  https://github.com/NousResearch/hermes-agent/archive/refs/tags/v0.22.5.tar.gz

# 2. 生成补丁源码（移除 Android-only psutil，重新生成官方 uv.lock）
python3 scripts/prepare_source.py \
  --source-tarball /tmp/hermes-agent-0.22.5.tar.gz \
  --uv /path/to/uv-0.13.5 \
  --python /path/to/python3.14 \
  --output .cache/hermes-agent-0.22.5-fnos.tar.gz

# 3. 构建 FPK（首次会自动构建 web_dist）
python3 scripts/build.py \
  --patched-source .cache/hermes-agent-0.22.5-fnos.tar.gz \
  --artifact-suffix r2
```

输出：

```text
dist/hermes-agent-0.22.5.3-fnos-amd64-r2.fpk
dist/hermes-agent-0.22.5.3-fnos-amd64-r2.fpk.sha256
dist/provenance.generated.json
```

`--app-version` 默认读取 `APP_VERSION`；`--artifact-suffix` 同时作为打包修订号（`r2`）写入版本信息和内嵌源码文件名。

## 离线/复用

```bash
python3 scripts/build.py \
  --patched-source .cache/hermes-agent-0.22.5-fnos.tar.gz \
  --source-tarball /tmp/hermes-agent-0.22.5.tar.gz \
  --web-dist .cache/source/hermes-agent-0.22.5/hermes_cli/web_dist \
  --fnpack /path/to/fnpack \
  --artifact-suffix r2
```

- `--web-dist`：复用已构建的官方 dashboard 前端。
- `--source-tarball`：复用已下载的上游源码。
- `--fnpack`：复用已校验的 fnpack 1.2.3。

## 补丁源码说明

`prepare_source.py` 只改两处：

1. 删除 `pyproject.toml` 中 Android-only 的 `psutil @ git+https://github.com/giampaolo/psutil.git@...`。
2. 用官方 PyPI 重新生成 `uv.lock`。

这样 NAS 上的 `uv sync --locked` 不会去构建 Android 专用的 git psutil，也不会因为国内 PyPI 镜像缺少上传时间而失败。Linux 仍使用 `psutil==7.2.2`。

## 发布

```bash
export PATH="$HOME/.local/bin:$PATH"
gh release create hermes-agent-v0.22.5.3 \
  dist/hermes-agent-0.22.5.3-fnos-amd64-r2.fpk \
  dist/hermes-agent-0.22.5.3-fnos-amd64-r2.fpk.sha256 \
  --title "Hermes Agent 0.22.5.3" \
  --notes "Hermes Agent upstream v0.22.5, FnDepot packaging r2, for fnOS (x86_64)."
```

然后更新：

- `fnpack.json` 的 `download_url`、`sha256`、`size`
- `provenance.json` 的 `fpk` 字段
- 根 `README.md` 和本目录 `README.md` 的版本/哈希

## 版本升级

1. 更新 `VERSION`（上游版本）、`APP_VERSION`（应用版本）、`SOURCE_COMMIT`。
2. 更新 `package/config/bootstrap/version.env`（构建时也会按参数重写）。
3. 更新 `package/app/install-stamp.json`（`baseVersion`、`commit`、`displayVersion`）。
4. 更新 `scripts/prepare_source.py`/`build.py` 中固定的上游 URL 与 SHA-256。
5. 重新生成补丁源码并构建。
6. 发布新 Release，更新 `fnpack.json`/`provenance.json`/README。

## 打包修订（rN）

上游版本不变、只改打包脚本时：

1. 递增 `APP_VERSION`（例如 `0.22.5.3` → `0.22.5.4`）。fnOS 应用中心以应用版本作为升级键；重复使用同一个应用版本会命中缓存，或被判定为“已安装”而拒绝安装。
2. 用新的 `--artifact-suffix` 构建，同时递增打包修订号：

```bash
python3 scripts/build.py \
  --patched-source .cache/hermes-agent-0.22.5-fnos.tar.gz \
  --web-dist .cache/source/hermes-agent-0.22.5/hermes_cli/web_dist \
  --artifact-suffix r3
```

上传新的 Release 资产，更新 `fnpack.json` 的版本键、URL、`sha256`、`size`；不要覆盖已发布的同版本资产。

## 内置更新

保持 `package/app/install-stamp.json` 的：

```json
"updateMechanism": "external",
"distribution": "fnos"
```

不要改成 `self`。升级只由 FnDepot + fnOS 应用中心交付；应用内 `hermes update` 会被上游拒绝。
