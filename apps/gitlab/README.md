# GitLab for fnOS

GitLab CE `19.5.3` 的 fnOS x86_64 Docker 应用包。直接运行官方
`gitlab/gitlab-ce:19.5.3-ce.0` 镜像，不自建控制台，数据保存在 fnOS 应用数据目录。

> 这是第三方社区打包，不是 GitLab Inc. 官方发布。GitLab 是 GitLab Inc. 的商标。

## 版本与来源

| 项目 | 值 |
| --- | --- |
| 应用版本 | 19.5.3.1（打包修订 r1） |
| 上游版本 | GitLab CE 19.5.3 |
| 镜像 | `gitlab/gitlab-ce:19.5.3-ce.0` |
| amd64 摘要 | `sha256:60fc37e470aca439ead4b6e3ed8f578d9e85c954b84b611b5f323a32a9e47615` |
| 架构 | x86_64 |
| FPK SHA-256 | `4fce07f9622f5355b7085a40547888bf61312f465066ae200710bc82a61914b8` |
| FPK 大小 | 38,430 字节 |
| 最低 fnOS | 1.2.0800 |

打包修订 r1 修复了 HTTPS 证书链：优先复制 fnOS 证书的 fullchain，避免只发送叶子证书导致中间证书缺失。

## 安装

在 FnDepot 中添加源 `https://github.com/CrRinko/FnDepot`，选择 **GitLab** 安装。

直接下载：

```text
https://github.com/CrRinko/FnDepot/releases/download/gitlab-v19.5.3.1/gitlab-19.5.3.1-fnos-amd64-r1.fpk
```

首次安装需要从镜像仓库拉取约 1.65GB 的镜像，首次启动还会执行
`gitlab-ctl reconfigure`，通常需要 5–15 分钟。安装日志：

```text
/vol1/@appdata/gitlab/install.log
/vol1/@appdata/gitlab/control.log
```

## 访问

默认地址由应用设置决定：

```text
https://<对外域名>:8443
```

- 域名留空时，应用会自动使用 fnOS 当前证书的域名；没有可用证书时使用 NAS IP。
- HTTPS 默认端口 `8443`。fnOS 自身占用 80/443，所以第一版使用非标准端口。
- HTTP 端口 `8080` 只用于 301 跳转到 HTTPS。桌面图标会走这个入口，避免用 NAS IP 访问时出现证书域名不匹配的警告。
- Git over SSH 默认端口 `2224`。

### 修改访问地址

应用设置中可以修改：

| 设置 | 默认值 | 说明 |
| --- | --- | --- |
| 对外访问域名 | 空（自动） | 只填主机名，不带 `https://` 和端口 |
| HTTPS 端口 | 8443 | GitLab HTTPS 端口 |
| HTTP 跳转端口 | 8080 | 只做 301 跳转 |
| Git SSH 端口 | 2224 | 映射到容器 22 |
| 时区 | Asia/Shanghai | GitLab 和容器时区 |

保存后应用会重新渲染 `gitlab.rb` 并重建 GitLab 容器。非法端口、重复端口、
80/443/22 会被拒绝；失败不会覆盖上一次可用配置。

## 登录

- 用户名：`root`
- 初始密码：首次启动后由 GitLab 生成，应用会复制到：

```text
/vol1/@appdata/gitlab/initial_root_password.txt
```

也可以查看 GitLab 容器内的 `/etc/gitlab/initial_root_password`。该初始密码只应使用一次，
登录后请立即修改。

## 证书

应用读取 fnOS 的证书列表 `/usr/trim/etc/network_cert_all.conf`：

1. 优先使用与“对外访问域名”匹配的证书（精确 SAN 或通配符 SAN）。
2. 域名留空时，优先使用 fnOS 当前启用的非 `fnOS` 证书，其次使用最新的非 `fnOS` 证书。
3. 没有可用证书时，为最终域名生成自签名证书。

证书和私钥会复制到应用自己的配置卷：

```text
/vol1/@appdata/gitlab/config/ssl/gitlab.crt
/vol1/@appdata/gitlab/config/ssl/gitlab.key
```

fnOS 证书续期后，应用会在下一次状态检查时自动重载 GitLab 的 nginx。
应用不会修改或删除 fnOS 的证书文件。

如果修改域名后没有匹配证书，应用会为新域名生成自签名证书，而不会把其他域名的
Let's Encrypt 证书用于不匹配的主机。要在新域名上使用受信任证书，请先在 fnOS
中为该域名配置证书。

## 数据与备份

```text
/vol1/@appdata/gitlab/config  GitLab 配置、密钥、证书
/vol1/@appdata/gitlab/data    仓库、数据库、上传文件、备份
/vol1/@appdata/gitlab/logs    日志
```

备份：

```bash
docker exec gitlab gitlab-backup create
```

备份默认写入 `/vol1/@appdata/gitlab/data/backups`。备份不包含
`/etc/gitlab` 中的配置和密钥，建议同时备份 `config` 目录。

## 升级

只通过 **FnDepot + fnOS 应用中心**升级。应用内 `gitlab-ctl upgrade` 或镜像
`latest` 不受支持。

GitLab 大版本不能跳级升级。跨大版本时，请按 GitLab 官方升级路径逐版本升级；
小版本和打包修订可以直接升级。升级 FPK 会重建容器，但保留
`/vol1/@appdata/gitlab` 下的数据。

## 卸载

在应用中心卸载时可以选择：

- **保留数据**（默认）：重新安装后可继续使用仓库和用户。
- **删除数据**：清空 `/vol1/@appdata/gitlab` 内容。

## 资源

- 默认内存上限 8GB；Puma 2 workers、Sidekiq 6。
- 关闭内置 Prometheus 和 KAS，降低内存占用。
- 镜像约 1.65GB，数据容量取决于仓库和附件规模。

## 安全

- 不要把 `8443`、`8080` 或 `2224` 直接暴露到公网；远程访问请使用 VPN、Tailscale
  或受控的反向代理。
- 登录后立即修改 `root` 密码，并启用双因素认证。
- 应用与 fnOS 可能使用同一主机名的不同端口，Cookie 按主机共享；如遇登录冲突，
  建议为 GitLab 使用独立子域名，并在 fnOS 中配置匹配的证书。
- 初始密码文件权限为 0600，不要提交到仓库或发送到聊天中。

## 说明

打包脚本和文档采用 MIT License；GitLab CE 上游同样采用 MIT License。
详见 `NOTICE`。
