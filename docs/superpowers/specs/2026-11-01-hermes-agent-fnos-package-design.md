# Hermes Agent fnOS 应用设计

- 日期：2026-11-01
- 状态：待评审
- 应用名：`hermes-agent`
- 上游版本：NousResearch/hermes-agent `v0.22.5`
- 目标仓库：`CrRinko/FnDepot`

## 1. 意图

在 `CrRinko/FnDepot` 中新增一个 FnDepot V2 应用 `hermes-agent`，把上游 NousResearch Hermes Agent 的最新版做成 fnOS 原生 FPK。

关键取向：

- 不做自定义 fnOS 控制台，不复制社区 fnOS 包（GPL-3.0）的代码。
- 直接运行官方 `hermes dashboard`，fnOS 应用中心点击图标即打开官方 Web UI。
- 只支持 x86_64。
- 首次启动生成随机密码，通过上游自带的密码登录页 + 签名 Cookie 会话保护 dashboard（不是 HTTP Basic 协议级认证）。
- 数据、配置、会话、技能持久化，升级 FPK 时保留。
- 提交中只出现仓库维护者 `CrRinko` 的身份；不出现上游个人账号、群二维码、手机号、NAS IP/主机名/卷 ID 等隐私信息。

**已确认：** 使用 `appname=hermes-agent` 单 app key。用户 NAS 上的社区版已卸载，不需要共存；如果未来遇到同 appname 的旧安装，按“升级并保留 `data/`”处理。

## 2. 目标

1. FnDepot 客户端能识别 `fnpack.json` 中的 `hermes-agent`，并按 x86 安装。
2. 安装完成后，应用中心可以启动、停止应用；点击图标打开 `http://<NAS-IP>:49375`。
3. 首次启动自动生成随机密码，用户名 `hermes`，密码写入 `/var/apps/hermes-agent/etc/password`；浏览器打开 dashboard 登录页后输入用户名和密码。
4. 升级后保留 `config.yaml`、`.env`、sessions、skills、memories、workspace。
5. 构建可重复：源码、Python、uv、Node、ripgrep 都有固定版本和 SHA-256 校验。
6. 发布产物可验证：FPK 的 `sha256` 与 `size` 写入 `fnpack.json`，并上传到 GitHub Release。

## 3. 非目标

- 不做中文自定义控制台、渠道扫码、模型管理面板；这些使用官方 dashboard 自带能力。
- 不支持 ARM64；本仓库当前只发布 x86。
- 不把完整 Python venv、全部 Python 依赖或 84 MB 源码包打进 FPK；GitHub Release 单文件 100 MB 限制不允许。
- 不修改上游 Hermes 源码；只在上游源码目录中放入预构建的 `web_dist`。
- 不做应用内自更新；升级只走 FnDepot + fnOS 应用中心。`install-stamp.json` 使用 `updateMechanism=external` 和 `distribution=fnos`，让上游 `hermes update` 和 dashboard 更新按钮都拒绝执行。
- 不提交 `.fpk`、源码 tarball、`node_modules`、构建缓存或 `dist/`。

## 4. 约束

### 4.1 FnDepot V2

- `fnpack.json` 的 app key 必须等于 FPK `appname`。
- `platform` 只写 `["x86"]`。
- `categories` 只能从固定列表选择，最多 2 个。
- `packages.x86.size` 是最终 FPK 的精确字节数，`sha256` 是最终 FPK 的 64 位十六进制摘要。
- `download_url` 指向 GitHub Release 资产。
- 继续使用 `run_as: "package"`、`install_type: ""`、`is_docker: false`。

### 4.2 fnOS 生命周期

- `cmd/install_init` 在应用目录不存在、且以包用户身份运行时执行，必须无副作用，不创建目录、不写密码。
- `cmd/install_callback` 在安装后执行，负责下载运行时、创建 venv、安装 Python 依赖。不同 fnOS 版本对回调执行用户的行为不一致：脚本必须同时支持 root 和包用户。`id -u == 0` 时创建目录并 `chown` 给 `$TRIM_USERNAME`；非 root 时只创建/写入当前用户可写的目录，并校验 `$TRIM_USERNAME` 与当前用户一致，绝不执行 `chown`。
- `cmd/main` 负责 start/stop/status；密码和 dashboard 配置在首次 start 时生成。如果 `install_callback` 因超时或中断没有完成运行时安装，`cmd/main start` 会在获得 `flock` 后调用 `hermes-setup` 补装，再启动。
- 升级/卸载前先停止服务，避免文件句柄和端口残留。

### 4.3 上游安装方式

- 上游不发布 wheel/sdist，只支持源码安装、Docker 或 Nix。
- 源码包约 84 MB。
- 核心依赖要求 Python 3.14；上游 `pm/lock.json` 固定 Python `3.14.9+20261021`、uv `0.13.5`、Node `26.12.1`。
- `hermes dashboard` 的前端 `hermes_cli/web_dist` 不在源码仓库中，需要用 Node/npm 构建。
- dashboard 绑定非回环地址时必须配置认证提供方，`--insecure` 不再能绕过。上游的 `dashboard.basic_auth` 是“用户名 + 密码登录页 + 签名 Cookie 会话”，不是 HTTP Basic 协议认证。
- 源码 tarball 没有 `.git`，必须写入 `install-stamp.json`，否则 `hermes --version` 会报 `unknown`。stamp 的 `updateMechanism` 设为 `external`、`distribution` 设为 `fnos`：前者声明更新由外部管理，后者让上游的 `evaluate_update_admission()` 把源码树识别为受管安装，`hermes update` 和 dashboard 更新动作都会拒绝执行。

### 4.4 构建与发布

- 构建主机：Linux amd64，Python 3.10+，可下载 Node 26 和 npm 依赖。
- FPK 使用 fnpack 1.2.3，SHA-256 固定。
- GitHub Release 单文件不能超过 100 MB。
- 首次安装需要访问 GitHub、PyPI、nodejs.org；构建机和 NAS 都需要网络。

### 4.5 许可与隐私

- 上游 Hermes Agent 为 MIT License。
- 本仓库新增的打包脚本和文档为 MIT License。
- 不复制社区 fnOS 包的 GPL-3.0 代码；只在文档中说明“参考了社区 fnOS 集成思路”，不出现个人 handle。
- 提交作者固定为 `CrRinko <9782921+CrRinko@users.noreply.github.com>`，不添加 co-author 或工具签名。
- 不提交任何真实手机号、邮箱、即时通讯群、NAS 内网 IP、主机名、卷 ID、token、API key。

## 5. 方案与选择

### 方案 A：预构建前端 + 安装时创建 Python 环境（已选择）

FPK 中包含 fnOS 生命周期脚本、预构建的 `web_dist`、图标和版本元数据。安装时下载并校验 Hermes 源码、Python 3.14.9、uv、Node、ripgrep，创建 venv，执行 `uv sync --extra all --locked`，把 `web_dist` 放入源码目录，首次启动时生成密码并启动官方 dashboard。

优点：

- FPK 小（预计 10–20 MB），不触碰 GitHub 100 MB 限制。
- 前端在发布时构建一次，NAS 上不需要 npm build，启动快且行为稳定。
- Python 依赖仍由 uv 在安装时解析，但 `uv.lock` 和 `--locked` 保证版本固定。
- 官方 dashboard 原样运行，后续升级只需要换上游版本和 `web_dist`。

缺点：

- 首次安装需要下载 84 MB 源码和约 1 GB Python 依赖，预计 10–20 分钟。
- 依赖 PyPI、GitHub、nodejs.org 的网络可达性。
- 需要维护 Python/uv/Node/ripgrep 的版本 pin 和 hash。

### 方案 B：安装时现场构建前端

FPK 只带脚本，安装时下载 Node 并执行 `npm install` + `npm run build`。

未选择：

- 安装时间明显更长，npm 依赖体积大。
- Node/npm 版本、npm registry 可达性、构建内存都会影响安装成功率。
- 前端构建失败会让整个应用无法使用，故障面比方案 A 大。

### 方案 C：把完整运行时打进 FPK

把 Python、venv、全部依赖、Node 和前端一起打包。

未选择：

- FPK 预计超过 500 MB，无法作为 GitHub Release 资产发布。
- 与 fnOS 的 glibc/架构绑定，升级和复用都差。

## 6. 架构

### 6.1 仓库目录

```text
apps/hermes-agent/
├── README.md                 # FnDepot 详情页
├── BUILD.md                  # 构建与发布说明
├── VERSION                   # 0.22.5
├── SOURCE_COMMIT             # bf0203a794a07aac3ff764972ab9087baa4e4f4e
├── provenance.json           # 固定输入、构建工具链、当前发布溯源
├── icon-256.png              # 应用图标
├── icon-64.png
├── package/                  # fnOS FPK 骨架
│   ├── manifest
│   ├── ICON.PNG
│   ├── ICON_256.PNG
│   ├── config/
│   │   ├── privilege
│   │   └── resource
│   ├── app/
│   │   ├── install-stamp.json  # 版本身份 + external 更新机制
│   │   ├── bin/
│   │   │   ├── hermes          # CLI 包装器
│   │   │   └── hermes-setup    # 安装/升级运行时
│   │   └── ui/
│   │       ├── config
│   │       └── images/{icon_256.png,icon_64.png}
│   └── cmd/                    # fnOS 生命周期脚本
└── scripts/
    └── build.py                # 下载/构建/校验/打包
```

`web_dist` 不提交到仓库，由 `build.py` 构建后放入 FPK staging 的 `app/web_dist/`。

### 6.2 运行时目录

```text
TRIM_PKGHOME=/vol1/@apphome/hermes-agent
├── data/                         # HOME 和 HERMES_HOME；卸载时保留
│   ├── config.yaml
│   ├── .env
│   ├── sessions/
│   ├── skills/
│   ├── memories/
│   └── workspace/
└── runtime/
    ├── hermes-agent-0.22.5/      # 上游源码 checkout
    │   └── install-stamp.json    # 版本身份 + external 更新机制
    ├── venv/                     # Python 3.14 venv
    ├── python/                   # Python 3.14.9 standalone
    ├── node/                     # Node 26.12.1
    ├── bin/{uv,rg}
    ├── .uv-cache/
    └── .ready                    # version/commit/web_dist hash/revision

TRIM_PKGVAR=/vol1/@appdata/hermes-agent
├── dashboard.log
├── dashboard.pid
└── install.log

TRIM_PKGETC=/var/apps/hermes-agent/etc
└── password                      # 0600，首次启动生成

TRIM_APPDEST=/var/apps/hermes-agent/target
├── app/...
└── web_dist/                     # FPK 预构建前端
```

`data/` 与 `runtime/` 分离：升级时可以安全删除并重建 `runtime/`，`data/` 始终保留。

### 6.3 安装/升级流程

`cmd/install_callback` 和 `cmd/upgrade_callback` 都调用 `app/bin/hermes-setup`。`hermes-setup` 同时支持 root 和包用户：

- `id -u == 0`：创建目录，完成后 `chown -R "$TRIM_USERNAME:$TRIM_USERNAME"` 到 `TRIM_PKGHOME`、`TRIM_PKGVAR`，`chmod` 到安全权限。
- 非 root：只创建/写入当前用户可写的目录；如果 `$TRIM_USERNAME` 存在且不等于当前用户，记录错误并失败；绝不执行 `chown`。
- 用 `${TRIM_PKGVAR}/setup.lock` + `flock` 防止 `install_callback` 和 `cmd/main start` 并发安装。

步骤：

1. 校验架构为 `x86_64`；不支持则写入 `TRIM_TEMP_LOGFILE` 并失败。
2. 创建 `TRIM_PKGHOME`、`TRIM_PKGVAR`、runtime 子目录。
3. 读取 `.ready`（如果有），比较 `version`、`commit`、`web_dist_sha256`、`packaging_revision`：
   - version/commit 相同且 `venv/bin/hermes` 存在：跳过源码、Python、venv 安装。
   - `web_dist_sha256` 不同：只替换源码里的 `hermes_cli/web_dist/` 并更新 stamp（打包修订 rN 的快速路径，不重装 1 GB 依赖）。
   - version/commit 不同：重建 `runtime/` 下的源码、Python、venv。
4. 下载 Hermes 源码 tarball，校验 SHA-256，解压到 `runtime/hermes-agent-<version>/`。
5. 把 FPK 内的 `install-stamp.json`（仓库中已提交的静态文件，构建时校验）写入源码根目录；stamp 使用 `commit=bf0203...`、`baseVersion=0.22.5`、`updateMechanism=external`、`distribution=fnos`，使 `hermes --version` 显示 `0.22.5`，并让 `hermes update` / dashboard 更新动作拒绝执行。
6. 把 `${TRIM_APPDEST}/web_dist` 复制到源码的 `hermes_cli/web_dist/`，记录其 SHA-256。
7. 下载 Python 3.14.9 standalone，校验 SHA-256，解压到 `runtime/python/`。
8. 下载 uv 0.13.5，校验 SHA-256，解压出 `uv` 到 `runtime/bin/uv`。
9. 下载 Node 26.12.1，校验 SHA-256，解压到 `runtime/node/`。
10. 下载 ripgrep 15.2.0，校验 SHA-256，解压出 `rg` 到 `runtime/bin/rg`。
11. 用 `uv venv --python runtime/python/bin/python3 runtime/venv` 创建 venv。
12. 在源码目录执行：
    ```bash
    UV_PROJECT_ENVIRONMENT="$RUNTIME/venv" \
    UV_PYTHON="$RUNTIME/python/bin/python3" \
    UV_CACHE_DIR="$RUNTIME/.uv-cache" \
    UV_CONCURRENT_DOWNLOADS=16 \
    UV_CONCURRENT_INSTALLS=8 \
    "$RUNTIME/bin/uv" sync --extra all --locked
    ```
13. 校验 `venv/bin/hermes --version` 输出包含 `0.22.5`。
14. 写入 `.ready`：
    ```text
    version=0.22.5
    commit=bf0203a794a07aac3ff764972ab9087baa4e4f4e
    web_dist_sha256=<sha256>
    packaging_revision=r0
    installed_at=<iso8601>
    ```
15. 失败时把最后几行日志写入 `TRIM_TEMP_LOGFILE`，退出非 0。

所有下载都先写 `.part`，校验通过后再原子改名。下载层内置镜像回退，不要求用户在应用中心设置环境变量：

- GitHub 资产：直连 → `ghproxy` / `gh-proxy` 等镜像，最终 SHA-256 必须一致。
- Node：`nodejs.org` → `npmmirror.com/mirrors/node`，最终 SHA-256 必须一致。
- PyPI：探测阿里云/清华/腾讯/中科大，失败回退 `https://pypi.org/simple/`；`uv.lock` 的 hash 校验仍然生效。

`HERMES_DOWNLOAD_MIRROR` 只作为手动安装/调试的可选覆盖，不是应用中心安装的必需条件。

**安装时长：** 首次安装预计 10–20 分钟，主要耗时在 `uv sync`。安装日志写入 `TRIM_PKGVAR/install.log`，并持续输出阶段标记。如果 fnOS 应用中心对 `install_callback` 有超时限制，`cmd/main start` 的补装路径会接管未完成的安装；如果补装也失败，日志会给出具体下载/依赖错误。

**从社区版升级：** 如果 NAS 上已有 `appname=hermes-agent` 的社区版，本包会被视为同 app 升级。`data/`（config、.env、sessions、skills、memories）原样保留；旧社区版的 `data/venv`、`data/node`、`data/.uv-cache`、`data/bin` 不再使用，但不会自动删除，避免误删用户数据。README 会说明可手动清理这些旧目录。

### 6.4 启动与停止

`cmd/main start`：

1. 解析 `PORT=${TRIM_SERVICE_PORT:-49375}`。
2. 确保 `TRIM_PKGHOME/data`、`TRIM_PKGVAR` 存在。
3. 如果 `runtime/.ready` 缺失或 `runtime/venv/bin/hermes` 不存在，调用 `hermes-setup` 补装（带 `flock`，非 root 时按包用户路径处理）。
4. 调用 `ensure_password`：如果 `TRIM_PKGETC/password` 不存在，生成 32 字节随机值（base64/urlsafe），写入 0600。
5. 调用 `ensure_dashboard_config`：用 venv Python 调用上游 `hermes_cli.config`，把 `dashboard.basic_auth.username=hermes`、`password_hash`、`secret` 写入 `data/config.yaml`，并确保 bundled `basic` auth 插件未被禁用；保留用户已有的 provider/model 配置。第一次启动时如果 `terminal.cwd` 为空，设置为数据共享目录（`TRIM_DATA_SHARE_PATHS` 的第一项），否则为 `data/workspace`。
6. 检查端口是否被占用；占用则记录错误并失败。
7. 启动：
   ```bash
   HOME="$DATA_DIR" \
   HERMES_HOME="$DATA_DIR" \
   PATH="$RUNTIME/venv/bin:$RUNTIME/node/bin:$RUNTIME/bin:/usr/local/bin:/usr/bin:/bin" \
   nohup "$RUNTIME/venv/bin/hermes" dashboard \
     --host 0.0.0.0 --port "$PORT" --no-open --skip-build \
     >> "$LOG_FILE" 2>&1 &
   ```
8. 写 PID 文件，最多等待 60 秒直到端口可连接；失败则终止进程并返回非 0。

`stop`：SIGTERM PID，最多等 20 秒，再 SIGKILL；同时清理子进程和 PID 文件。

`status`：PID 存活且端口可连接返回 0，否则返回 3。

`--skip-build` 使用 FPK 预置的 `hermes_cli/web_dist`，不触发 npm。

### 6.5 Dashboard 认证

- 使用上游 bundled `dashboard_auth/basic` 插件；它的行为是“用户名 + 密码登录页 + 签名 Cookie 会话”，不是 HTTP Basic 协议认证。README 和 smoke test 都按登录页处理，不能用 `curl -u` 断言。
- 用户名固定 `hermes`。
- 密码首次启动随机生成，写入 `/var/apps/hermes-agent/etc/password`（0600），README 指导用 `sudo cat` 读取。
- `dashboard.basic_auth.secret` 随机生成并写入 `config.yaml`，保证 dashboard 重启后 session 仍有效；默认 session TTL 为上游默认值（12 小时），README 说明。
- 不设置 `HERMES_DASHBOARD_BASIC_AUTH_*` 环境变量，避免和 `config.yaml` 双来源。
- 不设置 `HERMES_DASHBOARD_PUBLIC_URL`；dashboard 直接监听 `0.0.0.0:49375`。
- 不提供无认证公网访问；`--insecure` 是 no-op，不做绕过。
- 内置更新禁用：`install-stamp.json` 的 `updateMechanism=external` + `distribution=fnos`。`hermes update` 应退出 2 并提示由 fnOS/FnDepot 管理；dashboard 更新动作应返回拒绝信息。README 说明“只通过 FnDepot + 应用中心升级”。

### 6.6 FPK 元数据

`package/manifest`：

```ini
appname               = hermes-agent
version               = 0.22.5
display_name          = Hermes Agent
desc                  = ...
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

`package/app/ui/config`：

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
      "control": {"accessPerm": "readonly"}
    }
  }
}
```

`config/privilege`：`run-as=package`，用户/组 `hermes-agent`。

`config/resource`：数据共享目录 `hermes-agent`；`usr-local-linker` 暴露 `bin/hermes`。数据共享目录只用于用户文件交换，应用配置/会话的权威位置仍是 `TRIM_PKGHOME/data`。首次启动时，如果 `terminal.cwd` 为空，dashboard 的工作目录指向该共享目录。

**app key：** 已确认使用 `hermes-agent`。用户 NAS 上的社区版已卸载，不需要共存；保留同 appname 升级并保留 `data/` 的兼容行为。

### 6.7 下载 pin

| 组件 | 版本 | 来源 | SHA-256 |
| --- | --- | --- | --- |
| Hermes 源码 | v0.22.5 / `bf0203a794a07aac3ff764972ab9087baa4e4f4e` | `https://github.com/NousResearch/hermes-agent/archive/refs/tags/v0.22.5.tar.gz` | `a8f67e5ec14fea681acef6cc7ff1553f002bb6101fd2df22bfdd4b7eecc54eb2` |
| Python | 3.14.9+20261021 linux-x64 | python-build-standalone | `dfa4c5a40c47f338f41658017be550c72247c391e6bfb1fa4da03ebc8451abdf` |
| uv | 0.13.5 linux-x64 | astral-sh/uv | `f68d291c75783122dad58ab77def0e13f3233f358731db5d6d7e8715603b928f` |
| Node | 26.12.1 linux-x64 | nodejs.org | `6170b2d474e1c626f43cff3adc118df9fe3b573258a4fc3d850c8dbc6b079bbd` |
| ripgrep | 15.2.0 linux-x64 | BurntSushi/ripgrep | `33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c` |

安装脚本内置镜像回退，不需要用户在应用中心设置环境变量；所有镜像下载最终都必须通过上表的 SHA-256 校验。`HERMES_DOWNLOAD_MIRROR` 只作为手动安装/调试的可选覆盖。

PyPI：默认使用 `https://pypi.org/simple/`；安装脚本探测阿里云/清华/腾讯/中科大镜像，探测成功则设置 `UV_INDEX_URL`，失败回退官方。镜像只影响下载速度，`uv.lock` 的 hash 校验仍然生效。

### 6.8 构建脚本

`apps/hermes-agent/scripts/build.py`：

- 读取 `VERSION`、`SOURCE_COMMIT`、`provenance.json`。
- 下载源码 tarball 并校验 SHA-256。
- 校验仓库中已提交的 `package/app/install-stamp.json`：`baseVersion=0.22.5`、`commit=bf0203...`、`updateMechanism=external`。如需重新生成，可运行源码里的：
  ```bash
  python3 scripts/write_install_stamp.py \
    --output install-stamp.json \
    --commit bf0203a794a07aac3ff764972ab9087baa4e4f4e \
    --branch v0.22.5 \
    --base-version 0.22.5 \
    --distance 0 \
    --commit-date 1761187425 \
    --source fndepot \
    --update-mechanism external
  ```
  stamp 进入 FPK 的 `app/install-stamp.json`；安装时复制到源码根目录。
- 如果没有传入 `--web-dist`：
  1. 在缓存目录下载/解压 Node 26.12.1。
  2. 在源码目录执行 `npm install --workspace web --no-audit --no-fund`。
  3. 执行 `npm run build -w web`，产出 `hermes_cli/web_dist/`。
  4. 校验 `index.html` 存在，打包为 `web_dist.tar.gz` 并记录 SHA-256。
- 复制 `package/` 到 staging，写入 manifest 版本、`config/bootstrap/version.env`、`app/install-stamp.json`、`app/web_dist/`、图标。
- 下载并校验 fnpack 1.2.3，执行 `fnpack build`。
- 校验：
  - manifest 的 appname/version/platform/service_port；
  - `app.tgz` 内包含 `web_dist/index.html` 和 `install-stamp.json`；
  - `install-stamp.json` 的 `baseVersion=0.22.5`、`updateMechanism=external`；
  - `ICON.PNG` / `ICON_256.PNG` 尺寸；
  - FPK 内不含 `.git`、`node_modules`、`.env`、token、真实 IP；
  - `sha256` 和 `size`。
- 输出：
  ```text
  dist/hermes-agent-0.22.5-fnos-amd64.fpk
  dist/hermes-agent-0.22.5-fnos-amd64.fpk.sha256
  dist/provenance.generated.json
  ```
- 支持 `--artifact-suffix rN`、`--source-tarball`、`--expected-sha256`、`--web-dist`、`--fnpack`，便于离线/复用。
- 构建缓存放在 `apps/hermes-agent/.cache/`，加入 `.gitignore`。

### 6.9 发布流程

1. 构建并验证 FPK。
2. 用 `gh release create hermes-agent-v0.22.5` 创建 Release，上传 `.fpk` 和 `.sha256`。
3. 更新 `fnpack.json`：
   - `download_url`；
   - `sha256`；
   - `size`；
   - changelog / updated_at。
4. 更新 `provenance.json` 和两个 README。
5. 提交并推送。
6. 打包修订（上游版本不变）使用 `--artifact-suffix rN`，上传新资产，更新 `fnpack.json` 的 URL/hash/size，版本键不变。

### 6.10 FnDepot 元数据

- app key：`hermes-agent`
- display_name：`Hermes Agent`
- 简介：官方 dashboard、AI Agent、x86、随机密码、密码路径。
- categories：`["AI赋能", "系统工具"]`（可调整为 `["AI赋能", "编程开发"]`）。
- `service_port`：`"49375"`
- `icon_url`：`apps/hermes-agent/icon-256.png`
- `readme_url`：`apps/hermes-agent/README.md`
- `bug_report_url`：`https://github.com/CrRinko/FnDepot/issues`
- maintainer/distributor：`CrRinko`

## 7. 隐私与许可

- 新增文件只使用 `CrRinko` 作为维护者/发布者身份。
- 不出现上游个人账号、社区作者 handle、即时通讯群、真实手机号、真实邮箱、NAS 内网 IP、主机名、卷 ID。
- README 使用 `<NAS-IP>`、`<password>` 占位符。
- 上游 Nous Research 在 README/NOTICE 中署名；不复制 GPL 代码。
- `provenance.json` 只记录公开 URL、版本、commit 和 hash，不记录本机绝对路径。
- 构建缓存、源码 tarball、`node_modules`、`web_dist`、`dist/` 全部 gitignore。
- 提交前运行隐私 grep 和 `git diff` 检查；提交作者使用仓库现有 Git 身份。

## 8. 验证

### 8.1 静态检查

- `python3 -m py_compile apps/hermes-agent/scripts/build.py`
- `bash -n` 检查 `package/cmd/*` 和 `package/app/bin/*`
- `python3 -m json.tool fnpack.json`、`provenance.json`、`app/ui/config`
- `git diff --check`

### 8.2 构建验证

- 运行 `build.py`，确认 FPK 生成。
- 解包 FPK，检查 manifest、`app.tgz`、`web_dist/index.html`、图标尺寸。
- 用 `sha256sum` 和 `stat` 核对 `fnpack.json` 的 `sha256` / `size`。
- 确认 FPK 小于 100 MB。

### 8.3 运行时 smoke test

在构建机上用临时 `TRIM_*` 目录模拟 fnOS：

- 运行 `hermes-setup`（允许非 root，跳过 chown）。
- 创建 venv、安装依赖、复制 `web_dist` 和 `install-stamp.json`。
- 确认 `hermes --version` 输出 `0.22.5`，不是 `unknown`。
- 确认 `hermes update --check` 退出码为 2，输出包含 `fnos` 或“managed by its install method”，证明内置更新被拒绝。
- 启动 `hermes dashboard --host 127.0.0.1 --port <临时端口> --no-open --skip-build`。
- 验证未认证请求返回登录页/401/302；用生成的用户名和密码通过登录页表单登录，确认拿到会话 Cookie。
- 停止进程，确认端口释放。

如果完整 `--extra all` 安装过重，至少用 `--extra web` 做 dashboard 启动和认证 smoke test；正式包仍使用 `all`。

### 8.4 隐私检查

- grep 公开工具中已知的个人 handle、真实号码、邮箱、内网地址等模式（具体模式只在本机执行，不写入仓库）。
- 检查 README、provenance、build 日志中没有本机路径、内网 IP、token。
- 检查 `git log -1 --format='%an <%ae>'` 为 CrRinko。

## 9. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 首次安装 10–20 分钟、约 1 GB 依赖 | README 明确说明；安装日志写 `install.log`；失败时 `TRIM_TEMP_LOGFILE` 给出摘要；`cmd/main start` 可补装 |
| fnOS 应用中心对 `install_callback` 有超时 | 同步安装并提供补装路径；阶段日志；必要时后续改为后台任务 + 状态页 |
| GitHub 源码 tarball hash 变化 | 固定 tag + SHA-256；失败即停；内置镜像回退；提供 `--source-tarball` |
| fnOS glibc 与 Python standalone 不兼容 | 使用上游 `pm/lock.json` 同款 python-build-standalone；smoke test；失败日志明确 |
| `uv sync` 某个依赖无 wheel | 使用 `--locked` 和上游 lock；安装日志保留完整 stderr；必要时在构建机复现 |
| dashboard 密码登录插件未启用 | `ensure_dashboard_config` 显式启用 bundled 插件；smoke test 验证登录页和 Cookie |
| 上游内置更新被误触发 | `updateMechanism=external` + `distribution=fnos`；smoke test 断言 `hermes update --check` 退出 2；README 说明只走 FnDepot |
| 49375 端口冲突 | 启动前检查端口；失败日志提示修改 `service_port` 或释放端口 |
| FPK 超过 100 MB | 不打包源码/venv；只打包脚本、web_dist、图标；构建时检查大小 |
| 社区版同 appname 升级 | 保留 `data/`；旧 runtime 目录不自动删除；README 说明迁移和手动清理 |
| 打包修订 rN 仍用旧前端 | `.ready` 记录 `web_dist_sha256`；hash 变化时只替换 `web_dist` 和 stamp |
| 没有真实 fnOS 设备 | 用临时目录 smoke test；严格按 fnOS 生命周期脚本约定；README 说明已知限制 |

## 10. 留给构建者的决定

- 具体 shell 函数拆分、日志轮转和错误文案。
- 图标从上游 `assets/icon-master.svg` 渲染还是使用已有 PNG。
- 是否额外安装 ffmpeg（默认不装，Hermes 可 lazy-install）。
- PyPI 镜像候选列表和探测超时。
- categories 最终选 `系统工具` 还是 `编程开发`。
- 构建缓存目录的具体布局。

## 11. 评审问题处理记录

独立 builder review 提出的 8 个问题及处理：

1. **回调执行用户**：脚本同时支持 root 和包用户；root 时 `chown`，非 root 时只写当前用户可写目录并校验 `TRIM_USERNAME`。`cmd/main start` 可补装。
2. **是否替换社区版**：已确认使用 `appname=hermes-agent`；用户 NAS 上的社区版已卸载，不需要共存。未来遇到旧安装时按同 appname 升级、保留 `data/`、旧 runtime 目录不自动删除。
3. **HTTP Basic 还是登录页**：上游是密码登录页 + 签名 Cookie 会话，不是 HTTP Basic；已修正设计、README 和 smoke test。
4. **安装回调超时**：同步安装 + 阶段日志；`cmd/main start` 提供补装路径；如果 fnOS 明确限制超时，后续改为后台任务。
5. **`.ready` 是否包含 revision/web_dist hash**：包含 `version`、`commit`、`web_dist_sha256`、`packaging_revision`；rN 只替换前端和 stamp。
6. **数据根与卸载**：权威数据根是 `TRIM_PKGHOME/data`；数据共享目录用于用户文件交换；卸载不主动删除 `data/`，README 给出备份/清理命令。
7. **镜像环境变量**：安装脚本内置镜像回退，不依赖应用中心环境变量；`HERMES_DOWNLOAD_MIRROR` 仅用于手动调试。
8. **install-stamp**：仓库提交静态 `install-stamp.json`（`baseVersion=0.22.5`、`updateMechanism=external`、`distribution=fnos`），构建时校验，安装时复制到源码根目录；修复 `hermes --version=unknown`，并让 `hermes update` / dashboard 更新动作拒绝执行。
