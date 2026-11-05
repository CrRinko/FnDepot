# 构建 GitLab fnOS Docker 应用

本目录包含 GitLab CE 的 fnOS Docker 应用包源码。FPK 不包含 GitLab 镜像，
只包含 compose、生命周期脚本、向导、图标和配置；镜像由应用中心在首次启动时拉取。

## 环境

- Linux amd64
- Python 3.10+
- `fnpack` 1.2.3（脚本会自动下载并校验）
- 可访问 `static2.fnnas.com` 和镜像仓库
- 真实安装验证需要 fnOS 1.2.0800

## 检查

```bash
cd apps/gitlab
python3 scripts/build.py --check-only
bash tests/run_tests.sh
```

`--check-only` 校验 manifest、compose、wizard JSON、脚本可执行位、图标尺寸和隐私内容。
`tests/run_tests.sh` 运行证书选择、配置渲染、同步编排的单元测试和生命周期脚本测试。

## 构建

```bash
cd apps/gitlab
python3 scripts/build.py --artifact-suffix r2 --json
```

输出：

```text
dist/gitlab-19.5.3.2-fnos-amd64-r2.fpk
dist/gitlab-19.5.3.2-fnos-amd64-r2.fpk.sha256
dist/provenance.generated.json
```

打包修订（上游版本不变，只改脚本或文档）时递增 `APP_VERSION`，并传入后缀：

```bash
python3 scripts/build.py --app-version 19.5.3.3 --artifact-suffix r3 --json
```

## 版本与镜像

`VERSION` 是上游 GitLab 版本，`APP_VERSION` 是 FPK 应用版本。两者通常一致；
打包修订时只递增 `APP_VERSION` 的末位。

镜像固定为 `gitlab/gitlab-ce:<版本>-ce.0`，不使用 `latest`。升级 GitLab 时同时更新：

- `VERSION`、`APP_VERSION`
- `package/app/docker/docker-compose.yaml` 的 image
- `provenance.json` 的 image tag/digest
- `apps/gitlab/README.md` 的版本和摘要

## 目录

```text
apps/gitlab/
├── package/
│   ├── app/
│   │   ├── bin/select_cert.py      证书选择
│   │   ├── bin/gitlab_config.py    gitlab.rb 渲染
│   │   ├── bin/sync_config.py      编排
│   │   ├── docker/                 compose
│   │   └── ui/                     桌面入口和图标
│   ├── cmd/                        9 个生命周期脚本
│   ├── config/                     权限和 docker-project 声明
│   └── wizard/                     安装、设置、卸载表单
└── scripts/build.py
```

## 发布

```bash
gh release create gitlab-v19.5.3.2 \
  dist/gitlab-19.5.3.2-fnos-amd64-r2.fpk \
  dist/gitlab-19.5.3.2-fnos-amd64-r2.fpk.sha256 \
  --title "GitLab 19.5.3.2" \
  --notes "GitLab CE 19.5.3 for fnOS (x86_64)."
```

然后更新 `fnpack.json`、`provenance.json` 和 README 的下载地址、sha256、size。
