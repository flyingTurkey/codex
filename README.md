# 四川路桥·智安情报

四川路桥内部使用的行业数智与安全情报平台。仓库已形成 Round 00—11 的工程切片，覆盖来源与原始文档、证据化内容处理、统一信息流、搜索/日报/收藏以及质量、运维和安全门禁。各项能力的真实联网和生产等级仍须按验收证据判断，不能由本说明直接推定。

当前第 11 轮工程切片状态为 `PASSED`，生产证据状态仍为 `BLOCKED`：真实业务金标、连续运行窗口、生产 PITR 和真实告警路由等证据尚未完整。仓库不应被表述为生产就绪。

## 运行组成

- `apps/web`：Node.js 24、Nuxt 4、Vue 3、TypeScript strict、Nuxt UI 4；
- `apps/api`：Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic；
- `apps/worker`：与 API 共享契约的 Celery Worker；
- `packages/contracts`：Problem Details、分页、健康和版本契约；
- `infra/compose`：PostgreSQL 17、Redis 7、MinIO，以及 API、Worker、Web 和迁移任务。

## Windows 与 D 盘约束

本工作站不重复安装 Docker Desktop。Docker 数据虚拟盘已迁移到 `D:\Dockerdata`。项目工具、Python、浏览器与缓存均从仓库内的 D 盘目录使用：

- `.tools/uv`、`.tools/python`、`.tools/node`、`.tools/make`；
- `.cache/uv`、`.cache/ms-playwright`；
- pnpm store：`D:\.pnpm-store`。

打开新的 PowerShell 后，可先加载本项目环境：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. .\scripts\use-local-toolchain.ps1
```

脚本只调整当前 PowerShell 进程，不向 C 盘安装任何工具。若在新机器配置工具，请把工具实体和缓存放在 D 盘，并保持上述目录或通过 Make 变量显式覆盖。

## 首次设置与启动

先复制本地演示配置；`.env` 已被 Git 忽略，不得填入生产密钥：

```powershell
Copy-Item .env.example .env
```

若宿主端口已被其他项目占用，只修改 `.env` 中的宿主端口。容器内部端口不要改。本工作站因已有服务占用 `5432` 和 `8000`，使用：

```dotenv
POSTGRES_PORT=15432
API_PORT=18000
```

安装锁定依赖并启动：

```bash
make setup
make dev
```

常用地址：

- 首页：<http://127.0.0.1:3000>
- API liveness：<http://127.0.0.1:18000/health/live>
- API readiness：<http://127.0.0.1:18000/health/ready>
- API 版本：<http://127.0.0.1:18000/api/v1/version>
- MinIO 控制台：<http://127.0.0.1:9001>

端口使用默认值时，API 地址为 `8000`。停止服务不会删除数据卷：

```bash
make down
```

## 质量门禁

```bash
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make quality-gate
make web-e2e
make web-a11y
```

运行时验收：

```bash
make smoke
make resilience-test
```

`resilience-test` 会暂时停止本项目 Redis，验证 readiness 失败但 liveness 保持成功，并在结束时恢复 Redis。

`security-check` 会审计 Python/pnpm 生产依赖，并把 Git 已跟踪及未忽略的新文件暂存到 `.cache/trivy-input` 后执行 Trivy secret/misconfiguration 扫描。`.env`、D 盘本地工具、依赖目录和构建产物不会进入扫描镜像或 Git。

## 常见问题

- `port is already allocated`：保留已有进程，在 `.env` 覆盖对应宿主端口；Compose 和验收脚本会读取同一配置。
- Docker 构建下载慢：保持官方镜像与注册表引用；pnpm BuildKit store 会在 D 盘 Docker 数据区复用已下载包。
- Playwright 找不到浏览器：确认 `PLAYWRIGHT_BROWSERS_PATH` 指向仓库 `.cache/ms-playwright`，再运行 `make setup`。
- readiness 为 503：查看响应中的 `postgresql`、`redis`、`object_storage` 分项和容器健康状态。

## 文档导航

- 架构基线：[ADR-0001](docs/adr/0001-modular-monolith.md)
- 第 11 轮工程与生产证据状态：[Round 11 验收记录](docs/acceptance/round-11-quality-operations-security.md)
- 二阶段产品与架构基线：[二阶段实施总规范](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Optimization-Codex-Spec.md)
- 二阶段执行顺序：[11F、11P 及第 12—21 轮指令](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Rounds-11F-21-Codex-Commands.md)
- 初始工程证据：[Round 00 验收记录](docs/acceptance/round-00-foundation.md)
