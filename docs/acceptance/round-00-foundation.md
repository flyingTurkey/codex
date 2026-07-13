# Round 00 工程基线验收记录

- 日期：2026-07-13
- 分支：`codex/init-agents-reconcile`
- 环境：Windows 11、Docker Desktop 29.6.1 / Compose 5.3.0
- Docker 数据：`D:\Dockerdata\DockerDesktopWSL\disk\docker_data.vhdx`
- 工具与缓存：仓库 `.tools`、`.cache` 及 `D:\.pnpm-store`

## 本机端口

宿主已有 `quant_stock_postgres` 占用 `5432`，另有 Python 进程占用 `8000`。未停止或修改用户进程，本项目通过 Git 忽略的 `.env` 使用：

| 服务 | 宿主端口 | 容器端口 |
|---|---:|---:|
| Web | 3000 | 3000 |
| API | 18000 | 8000 |
| PostgreSQL | 15432 | 5432 |
| Redis | 6379 | 6379 |
| MinIO / Console | 9000 / 9001 | 9000 / 9001 |

## 已验证结果

| 项目 | 结果 | 证据摘要 |
|---|---|---|
| Compose 配置与固定镜像 | 通过 | PostgreSQL 17.10、Redis 7.4.7、固定 MinIO release，无 `latest` 源引用 |
| 数据迁移 | 通过 | `0001_foundation` 可降级到 `base`、重新升级到 `head`，当前版本确认为 `head` |
| 容器健康 | 通过 | PostgreSQL、Redis、MinIO、API、Worker、Web 全部 healthy |
| 运行时冒烟 | 通过 | readiness 三项均 up；liveness、版本、首页契约通过 |
| Redis 韧性 | 通过 | Redis 停止后 readiness=503、liveness=200；恢复后 readiness=200 |
| Web E2E | 通过 | 首页身份、关键内容、四张指标卡、控制台零错误 |
| Web 无障碍 | 通过 | axe 0 violations |
| 响应式视觉 | 通过 | 1920×1080 与 390×844 视口无裁切、重叠或错误覆盖层 |
| 代码与类型门禁 | 通过 | Ruff、ESLint、mypy strict、Nuxt TypeScript 与生成契约类型检查通过 |
| 自动化测试 | 通过 | Python 38 项、Vitest 2 项、契约测试 8 项全部通过 |
| 安全门禁 | 通过 | Python 0 个已知漏洞；pnpm 无高危（1 个低危）；Trivy HIGH/CRITICAL 为 0 |

## 截图

- [桌面首页](assets/round-00-homepage-desktop.png)
- [移动首页](assets/round-00-homepage-mobile.png)

桌面证据文件：`round-00-homepage-desktop.png`。

## 门禁命令

本记录在最终提交前已刷新以下命令，全部返回退出码 0：

```bash
make lint
make typecheck
make test
make contract-test
make security-check
make web-e2e
make web-a11y
make smoke
make resilience-test
```

Alembic 回滚策略另以 Compose 临时迁移容器验证：先执行 `downgrade base`，再执行 `upgrade head` 和 `current`，最终输出 `0001_foundation (head)`。

## 已知限制

- 当前为演示骨架，没有真实业务数据、真实 SSO、来源适配器或模型调用；
- CSP 为支持 Nuxt Round 00 水合暂时允许同源内联脚本，生产发布前应切换为 nonce/hash 策略；
- 应用内 Browser 插件在本机初始化失败，浏览器验收使用仓库 Playwright 与 D 盘 Chromium；
- 官方 npm/Python 仓库链路较慢，锁文件供应链校验和首次镜像构建耗时较长；pnpm BuildKit store 已启用缓存；
- pnpm 生产依赖审计有 1 个低危传递依赖告警，未达到本轮 HIGH/CRITICAL 阻断阈值，后续依赖升级时继续跟踪。
