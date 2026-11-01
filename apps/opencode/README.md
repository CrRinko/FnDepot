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
| FPK SHA-256 | `7a348547346b6cd78237ef7b187c7ec25083c660986624044dc11d997f8dd824` |
| FPK 大小 | 121,154,901 字节 |

## 安装

在 FnDepot 中添加源 `https://github.com/CrRinko/FnDepot`，选择 **OpenCode V2** 安装。

安装包直接下载：

```text
https://github.com/CrRinko/FnDepot/releases/download/opencode-v2.2.5/opencode-2.2.5-fnos-amd64-r2.fpk
```

校验：

```bash
sha256sum opencode-2.2.5-fnos-amd64-r2.fpk
# 7a348547346b6cd78237ef7b187c7ec25083c660986624044dc11d997f8dd824
```

## 登录 WebUI

- 默认用户名：`opencode`
- 默认密码：没有固定默认密码，首次启动时随机生成
- 获取密码：密码文件权限为 `0600`，属主是 `opencode`，普通用户无法直接读取。SSH 登录 NAS 后以 root 权限执行：

```bash
sudo cat /var/apps/opencode/etc/password
```

也可以先执行 `su -` 切换到 root，再执行 `cat /var/apps/opencode/etc/password`。

## 使用

安装后在 fnOS 应用中心启动 **OpenCode V2**。

- Web UI：`http://<NAS-IP>:49374`
- 用户名：`opencode`
- 密码：首次启动时随机生成，保存在 `/var/apps/opencode/etc/password`

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

## 升级

请通过 **FnDepot + fnOS 应用中心**升级：

1. 本仓库发布新版本 FPK；
2. 在 fnOS 应用中心安装新版本；
3. 应用中心会处理停止、卸载重装和数据保留。

不要在应用内使用 TUI 的 `/update` 或 `opencode upgrade`。本包已设置
`OPENCODE_DISABLE_AUTOUPDATE=1`，不会主动检查自更新；手动执行时也会因为
无法识别安装方式而安全失败。

## 说明

本包是第三方打包，不是 OpenCode 官方发布。OpenCode 上游采用 MIT License。
