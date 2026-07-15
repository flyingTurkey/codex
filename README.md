# 四川路桥·智安情报

四川路桥内部使用的行业数智与安全情报平台。仓库已形成 Round 00—13 的工程切片，覆盖来源与原始文档、证据化内容处理、统一信息流、搜索/日报/收藏、质量运维安全门禁，以及 Event-keyed 内部发布投影的安全影子基线。各项能力的真实联网和生产等级仍须按验收证据判断，不能由本说明直接推定。

当前第 14 轮工程验收已通过：默认普通用户 Feed、Event 详情、搜索、已发布日报和收藏内容通过 `srbg_projection_reader_login` 读取 `published_v1`，Event 收藏、专题和反馈的新写入只使用 `event_id`；旧 `item_id` 仅作为可空、不可变的兼容溯源。隔离 PostgreSQL TEST 数据已对旧收藏、日报、专题、revision 与 R3 ACL 引用完成非空对账。第 11 轮生产证据状态仍为 `BLOCKED`：真实业务金标、连续运行窗口、生产 PITR 和真实告警路由等证据尚未完整，因此仓库仍不应被表述为生产就绪。

## 第 14 轮 Event 统一身份

- `EventSummary`/`EventDetail` 是唯一用户契约，`event_type` 必填且不默认安全事故；Document 只作为证据并显式记录来源角色。
- 旧 `/items/{id}` 页面返回 308 到 `/events/{event_id}`；旧读取 API 返回 `Deprecation` 和 successor `Link`。`Sunset` 只有显式配置后才发送，仓库没有自定生产删除日期。
- 回填任务独立于 Alembic，按版本和 checkpoint 幂等运行；模糊匹配只进入人工候选，生产自动合并关闭。
- 本地验收已发布 Item 身份迁移为 23/23、consumer parity difference 为 0；23 条来源角色因证据不足进入人工队列，没有猜测。

完整证据见[第 14 轮验收记录](docs/acceptance/phase-2/round-14-event-unification.md)。

## 运行组成

- `apps/web`：Node.js 24、Nuxt 4、Vue 3、TypeScript strict、Nuxt UI 4；
- `apps/api`：Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic；
- `apps/worker`：与 API 共享契约的 Celery Worker；
- `packages/contracts`：Problem Details、分页、健康、版本及 `PublishedEventSummaryV1`/`PublishedEventDetailV1` 契约；
- `infra/compose`：PostgreSQL 17、Redis 7、业务 MinIO、独立审计锚定 MinIO，以及 API、Worker、Web 和迁移任务。

## 第 13 轮内部发布投影

- `published_v1` 是版本化、Event-keyed 的影子发布内容 schema；`publication_projection_state` 仍只表达搜索、缓存和日报失效状态，不充当内容投影。
- `srbg_projection_reader` 只拥有 `published_v1` 只读视图的 `USAGE/SELECT`，不拥有业务 `public` schema、原始对象、审核备注、审计表或投影基表权限。普通读取服务不得用应用超管连接代替该角色。
- `publication_risk_tier`、`content_severity` 和 `projection_level` 是相互独立的权威轴。R3 待审核只产生官方题录 `METADATA_ONLY`，且不进入精选、日报、推荐、通知或全文导出；R4 零投影。
- 投影只保存发布题录、accepted claims 和证据定位，不复制原始全文。撤回、纠正及法律下架会使当前投影失效。
- 审计边界为 append-only/tamper-evident：运行角色不能直接写 `audit_log`，链值由受控数据库函数生成，链根锚定到独立对象存储；这不等于数据库管理员绝对不可篡改。
- publisher 每日锚定审计链根；`/metrics` 暴露由 PostgreSQL 计算的投影对账差异、最近成功回填和最近成功锚定时刻，Prometheus 对差异或陈旧状态告警，处置流程保持不切换消费者且不回退读取业务表。
- 首期仍仅允许企业内部 OIDC/SSO，非开发环境不接受本地身份头，不开放匿名互联网访问。

本地验收影子数据为 32 个稳定 Event：23 条 `FULL`、9 条 R3 `METADATA_ONLY`、0 条 R4 投影，连续两代对账差异均为 0。该数量是固定验收数据证据，不代表生产内容规模。完整证据见[第 13 轮验收记录](docs/acceptance/phase-2/round-13-internal-projection-event-identity.md)。

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
make phase2-round13-test
make phase2-round14-test
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
- 第 13 轮内部发布投影与 Event 身份：[Round 13 验收记录](docs/acceptance/phase-2/round-13-internal-projection-event-identity.md)
- 第 14 轮 Event 统一身份与 Item 兼容迁移：[Round 14 验收记录](docs/acceptance/phase-2/round-14-event-unification.md)
- 二阶段产品与架构基线：[二阶段实施总规范](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Optimization-Codex-Spec.md)
- 二阶段执行顺序：[11F、11P 及第 12—21 轮指令](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Rounds-11F-21-Codex-Commands.md)
- 初始工程证据：[Round 00 验收记录](docs/acceptance/round-00-foundation.md)
