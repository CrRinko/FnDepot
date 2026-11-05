# CrRinko 的 FnOS 应用源

用于 FnDepot 的个人 FnOS 应用源，当前包含 **OpenCode V2** 与 **Hermes Agent**，后续会继续加入其他应用。

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
| [Hermes Agent](apps/hermes-agent/README.md) | 0.22.5.3 | x86 | AI赋能 / 系统工具 |
| [GitLab](apps/gitlab/README.md) | 19.5.3.1 | x86 | 编程开发 / 系统工具 |

### OpenCode V2

开源 AI 编程代理，提供 Web UI 与 CLI。本包基于上游 OpenCode v2.2.5 的 linux-amd64 制品构建。

- 安装包：[GitHub Release](https://github.com/CrRinko/FnDepot/releases/tag/opencode-v2.2.5)
- Web UI：`http://<NAS-IP>:49374`，用户名 `opencode`
- 密码：没有固定默认密码，首次启动时随机生成；SSH 登录 NAS 后以 root 权限执行 `sudo cat /var/apps/opencode/etc/password` 获取
- 文件：`opencode-2.2.5-fnos-amd64-r3.fpk`
- 大小：121,153,993 字节
- SHA-256：`7fa917bbfd5334bf509a8489eb4070a9e2030d6ed0e34a3123a62d0fd296829a`
- 说明：r3 修复了安装阶段 `install_init` 的权限问题，密码改为首次启动时生成，并将开发者/发布者统一为 CrRinko。
- 使用说明：[apps/opencode/README.md](apps/opencode/README.md)

### Hermes Agent

Nous Research Hermes Agent 的官方 Web Dashboard，直接运行上游 `hermes dashboard`，不包含自定义控制台。本包基于上游 v0.22.5 构建，FPK 内置补丁源码，安装时创建 Python 3.14 运行时。

- 安装包：[GitHub Release](https://github.com/CrRinko/FnDepot/releases/tag/hermes-agent-v0.22.5.3)
- Web UI：`http://<NAS-IP>:49375`，用户名 `hermes`
- 密码：没有固定默认密码，首次启动时随机生成；SSH 登录 NAS 后以 root 权限执行 `sudo cat /var/apps/hermes-agent/etc/password` 获取
- 文件：`hermes-agent-0.22.5.3-fnos-amd64-r2.fpk`
- 大小：89,275,531 字节
- SHA-256：`9ac7a9cd1484757a8ec2b2a3710bb50f4595927e97e5beed1b68545576371136`
- 说明：应用版本 0.22.5.3 对应上游 v0.22.5 的 r2 打包修订；首次安装约 30–60 分钟。内置更新由 FnDepot/应用中心接管，`hermes update` 会拒绝执行。
- 使用说明：[apps/hermes-agent/README.md](apps/hermes-agent/README.md)

### GitLab

GitLab CE 19.5.3 的 fnOS Docker 应用包，直接运行官方 `gitlab/gitlab-ce:19.5.3-ce.0` 镜像，默认启用 HTTPS，并自动复用 fnOS 证书。

- 安装包：[GitHub Release](https://github.com/CrRinko/FnDepot/releases/tag/gitlab-v19.5.3.1)
- Web UI：`http://<NAS-IP>:8080` 会自动跳转到 `https://<域名>:8443`，用户名 `root`
- 密码：首次启动后随机生成；以 root 权限执行 `sudo cat /var/apps/gitlab/var/initial_root_password.txt` 获取
- 文件：`gitlab-19.5.3.1-fnos-amd64-r1.fpk`
- 大小：38,430 字节
- SHA-256：`4fce07f9622f5355b7085a40547888bf61312f465066ae200710bc82a61914b8`
- 说明：应用设置可修改对外域名、HTTPS 端口、HTTP 跳转端口和 SSH 端口；443 被 fnOS 占用，默认使用 8443。首次启动需拉取约 1.65GB 镜像。
- 使用说明：[apps/gitlab/README.md](apps/gitlab/README.md)

## 仓库结构

```text
FnDepot/
├── fnpack.json                 # FnDepot V2 源索引
├── README.md                   # 本文件
├── LICENSE
├── .gitattributes
├── .gitignore
└── apps/
    ├── opencode/
    │   ├── README.md           # 应用详情
    │   ├── BUILD.md            # 构建说明
    │   ├── icon-256.png        # 应用图标
    │   ├── VERSION             # 当前版本
    │   ├── SOURCE_COMMIT       # 上游 commit
    │   ├── provenance.json     # 当前发布溯源
    │   ├── package/            # fnOS FPK 包源码
    │   └── scripts/
    │       └── build.py        # 下载/校验/构建脚本
    └── hermes-agent/
        ├── README.md
        ├── BUILD.md
        ├── NOTICE
        ├── icon-256.png
        ├── VERSION
        ├── SOURCE_COMMIT
        ├── provenance.json
        ├── package/
        └── scripts/
            ├── build.py
            └── prepare_source.py
```

FPK 文件体积较大，作为 GitHub Release 附件发布，不提交到 Git 仓库。后续新增应用时，按 `apps/<appname>/` 建独立目录。

## 说明

- 本仓库是第三方打包与分发，不是 OpenCode 或 Hermes Agent 官方项目。
- 当前仅提供 amd64（x86）安装包；没有 ARM64 包。
- 升级请通过 FnDepot + fnOS 应用中心：OpenCode 不要使用 `/update` 或 `opencode upgrade`；Hermes Agent 的内置 `hermes update` 已被禁用。
- OpenCode 与 Hermes Agent 上游均采用 MIT License；本仓库的元数据与说明同样采用 MIT License。
- 安装前请确认设备架构与 fnOS 版本；生产环境请先备份数据。
