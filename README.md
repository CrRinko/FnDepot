# CrRinko 的 FnOS 应用源

用于 FnDepot 的个人 FnOS 应用源，当前包含 **OpenCode V2**，后续会继续加入其他应用。

## 添加源

需要 FnDepot 客户端 **> 0.0.7**（支持 V2 源）。在客户端中添加仓库地址：

```text
https://github.com/CrRinko/FnDepot
```

客户端会读取仓库根目录的 `fnpack.json`。

## 应用

| 应用 | 版本 | 架构 | 分类 |
| --- | --- | --- | --- |
| [OpenCode V2](apps/opencode/README.md) | 2.2.5 | x86 | 编程开发 / AI赋能 |

### OpenCode V2

开源 AI 编程代理，提供 Web UI 与 CLI。本包基于上游 OpenCode v2.2.5 的 linux-amd64 制品构建。

- 安装包：[GitHub Release](https://github.com/CrRinko/FnDepot/releases/tag/opencode-v2.2.5)
- Web UI：`http://<NAS-IP>:49374`，用户名 `opencode`
- 密码：没有固定默认密码，首次启动时随机生成；SSH 登录 NAS 后以 root 权限执行 `sudo cat /var/apps/opencode/etc/password` 获取
- 文件：`opencode-2.2.5-fnos-amd64-r2.fpk`
- 大小：121,154,901 字节
- SHA-256：`7a348547346b6cd78237ef7b187c7ec25083c660986624044dc11d997f8dd824`
- 说明：r2 修复了安装阶段 `install_init` 的权限问题，密码改为首次启动时生成。
- 使用说明：[apps/opencode/README.md](apps/opencode/README.md)

## 仓库结构

```text
FnDepot/
├── fnpack.json                 # FnDepot V2 源索引
├── README.md                   # 本文件
├── LICENSE
├── .gitattributes
├── .gitignore
└── apps/
    └── opencode/
        ├── README.md           # 应用详情
        ├── BUILD.md            # 构建说明
        ├── icon-256.png        # 应用图标
        ├── VERSION             # 当前版本
        ├── SOURCE_COMMIT       # 上游 commit
        ├── provenance.json     # 当前发布溯源
        ├── package/            # fnOS FPK 包源码
        │   ├── manifest
        │   ├── cmd/
        │   ├── config/
        │   └── app/
        └── scripts/
            └── build.py        # 下载/校验/构建脚本
```

FPK 文件体积较大，作为 GitHub Release 附件发布，不提交到 Git 仓库。后续新增应用时，按 `apps/<appname>/` 建独立目录。

## 说明

- 本仓库是第三方打包与分发，不是 OpenCode 官方项目。
- 当前仅提供 amd64（x86）安装包；没有 ARM64 包。
- 升级请通过 FnDepot + fnOS 应用中心，不要使用应用内的 `/update` 或 `opencode upgrade`。
- OpenCode 上游采用 MIT License；本仓库的元数据与说明同样采用 MIT License。
- 安装前请确认设备架构与 fnOS 版本；生产环境请先备份数据。
