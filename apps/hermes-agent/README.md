# Hermes Agent for fnOS

Nous Research [Hermes Agent](https://github.com/NousResearch/hermes-agent) v0.22.5 的 fnOS x86_64 安装包，直接运行官方 `hermes dashboard`，不包含自定义控制台。

## 版本与来源

| 项目 | 值 |
| --- | --- |
| 应用版本 | 0.22.5 |
| 目标架构 | amd64（manifest `platform=x86`） |
| 上游仓库 | https://github.com/NousResearch/hermes-agent |
| 上游 tag | `v0.22.5` |
| 上游 commit | `bf0203a794a07aac3ff764972ab9087baa4e4f4e` |
| 上游源码 SHA-256 | `a8f67e5ec14fea681acef6cc7ff1553f002bb6101fd2df22bfdd4b7eecc54eb2` |
| 补丁源码 SHA-256 | `62d7d4b423ca749f08d39571e46e4981ce67a94c8e84e64ea34feab8ff18ba3b` |
| 运行时 | Python 3.14.9、uv 0.13.5 |
| FPK SHA-256 | `c5c3d33b70ee3430160ec84248f7d97156e12858d31037e4ed9124c34c9d5f9c` |
| FPK 大小 | 91,383,205 字节 |

补丁源码只做两件事：移除上游 `pyproject.toml` 中 Android-only 的 `psutil` git pin，并用官方 PyPI 重新生成 `uv.lock`。Linux 运行时仍使用 `psutil==7.2.2`。

## 安装

在 FnDepot 中添加源 `https://github.com/CrRinko/FnDepot`，选择 **Hermes Agent** 安装。

安装包直接下载：

```text
https://github.com/CrRinko/FnDepot/releases/download/hermes-agent-v0.22.5/hermes-agent-0.22.5-fnos-amd64.fpk
```

校验：

```bash
sha256sum hermes-agent-0.22.5-fnos-amd64.fpk
# c5c3d33b70ee3430160ec84248f7d97156e12858d31037e4ed9124c34c9d5f9c
```

首次安装会创建 Python 3.14 虚拟环境并安装依赖，通常需要 **10–20 分钟**；安装日志位于 `/vol1/@appdata/hermes-agent/install.log`。

## 登录 Web UI

- 地址：`http://<NAS-IP>:49375`
- 用户名：`hermes`
- 密码：没有固定默认密码，首次启动时随机生成
- 获取密码：SSH 登录 NAS 后，以 root 权限执行：

```bash
sudo cat /var/apps/hermes-agent/etc/password
```

Dashboard 使用上游的密码登录页 + 签名 Cookie 会话，不是 HTTP Basic。不要把 49375 端口直接暴露到公网；远程访问请使用 VPN 或 fnOS 反向代理。

## 数据与日志

```text
/vol1/@apphome/hermes-agent/data         配置、.env、sessions、skills、memories
/vol1/@appdata/hermes-agent/dashboard.log 服务日志
/vol1/@appdata/hermes-agent/install.log   安装日志
/var/apps/hermes-agent/etc/password       登录密码（0600）
```

`data/` 与运行时分离：升级 FPK 会重建运行时，但保留 `data/`。

## 升级

只通过 **FnDepot + fnOS 应用中心**升级。

`install-stamp.json` 固定为：

```json
{
  "updateMechanism": "external",
  "distribution": "fnos"
}
```

因此 `hermes update` 会拒绝执行（退出码 2），dashboard 的更新动作也会返回“由安装方管理”的拒绝信息。这样可避免应用内自更新覆盖 FPK 运行时；升级统一由新的 FPK 交付。

## 卸载

在 fnOS 应用中心卸载会停止服务。持久数据 `data/` 不会由本包主动删除；如需彻底清理：

```bash
sudo rm -rf /vol1/@apphome/hermes-agent /vol1/@appdata/hermes-agent
```

## 说明

本包是第三方打包，不是 Nous Research 官方发布。Hermes Agent 上游采用 MIT License；本目录的打包脚本和文档同样采用 MIT License。详见 `NOTICE`。
