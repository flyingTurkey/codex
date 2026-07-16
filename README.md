# 四川路桥·智安情报

四川路桥内部使用的行业数智与安全情报平台。仓库工程实现已推进至 Round 17，覆盖来源与原始文档、证据化内容处理、统一信息流、搜索/日报/收藏、Event 统一身份、内部发布投影、PostgreSQL 权威调度、来源健康、安全重放，以及20来源真实试运行的授权与离线验收门禁。各项能力的真实联网和生产等级仍须按验收证据判断，不能由本说明直接推定。

当前第17轮的工程准备门禁已经完成，但真实试运行仍为 `BLOCKED`。LEO 已作为唯一超级管理员确认并冻结20源清单、来源频率、展示边界、168小时窗口和单专家参考集方案；测试环境通过一次 Ed25519 签名原子安装授权，20/20来源已自动登记。当前仍为0个 ACTIVE、0个当前逐源策略、0个当前连接器配置、0个成功真实试运行，观察窗口尚未启动，LEO单专家参考集和真实证据导出均不存在。仓库没有用 Fixture、回填或测试日志冒充真实连续观察；AI观察、付费模型、语义搜索、邮件和企业微信保持关闭。

## 第17轮真实试运行准备

- `phase2-round17-test` 只执行确定性契约、Fixture、故障、安全、Event/投影边界、签名授权和发布路径测试；不会实时抓网。当前结果为308项后端/契约/安全测试和93项Web测试通过。
- `phase2-round17-eval` 使用版本化 `round17-flat-evidence-v1` 离线评估器，只读取哈希绑定的真实窗口 evidence 和 `LEO_SINGLE_EXPERT_REFERENCE_SET`。缺168小时窗口、20源逐源状态、LEO参考集或故障演练时必须非零 `BLOCKED`；它不再要求 yinzi/baixuejiao 双标，也不设置个人绩效指标。
- R17 测试环境使用 `SIGNED_LOCAL_PILOT`：LEO（`019f6b65-4cf5-71d1-b75c-a6c908912f58`）是唯一批准人。私钥只允许保存在被 Git 忽略的根目录 `.env`；提交的批准包只包含签名、公钥、哈希和有效期。生产环境仍拒绝该模式并保持企业 OIDC/SSO。
- 签名安装器会在同一事务中验证完整20源清单、安装LEO绑定和授权，并自动补录缺失的 `NRA-001`。自动登记只产生 `CANDIDATE/enabled=false` 和审计事实，不会绕过策略、配置、真实试运行或事件化门禁授予 ACTIVE。
- 真实运行只允许 PostgreSQL 权威 ACTIVE 来源，逐次物理请求在 I/O 前执行域名、租约和预算校验；重试/重定向计入频率，回放固定为无网络 `FIXTURE + REPLAY`。
- R17 真实链路仍未启动。来源特定的 raw-first Document→accepted Claim/Evidence→Event→PublicationService 配置不能在来源/DOM 未验证时编造；T0 必须由数据库权威事件化准备事实逐源放行。

完整的逐源诚实状态、工程命令和外部阻断见[第17轮验收记录](docs/acceptance/phase-2/round-17-20-source-pilot.md)，机器可读状态见 [`round-17-flat-readiness.json`](docs/acceptance/phase-2/round-17-flat-readiness.json)。结论保持：**第17轮未完成/BLOCKED，不进入第18轮。**

## 第 16 轮数据库权威调度

- `fetch_schedule` 保存计划、下次执行、租约、退避、熔断、freshness SLO、速率与日预算；并发领取使用 PostgreSQL `FOR UPDATE SKIP LOCKED`。
- Worker 在外部 I/O 前重新校验 ACTIVE 来源、当前有效策略/配置、生产审批、计划、预算与熔断；人工暂停后未执行运行以 `CANCELLED` 收口。
- 来源健康区分传输、发现、解析、内容质量与业务时效；304、429/`Retry-After`、5xx、超时、DNS、解析、对象存储和数据库失败均映射为受控状态。
- 失败事实不保存正文、Cookie、令牌或模型输入；重放只从当前有效的 source/run/document/event/outbox/projection 事实重建，不可重建时标记 `NON_REPLAYABLE/BLOCKED`。

详细状态机、故障矩阵与本次命令证据见 [第 16 轮验收记录](docs/acceptance/phase-2/round-16-scheduling-health-replay.md)。

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
- 首期仍仅允许企业内部访问，不开放匿名互联网访问。生产环境采用 OIDC/SSO；R17 的签名本地身份仅限明确标记的 `test` 环境，配置成 production 时服务端启动即拒绝。

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

R17 测试环境首次配置签名授权时执行以下命令。`round17_keygen.py` 会轮换根目录 `.env` 中的R17密钥，不应在已有有效窗口中重复运行；安装授权不会自动启动168小时窗口：

```powershell
.\tools\uv\uv.exe run python scripts/round17_keygen.py
.\tools\uv\uv.exe run python scripts/round17_sign_approval.py
.\tools\uv\uv.exe run python scripts/round17_install_approval.py --loopback-port 15432
```

若 `.env` 使用其他 `POSTGRES_PORT`，最后一条命令应传入对应宿主端口。一次签名安装只完成授权与20源自动登记，不创建策略、连接器、真实试运行证据，也不启动观察窗口。

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
make phase2-round16-test
make phase2-round17-test
make phase2-round17-eval
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
- 第17轮20来源真实试运行准备与阻断：[Round 17 验收记录](docs/acceptance/phase-2/round-17-20-source-pilot.md)
- 第17轮机器可读工程准备状态：[Round 17 readiness](docs/acceptance/phase-2/round-17-flat-readiness.json)
- 二阶段产品与架构基线：[二阶段实施总规范](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Optimization-Codex-Spec.md)
- 二阶段执行顺序：[11F、11P 及第 12—21 轮指令](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Rounds-11F-21-Codex-Commands.md)
- 初始工程证据：[Round 00 验收记录](docs/acceptance/round-00-foundation.md)
