# OpenCode V2 for fnOS

OpenCode V2 的 fnOS amd64 安装包，基于上游 **v2.2.5** 的 linux-amd64 制品构建。

## 版本与来源

| 项目 | 值 |
| --- | --- |
| 应用版本 | 2.2.5 |
| 目标架构 | amd64（manifest `platform=x86`） |
| 上游仓库 | https://github.com/anomalyco/opencode |
| 上游 commit | `9bbb8ce18c80f099e0e448775f59d965ead40a21` |
| 二进制来源 | `@opencode/cli-linux-x64@2.2.5` |
| 二进制 SHA-256 | `8d060e1d2fbb9bb44cf09ae6ed1f3f6a7cff070b5227e2f90970132b23a92050` |
| FPK SHA-256 | `bb71ae09b18925293f795e1494185aff2ae193ce3b36bf939998bfe9309f7242` |
| FPK 大小 | 121,155,364 字节 |

## 安装

在 FnDepot 中添加源 `https://github.com/CrRinko/FnDepot`，选择 **OpenCode V2** 安装。

安装包直接下载：

```text
https://github.com/CrRinko/FnDepot/releases/download/opencode-v2.2.5/opencode-2.2.5-fnos-amd64.fpk
```

校验：

```bash
sha256sum opencode-2.2.5-fnos-amd64.fpk
# bb71ae09b18925293f795e1494185aff2ae193ce3b36bf939998bfe9309f7242
```

## 使用

安装后在 fnOS 应用中心启动 **OpenCode V2**。

- Web UI：`http://<NAS-IP>:49374`
- 用户名：`opencode`
- 密码：安装时随机生成，保存在 `/var/apps/opencode/etc/password`

```bash
cat /var/apps/opencode/etc/password
```

默认工作区是共享目录 `opencode/projects`：

```text
/var/apps/opencode/share/projects
```

把代码仓库放到该目录即可。也可以在 fnOS 应用设置中授权其他目录，OpenCode 的工具会在权限允许时访问。

命令行：

```bash
/var/apps/opencode/target/bin/opencode --help
```

连接正在运行的 Web 服务：

```bash
OPENCODE_PASSWORD="$(cat /var/apps/opencode/etc/password)" \
  /var/apps/opencode/target/bin/opencode \
  --server http://127.0.0.1:49374
```

## 数据与日志

```text
/var/apps/opencode/home              配置、认证与会话数据
/var/apps/opencode/var/opencode.log  服务日志
```

## 安全说明

- 服务监听所有网卡的 `49374` 端口，使用 HTTP Basic Auth 保护 API。
- Web UI 根页面本身不要求认证，但所有 `/api/*` 请求都需要密码。
- 不要把 `49374` 端口直接暴露到公网；远程访问请使用 VPN 或 fnOS 反向代理。
- 应用以专用用户 `opencode` 运行，不使用 root。

## 说明

本包是第三方打包，不是 OpenCode 官方发布。OpenCode 上游采用 MIT License。
