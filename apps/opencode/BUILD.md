# 构建 OpenCode FPK

本目录保存 OpenCode 的 fnOS 包源码与构建脚本。上游 OpenCode 源码不直接放进本仓库；构建时下载官方 `@opencode/cli-linux-x64` 制品并校验 npm integrity，再用固定版本 fnpack 组装 FPK。

## 环境

- Linux amd64（Windows 建议使用 WSL Ubuntu）
- Python 3.10+
- 可访问 npm registry 和 `static2.fnnas.com`
- 不需要预先安装 fnpack；脚本会下载并校验 fnpack 1.2.3

## 构建

```bash
cd apps/opencode
python3 scripts/build.py
```

默认读取：

- `VERSION`：OpenCode 版本
- `SOURCE_COMMIT`：上游 commit（写入包内 provenance）

输出：

```text
apps/opencode/dist/opencode-<version>-fnos-amd64.fpk
apps/opencode/dist/opencode-<version>-fnos-amd64.fpk.sha256
```

脚本执行内容：

1. 从 npm registry 获取 `@opencode/cli-linux-x64@<version>` 的 tarball 和 `sha512` integrity；
2. 下载并校验 tarball；
3. 确认 `package/bin/opencode` 是 x86-64 ELF；
4. 复制 `package/` 到隔离 staging，写入二进制、版本号和 provenance；
5. 下载/校验 fnpack 1.2.3，执行 `fnpack build`；
6. 校验 `manifest`、`app.tgz` MD5、内层二进制 SHA-256、图标尺寸和架构。

## 指定版本

```bash
python3 scripts/build.py --version 2.2.6
```

同时更新 `VERSION` 和 `SOURCE_COMMIT`，便于下一次默认构建。

## 离线/复用已下载文件

```bash
python3 scripts/build.py \
  --version 2.2.5 \
  --tarball /path/to/cli-linux-x64-2.2.5.tgz \
  --expected-sha512 'sha512-...' \
  --fnpack /path/to/fnpack
```

## 发布新版本

1. 更新 `VERSION`、`SOURCE_COMMIT`，运行构建；
2. 把 `dist/` 中的 `.fpk` 和 `.sha256` 上传到 GitHub Release，tag 使用 `opencode-v<version>`；
3. 更新根目录 `fnpack.json` 的 `releases.<version>.packages.x86`：
   - `download_url`
   - `sha256`
   - `size`
4. 更新 `provenance.json` 和 `README.md` 中的版本/哈希；
5. 提交并推送。

## 自更新策略

包内启动脚本设置：

```bash
OPENCODE_DISABLE_AUTOUPDATE=1
```

OpenCode 的 `/update` 和 `opencode upgrade` 只识别 curl/npm/brew/winget 等安装方式；FPK 安装不在其中，因此不会自更新。升级必须通过 FnDepot + fnOS 应用中心发布新的 FPK。
