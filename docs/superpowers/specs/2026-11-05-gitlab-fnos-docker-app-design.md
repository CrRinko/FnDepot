# GitLab fnOS Docker 应用设计

日期：2026-11-05

## 1. 目标

把 GitLab CE 封装成 fnOS 应用中心的 Docker 应用，安装后：

- 直接运行官方 `gitlab/gitlab-ce` 镜像，不自建控制台。
- 通过应用设置修改对外访问域名和 HTTPS 端口，默认启用 HTTPS。
- 优先复用 fnOS 已有的 Let's Encrypt 证书；测试环境默认会选中 `<nas-domain>`，但该域名不写入仓库和发布物。
- 数据持久化在应用数据目录，升级 FPK 不丢数据。
- 由 FnDepot/应用中心负责安装、启动、停止、升级和卸载。

## 2. 非目标

- 不自动申请新的 Let's Encrypt 证书，不管理 DNS API Token。
- 不配置路由器端口转发、公网防火墙、Tailscale、Cloudflare Tunnel。
- 不内置 GitLab Runner、SMTP、对象存储、外部 PostgreSQL/Redis。
- 不做高可用、集群、备份调度。
- 不修改 fnOS 系统证书、nginx 配置或 `/usr/trim` 下的文件。

## 3. 约束与事实

### 3.1 设备

- fnOS `1.2.0800`，x86_64，4 核，内存 15.7GB（可用约 12.5GB）。
- Docker 28.5.2，Compose v2.40.3，data-root `/vol1/docker`，`/vol1` 剩余 2.3TB。
- 80/443 被 fnOS 系统 Web 服务占用，应用不能绑定 443。
- 测试环境的 NAS 域名解析到 Tailscale 地址，HTTPS 证书校验通过；具体域名和地址不写入仓库。

### 3.2 可用证书

fnOS 在 `/usr/trim/etc/network_cert_all.conf` 维护证书列表。真实样本（已脱敏）结构为 JSON 数组：

```json
[
  {
    "domain": "<nas-domain>",
    "san": ["<nas-domain>"],
    "certificate": "/usr/trim/var/trim_connect/ssls/<nas-domain>/<ts>/<nas-domain>.crt",
    "fullchain": "/usr/trim/var/trim_connect/ssls/<nas-domain>/<ts>/fullchain.crt",
    "privateKey": "/usr/trim/var/trim_connect/ssls/<nas-domain>/<ts>/<nas-domain>.key",
    "validFrom": 1793504521000,
    "validTo": 1801280520000,
    "sum": "...",
    "used": true,
    "appFlag": 14
  },
  {
    "domain": "fnOS",
    "san": ["fnOS"],
    "certificate": "/usr/trim/var/trim_connect/ssls/fnOS/<ts>/fnOS.crt",
    "fullchain": "",
    "privateKey": "/usr/trim/var/trim_connect/ssls/fnOS/<ts>/fnOS.key",
    "validFrom": 1793398992000,
    "validTo": 1801347792000,
    "sum": "...",
    "used": false,
    "appFlag": 0
  }
]
```

字段约定：

- `san` 是字符串数组，可能包含 DNS 名称和通配符（`*.example.com`）。
- `validTo` 是毫秒时间戳。
- `used` 是布尔值。
- `fullchain` 可能为空，此时使用 `certificate`。
- 路径是绝对路径。
- 测试环境中的 Let's Encrypt 证书覆盖 `<nas-domain>`，fnOS 自签证书只覆盖 `fnOS`。

### 3.3 fnOS Docker 应用契约

- 包结构：`manifest`、`app/docker/docker-compose.yaml`、`app/ui/config`、`cmd/` 九个生命周期脚本、`config/privilege`、`config/resource`、`wizard/`。
- `config/resource` 的 `docker-project.name` 必须与 compose 项目名一致：`gitlab`。
- `wizard/install` 和 `wizard/config` 的字段会作为环境变量传给生命周期脚本；`config_callback` 在应用设置保存后执行。
- 真机验证（fnOS 1.2.0800）：`cmd/main` 以 root 运行，可操作 Docker；`config_callback` 以包用户运行，不应依赖 Docker 权限。
- `app/ui/config` 的 `port` 支持 `${HTTP_PORT}` 这类向导变量。
- Docker 项目由应用中心按 `config/resource` 启动；`cmd/main` 负责兜底同步配置和状态。
- 应用中心可能在回调前后启动 compose 项目，因此所有运行时配置都必须能由 root 侧的 `cmd/main` 再次修正。

### 3.4 GitLab 镜像

- 版本：`19.5.3`，镜像 `gitlab/gitlab-ce:19.5.3-ce.0`。
- amd64 摘要：`sha256:60fc37e470aca439ead4b6e3ed8f578d9e85c954b84b611b5f323a32a9e47615`。
- 压缩后约 1.65GB，首次启动需要拉取镜像并执行 `gitlab-ctl reconfigure`。

## 4. 方案选择

### 方案 A：应用自带 HTTPS，复用 fnOS 证书（采用）

应用读取 fnOS 证书列表，选择匹配域名的证书，复制到应用配置卷，GitLab 自带 nginx 在该端口上终止 TLS。默认 HTTPS，HTTP 只做 301 跳转。

- 优点：自包含；直接复用已有 Let's Encrypt 证书；不需要额外反代或 DNS Token。
- 缺点：HTTPS 使用非标准端口；证书只覆盖其 SAN 中的域名，换域名需要 fnOS 里有匹配证书。

### 方案 B：只做 HTTP 后端，HTTPS 交给现有反代

应用监听 `8929`，由 Lucky/fnOS/Cloudflare 在 443 终止 TLS。

- 优点：地址无端口、可直接复用 443 上的泛域名证书。
- 缺点：依赖外部反代；应用无法独立保证 HTTPS；桌面入口在 LAN 直连时仍是 HTTP。

### 方案 C：自带 Caddy + DNS-01 自动证书

设置 DNS 服务商和 API Token，Caddy 自动申请和续期证书。

- 优点：全自动受信任证书。
- 缺点：需要定制 Caddy 镜像、保管 DNS Token、维护额外组件；超出当前需求。

**决定：采用 A。** B 和 C 作为后续可选项，不在第一版实现。

## 5. 应用身份与打包

| 项目 | 值 |
| --- | --- |
| appname | `gitlab` |
| 显示名 | `GitLab` |
| 应用版本 | `19.5.3`（打包修订时递增为 `19.5.3.1`） |
| 上游版本 | `19.5.3` |
| 架构 | `x86` |
| 分类 | 编程开发、系统工具 |
| `is_docker` | `true` |
| `service_port` | `8443`（默认值；实际端口由设置决定） |
| `checkport` | `false`（端口由向导动态决定，避免应用中心检查固定端口） |
| `os_min_version` | `1.2.0800`（仅在 1.2.0800 验证） |
| 运行身份 | `package`，用户名/组名 `docker-gitlab`，加入 `docker` 组 |
| 数据目录 | `${TRIM_PKGVAR}`（`/vol1/@appdata/gitlab`） |

目录：

```text
apps/gitlab/
├── APP_VERSION
├── VERSION
├── provenance.json
├── README.md
├── BUILD.md
├── icon-64.png
├── icon-256.png
├── package/
│   ├── manifest
│   ├── ICON.PNG
│   ├── ICON_256.PNG
│   ├── app/
│   │   ├── bin/
│   │   │   ├── gitlab-config.py
│   │   │   └── select-cert.py
│   │   ├── docker/docker-compose.yaml
│   │   └── ui/
│   │       ├── config
│   │       └── images/{icon_64.png,icon_256.png}
│   ├── cmd/（9 个脚本）
│   ├── config/{privilege,resource}
│   └── wizard/{install,config,uninstall}
└── scripts/build.py
```

FPK 不包含 GitLab 镜像，只包含 compose、脚本、图标和配置，体积应在几十 KB 级别。仓库和 FPK 中不得出现测试 NAS 的域名、Tailscale/IP 或私钥。

## 6. 运行架构

### 6.1 Compose

项目名 `gitlab`，单服务 `gitlab`：

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

- `8443` 是 HTTPS，`8080` 只用于跳转到 HTTPS，`2224` 是 Git over SSH。
- 端口均可通过应用设置修改；默认值避开 fnOS 的 80/443/22。
- 数据卷使用 `${TRIM_PKGVAR}`，避免用户目录权限问题。

### 6.2 GitLab 配置

应用在 `${TRIM_PKGVAR}/config/gitlab.rb` 生成配置，容器启动时由官方 entrypoint 执行 `gitlab-ctl reconfigure`：

```ruby
external_url 'https://<domain>:<https_port>'
gitlab_rails['nginx']['listen_port'] = <https_port>
gitlab_rails['nginx']['listen_https'] = true
gitlab_rails['nginx']['ssl_certificate'] = "/etc/gitlab/ssl/gitlab.crt"
gitlab_rails['nginx']['ssl_certificate_key'] = "/etc/gitlab/ssl/gitlab.key"
gitlab_rails['nginx']['redirect_http_to_https'] = true
gitlab_rails['nginx']['redirect_http_to_https_port'] = 80
gitlab_rails['gitlab_shell_ssh_port'] = <ssh_port>
gitlab_rails['time_zone'] = '<time_zone>'
letsencrypt['enable'] = false
puma['worker_processes'] = 2
sidekiq['concurrency'] = 6
prometheus_monitoring['enable'] = false
gitlab_kas['enable'] = false
postgresql['shared_buffers'] = "512MB"
redis['maxmemory'] = "512mb"
```

说明：

- GitLab 19.2 起 per-service nginx 配置迁移到 `gitlab_rails['nginx']`；使用新键，避免依赖已弃用的顶层 `nginx`。
- `external_url` 的端口、`listen_port` 和 compose 端口映射保持一致，均为用户配置的 `HTTPS_PORT`。
- HTTP 80 只监听跳转；跳转目标由 GitLab 模板使用 external_url 的 host 和 port 生成，因此会跳到 `https://<domain>:<HTTPS_PORT>`。
- 关闭内置 Let's Encrypt，避免在 80/443 被占用时尝试 ACME。
- 关闭 Prometheus 和 KAS，限制 Puma/Sidekiq/PostgreSQL/Redis 资源，适配 4 核/12.5GB 可用内存。

### 6.3 访问入口

- 规范地址：`https://<GITLAB_DOMAIN>:<HTTPS_PORT>`。
- 应用桌面入口：`protocol: http`、`port: ${HTTP_PORT}`、`url: /`，点击后由 GitLab 301 到规范 HTTPS 地址。这样桌面图标不会因为 NAS IP 与证书域名不一致而先弹证书警告。
- 如果实测跳转没有使用 external_url 的域名/端口，则回退为 `protocol: https`、`port: ${HTTPS_PORT}`，并在 README 说明可在应用设置中自定义 URL。
- 由于 443 被 fnOS 占用，第一版不支持无端口地址；需要标准 443 时走方案 B。

## 7. 应用设置

`wizard/install` 和 `wizard/config` 使用同一组字段：

| 字段 | 标签 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `GITLAB_DOMAIN` | 对外访问域名 | 空 | 只填主机名，不带 `https://` 和端口；留空时自动使用 fnOS 当前证书的域名，否则使用 NAS IP。测试环境会自动得到 `<nas-domain>`，但该值不写入包 |
| `HTTPS_PORT` | HTTPS 端口 | `8443` | 1–65535，不能是 80/443/22，不能与其他端口重复 |
| `HTTP_PORT` | HTTP 跳转端口 | `8080` | 只用于 301 到 HTTPS |
| `SSH_PORT` | Git SSH 端口 | `2224` | 映射到容器 22 |
| `TIME_ZONE` | 时区 | `Asia/Shanghai` | 写入 GitLab 配置 |

`wizard/uninstall` 增加：

| 字段 | 标签 | 默认值 |
| --- | --- | --- |
| `wizard_data_action` | 卸载时数据 | `keep`（保留）/ `delete`（删除） |

设置保存后的行为：

1. `config_callback` 校验域名和端口，重新选择/复制证书，原子写入 `gitlab.rb` 和 `settings.env`。
2. 应用中心重启应用；`cmd/main` 比较配置哈希，必要时 `docker restart gitlab` 使 `external_url`/端口生效。
3. 如果只更换了证书内容（例如 fnOS 续期），`cmd/main` 复制新证书后执行 `gitlab-ctl hup nginx`，不重启容器。
4. 如果新域名在 fnOS 证书库中没有匹配证书，应用为该域名生成自签名证书，并在日志和 README 中提示；不会把其他域名的证书用于不匹配的新域名。

### 7.1 配置校验与回退

- `settings.env` 保存最后一次校验通过的配置，是运行时权威来源。
- `config_callback` 先校验；校验失败时写 `TRIM_TEMP_LOGFILE` 并退出 1，不更新 `settings.env`。
- `cmd/main` 每次启动/状态检查都重新校验环境变量；非法时回退到 `settings.env`，保证服务不被一次错误保存弄坏。
- 端口检查：与当前配置相同的端口跳过“已被本应用占用”检查；变更后的端口才做占用检测。80/443/22 永远拒绝。
- 域名校验：只允许主机名或 IPv4，不允许协议前缀、斜杠、端口、`..`；空值走自动检测。

## 8. 证书选择

### 8.1 优先级

`select-cert.py` 读取 `${GITLAB_CERT_STORE:-/usr/trim/etc/network_cert_all.conf}`：

1. 如果 `GITLAB_DOMAIN` 非空：选择 `domain` 或 `san` 与该域名匹配、且未过期的证书。匹配顺序：精确 SAN → 通配符 SAN（`*.example.com` 匹配一层子域）→ `domain` 字段。多条时优先 `used: true`，再按 `validTo` 最新。
2. 如果 `GITLAB_DOMAIN` 为空：优先选择 `used: true` 且域名不是 `fnOS` 的证书；否则选择任意非 `fnOS`、未过期、`validTo` 最新的证书；该证书的域名成为 GitLab 域名。
3. 没有匹配/可用的非 `fnOS` 证书：为最终域名生成自签名证书（DNS SAN 或 IP SAN）。
4. 不直接使用 `fnOS` 自签证书作为 GitLab 证书，因为其 SAN 只有 `fnOS`，必然产生主机名不匹配。

在当前测试环境，默认域名留空时，第 2 步会选中 `used: true` 的 Let's Encrypt 证书，最终地址为 `https://<nas-domain>:8443`。

### 8.2 复制与续期

- 证书：优先 `fullchain`，没有则 `certificate`；私钥：`privateKey`。
- 复制到 `${TRIM_PKGVAR}/config/ssl/gitlab.crt` 和 `gitlab.key`，权限 `600`。
- 写入 `${TRIM_PKGVAR}/cert-source.json`：来源域名、源路径、有效期、SHA-256。
- `cmd/main status` 每次运行都重新解析证书库；源证书 SHA-256 变化时重新复制并 `docker exec gitlab gitlab-ctl hup nginx`。
- 源文件不可读或解析失败：保留现有证书；没有现有证书时生成自签名证书，并写日志。
- 不修改、不删除 fnOS 的证书文件。

### 8.3 自签名证书

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
  -keyout gitlab.key -out gitlab.crt \
  -subj "/CN=<domain>" \
  -addext "subjectAltName=DNS:<domain>"   # 或 IP:<ip>
```

仅作为回退；README 说明如何通过 fnOS 证书库换成受信任证书。

### 8.4 测试钩子

`GITLAB_CERT_STORE` 环境变量可指向测试用 fixture JSON。fixture 中的证书/私钥指向临时文件，用于安全模拟证书续期，不修改生产证书。该变量不暴露在应用设置中。

## 9. 生命周期脚本

### 9.1 install_init

无操作。不得创建 `TRIM_PKGETC`/`TRIM_PKGVAR`/`TRIM_PKGHOME`，避免 fnOS 安装前权限失败。

### 9.2 install_callback

以包用户运行：

- 校验 `GITLAB_DOMAIN`、端口范围、端口互斥和占用。
- 创建 `${TRIM_PKGVAR}/{config,config/ssl,logs,data}`。
- 调用 `select-cert.py` 选择/复制证书；失败则生成自签名。
- 调用 `gitlab-config.py` 渲染 `gitlab.rb` 和 `settings.env`。
- 将规范化后的访问地址写入 `TRIM_TEMP_LOGFILE` 或安装日志。
- 如果目录被 root 或 Docker 提前创建、导致包用户无法写入：记录警告并退出 0，由 `cmd/main`（root）修复，不让安装失败。

### 9.3 config_callback

与 `install_callback` 相同的配置生成逻辑，但不执行 Docker 命令。配置保存后由应用中心重启应用，`cmd/main` 负责最终生效。

### 9.4 upgrade_callback

重新选择证书、重新渲染配置；保留 `${TRIM_PKGVAR}/data`、`config`、`logs`。不执行破坏性迁移。

### 9.5 main

- `start`：`sync_config`，然后 `docker compose -p gitlab up -d`，检查容器状态。
- `stop`：`docker compose -p gitlab stop`。
- `status`：
  1. 以 root 修正 `${TRIM_PKGVAR}/config`、`config/ssl` 和 `settings.env` 的属主，使包用户可写；不要递归修改 `data`/`logs`（由 GitLab 容器管理）。
  2. `sync_config`：读取环境变量或 `settings.env`，校验；非法时回退到 `settings.env`；重新选择证书；渲染 `gitlab.rb`；比较哈希。
  3. 如果配置哈希变化：`docker compose up -d` 后 `docker restart gitlab`。
  4. 如果仅证书变化：`gitlab-ctl hup nginx`。
  5. 如果容器未运行：`docker compose up -d`。
  6. 复制首次 root 密码到 `${TRIM_PKGVAR}/initial_root_password.txt`（仅首次，权限 600）。
  7. 容器运行返回 0，否则返回 3。
- `sync_config` 失败时写 `TRIM_TEMP_LOGFILE` 并返回 1。

### 9.6 uninstall

- `uninstall_init`：停止 compose 项目（尽力而为）。
- `uninstall_callback`：`wizard_data_action=delete` 时清空 `${TRIM_PKGVAR}` 内容；`keep` 时保留。不要删除平台管理的目录本身。

## 10. 安全与隐私

- 不把私钥、证书、密码、测试 NAS 域名/IP 写入 FPK、仓库或日志。
- `gitlab.rb` 和 `settings.env` 权限 600；证书私钥 600。
- 应用设置中的域名和端口再次校验，拒绝 `..`、斜杠、协议前缀和非法端口。
- 不暴露 Docker socket 给容器；生命周期脚本通过宿主机 Docker 操作。
- GitLab 只暴露 8443/8080/2224；8080 仅跳转。
- 首次 root 密码复制到应用数据目录，文档提示登录后立即修改。
- 不修改 fnOS 系统证书和 nginx 配置，只读取证书库。
- 由于 GitLab 与 fnOS 使用同一主机名（不同端口），Cookie 按主机共享；GitLab 使用 `_gitlab_session`，与 fnOS 会话 Cookie 名称不同。README 提示如遇冲突可改用独立子域名并配置匹配证书。

## 11. 资源与容量

- `mem_limit: 8g`，为 NAS 保留约 4GB 余量。
- Puma 2 workers、Sidekiq 6、PostgreSQL shared_buffers 512MB、Redis maxmemory 512MB。
- 关闭 Prometheus、KAS。
- GitLab 数据会持续增长；README 说明备份命令和容量监控：
  `docker exec gitlab gitlab-backup create`，备份位于 `${TRIM_PKGVAR}/data/backups`。
- 首次拉取镜像约 1.65GB，首次 reconfigure 约 5–15 分钟，取决于网络和磁盘。

## 12. 测试计划

### 12.1 构建与静态检查

- `python3 scripts/build.py --check-only`：manifest、compose、wizard JSON、脚本可执行位、图标尺寸、隐私扫描。
- `fnpack build` 产物结构校验：`manifest`、`checksum`、`config/resource` 项目名、`wizard` JSON。
- 确认 FPK 不包含证书、私钥、密码或 `.cache`，也不包含测试 NAS 的域名/IP。

### 12.2 NAS 安装

- 通过应用中心安装 FPK，观察镜像拉取和首次 reconfigure。
- `docker compose ls` 显示项目 `gitlab`；`docker ps` 容器运行。
- `https://<nas-domain>:8443` 返回登录页，`curl` 校验证书结果为 0。
- `http://<NAS-IP>:8080` 301 到 `https://<nas-domain>:8443`。
- `ssh -p 2224 git@<nas-domain>` 返回 GitLab 欢迎信息。
- 读取 `${TRIM_PKGVAR}/initial_root_password.txt`，用 root 登录，确认页面正常。
- `gitlab-ctl status` 关键服务正常。

### 12.3 设置变更

- 将 `HTTPS_PORT` 从 8443 改为 8444：保存 → 容器重建 → 8444 可访问、8443 关闭；再改回。
- 将 `GITLAB_DOMAIN` 改为另一个域名：确认生成匹配的自签证书或提示缺少证书；再改回自动检测，确认重新使用 Let's Encrypt 证书。
- 修改 `SSH_PORT`，确认 `gitlab_shell_ssh_port` 和映射同步。
- 保存非法端口/重复端口，确认有清晰错误、`settings.env` 不变、现有容器继续可用。

### 12.4 生命周期

- 应用中心停止/启动，数据保留。
- 升级到打包修订版本，容器重建，仓库和用户数据保留。
- 卸载选择保留/删除数据，行为符合预期。
- 使用 `GITLAB_CERT_STORE` fixture 模拟证书续期：替换 fixture 中的证书/私钥，确认应用在 30 秒内重载且不修改生产证书。

## 13. 风险与回退

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| 应用中心先启动 compose，包用户无法写配置 | 首次配置错误或安装失败 | `cmd/main` 以 root 修正 `config`/`config/ssl` 和 `settings.env` 的属主并重写配置；不递归改 `data`/`logs`；install_callback 写入失败不阻断安装 |
| fnOS 证书库格式/权限变化 | 无法读取系统证书 | 保留自签名回退；`cmd/main` 以 root 读取；README 说明手动放置证书 |
| 8443 端口被占用 | 启动失败 | install/config 预检，给出明确错误 |
| 镜像拉取失败/超时 | 首次安装失败 | 文档说明重试；可使用 NAS 的 registry mirror；不把镜像打进 FPK |
| 同一主机名不同端口 Cookie 冲突 | 登录异常 | 实测；README 建议独立子域名 + 匹配证书 |
| 内存不足 | 服务被 OOM | 8G 限制、关闭 Prometheus/KAS、Puma/Sidekiq 降配 |
| 直接跳过 GitLab 大版本升级 | 数据不兼容 | README 要求按 GitLab 官方升级路径逐版本升级 |
| HTTP 跳转未使用 external_url | 桌面入口跳到错误地址 | 测试；回退为 HTTPS 入口并说明自定义 URL |

## 14. 已确定的实现决定

- CE 版，固定 `19.5.3-ce.0`，不使用 `latest`。
- 默认域名字段留空，自动使用 fnOS 证书域名；测试环境会得到 `<nas-domain>` 并选中其 Let's Encrypt 证书，但发布物不写死该域名。
- 默认 HTTPS 端口 `8443`，HTTP 跳转 `8080`，SSH `2224`；访问地址可通过应用设置修改。
- 证书优先匹配配置域名，其次是 fnOS 当前启用的非 `fnOS` 证书，没有则生成自签名。
- `os_min_version=1.2.0800`，`checkport=false`。
- 数据放 `${TRIM_PKGVAR}`，卸载默认保留。
- 第一版不做 SMTP、Runner、自动备份、自动申请证书。
