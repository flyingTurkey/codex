# 四川路桥·智安情报

## PERS-04 自动来源画像与个人纠错

`/sources` 会为已有和新探测成功的来源自动生成工程行业、内容域、语言、国家/地区、来源声明角色、权威等级和独立性等级。画像保存输入哈希、证据、理由、逐字段/总体置信度以及规则、Prompt、Schema 和模型版本；权威与独立性始终标记为自动推断，不冒充人工结论。

Owner 可在来源画像侧栏覆盖全部语义字段，自动重跑不会覆盖个人选择；“一键撤销覆盖”可恢复跟随最新自动画像。RSS、Sitemap、API、PDF 等技术事实只读。DeepSeek 不可用、余额不足、预算关闭或输入含提示注入时，本地规则结果仍以 `PARTIAL` 提供，且不会中断采集。字段与置信度解释见[个人来源画像说明](docs/user-guide/personal-source-profiles.md)。本轮不实现全网自动发现或内容自动发布。

## PERS-03 个人公开 URL 来源

平台当前唯一产品形态是本机单一 Owner 的个人研究平台，不提供企业模式开关。`/sources` 用两个独立状态管理来源：`desired_enabled` 只记录 Owner 的启停意图，`runtime_state` 只显示系统实际运行状态；“用户已启用”不代表“当前正在运行”。手工停用会写入不可变关键活动事件和最高优先级标记，旧自动任务不能重新启用该来源。

Owner 现在可在 `/sources` 只粘贴一个公开 HTTPS URL，系统自动识别来源主页、栏目列表、RSS/Atom、Sitemap、JSON API 或直接 PDF，并在同一规范化 Origin 下展示多个采集入口。操作说明见[个人用户：添加公开 URL](docs/user-guide/personal-add-url.md)。

个人 URL 探测与受控运行不删除旧治理表。旧角色、`/api/v1/admin` 和治理页面暂时保留供历史代码运行，但不是新的产品交互。公网安全、robots、限速、预算、raw-first、证据追溯、Schema 校验及 `PublicationService` 单一发布边界继续有效；证据事实与 AI 判断保持不同语义。

本轮只支持本机访问。Compose 将 Web 和 API 绑定到 `127.0.0.1`，Nuxt 服务端代理为固定本地 UUIDv7 注入 `owner`；不要把本地身份头或端口代理到局域网、公网。远程 OIDC Owner 尚未实现，非本地身份不能调用新的个人来源 API。

过渡期旧页面所需角色由 `NUXT_LOCAL_APP_ROLES` 单独配置；该变量不改变个人 API 的固定 `owner` 身份，也不能用于远程认证。

## R-AI01 AI 内容准备

当前 AI 纵向切片只允许规范来源 `GOV-003` 的一个固定交通运输部公开 PDF。服务端从当前 `READY` 文档生成页块与 Evidence Anchor，经固定 DeepSeek 能力适配器执行分类和事实抽取，最终停在 `WAITING_CLAIM_REVIEW`。模型输出始终是候选，不自动写入 accepted claim，也不触发摘要、Publication、Feed、检索投影或日报。

本地/测试默认使用 `SRBG_AI_PROVIDER=mock`。真实调用只能使用环境变量 `SRBG_AI_API_KEY` 或 Git 忽略的 `/run/secrets/srbg-ai/deepseek.key`，端点、路径、模型和 Token 上限不可由环境或请求覆盖。管理员可在 `/admin/ai` 查看固定能力、预算和阻断原因；生产环境禁用本地 Secret 写入。

定向门禁：

```bash
make ai-content-preparation-test
```

实现、资格审核和真实调用状态见 [R-AI01 验收记录](docs/acceptance/phase-2/round-ai01-content-preparation.md)。

四川路桥内部使用的行业数智与安全情报平台。仓库工程实现覆盖来源与原始文档、证据化内容处理、统一信息流、搜索/日报/收藏、Event 统一身份、内部发布投影、PostgreSQL 权威调度、来源健康、安全重放、自动化来源候选治理，以及20来源真实试运行的授权与离线验收门禁。各项能力的真实联网和生产等级仍须按验收证据判断，不能由本说明直接推定。

当前第17轮的工程准备门禁已经完成，但真实试运行仍为 `BLOCKED`。LEO 已作为唯一超级管理员确认并冻结20源清单、来源频率、展示边界、168小时窗口和单专家参考集方案；测试环境通过一次 Ed25519 签名原子安装授权，20/20来源已自动登记。当前仍为0个 ACTIVE、0个当前逐源策略、0个当前连接器配置、0个成功真实试运行，观察窗口尚未启动，LEO单专家参考集和真实证据导出均不存在。仓库没有用 Fixture、回填或测试日志冒充真实连续观察；AI观察、付费模型、语义搜索、邮件和企业微信保持关闭。

## 自动化来源治理优化切片（默认关闭）

本切片把管理员从“逐项创建政策、配置、试运行和审批”收敛为“查看服务端资格包后决定启用或不启用”，但没有把来源准入权交给搜索服务或模型：

1. Worker 每6小时按代码内固定的24个工程查询代码唤醒发现任务；首个联网发现执行器为百度智能搜索，单次 `top_k=50`，每个查询最多直接探测20个不同机构域名。手工录入的 HTTPS 机构地址也会自动进入同一资格审查。
2. 固定查询目录保存在代码中，但每次百度调用的查询记录及返回的标题、摘要只存在于当前进程内，不写 PostgreSQL、对象存储、Celery 消息或日志。候选必须再经过逐跳 DNS/IP/peer 固定、SSRF、重定向、超时、响应大小和机构域边界检查的直接目标请求；持久化只接受目标站点自身的证据哈希和服务端分类。
3. 候选进入独立 `QUALIFICATION` 执行域；资格原始证据保存在私有、内容寻址的隔离命名空间，不能被提升或复用为生产采集结果。规则输出 `QUALIFIED`、`WARN_WAIVABLE` 或 `BLOCKED`，并绑定规则版本、材料指纹、7天有效期和 SHA-256 资格包。
4. `source_admin` 可以补充候选和重新发起资格审查，但不能作最终决定；只有 `platform_admin` 能在生产 OIDC 会话最近5分钟内完成 MFA 后启用或不启用。全绿启用和不启用无需再填写通用操作原因，服务端记录受控审计原因；`WARN_WAIVABLE` 仍必须逐条填写具体豁免理由，材料变化后失效；`BLOCKED` 永远不能启用。批量启用只接受同一规则版本、未过期、全绿的1—10项。
5. 启用事务会写入服务端权威政策、连接器配置、生产审批、来源/流状态和不可变审计，并通过 Outbox 创建一个全新的 `SCHEDULED + PRODUCTION` 采集运行；资格审查响应不会进入生产内容链路。后续自动更新继续复用 PostgreSQL 权威调度、每次 I/O 前授权复核、raw-first 存储、5次失败/30分钟熔断和连续3次零发现异常。
6. 生产采集形成的当前 `READY` 文档通过独立耐久 Outbox、仅含 ID 的任务和原子数据库命令，幂等登记为 `ai_pipeline_run(LIVE, QUEUED)`；桥接到此停止，不创建 Claim、审核决定或发布。通用生产 AI 四步编排器尚未交付时，记录会诚实停留在 `WAITING_AI`，不会进入普通用户 Feed。

百度调用预算以 PostgreSQL 行锁在请求前原子预留：每个 UTC 月前1500次免费，之后按每次0.036元计费；达到200元月度硬上限前拒绝下一次会超额的请求，80%只告警一次。代码还把月度上限、免费次数和告警阈值分别钳制为不高于上述值，客户端或环境变量不能放宽。

该能力在 `.env.example` 和 Compose 中保持 `SRBG_SOURCE_DISCOVERY_ENABLED=false`、`SRBG_SOURCE_QUALIFICATION_ENABLED=false`、`SRBG_BAIDU_SEARCH_ENABLED=false`，API key 为空；必须由平台管理员、来源治理责任人和合规/版权责任人确认百度服务条款、目标站点 robots/条款、预算、告警路由及生产 OIDC/MFA 后才可显式启用。资格审核可以脱离付费发现单独启用，自动发现则必须同时启用资格审核。当前自动定时发现仅实现百度通道；Directory/RSS/Sitemap/Outbound Link 是候选渠道契约而非已运行的自动发现器，自动生成的生产连接器目前为通用 `LIST_DETAIL` V1。来源流的暂停/恢复/修复写操作仍走既有来源生命周期与计划运维接口。完整边界、测试证据、回滚和已知限制见[自动化来源治理验收记录](docs/acceptance/phase-2/round-18-source-automation.md)、[内容处理耐久桥验收记录](docs/acceptance/phase-2/round-19-source-content-bridge.md)和[运行手册](docs/operations/runbooks.md)。

## 第17轮真实试运行准备

- `phase2-round17-test` 只执行确定性契约、Fixture、故障、安全、Event/投影边界、签名授权和发布路径测试；不会实时抓网。当前结果为308项后端/契约/安全测试和93项Web测试通过。
- `phase2-round17-eval` 使用版本化 `round17-flat-evidence-v1` 离线评估器，只读取哈希绑定的真实窗口 evidence 和 `LEO_SINGLE_EXPERT_REFERENCE_SET`。缺168小时窗口、20源逐源状态、LEO参考集或故障演练时必须非零 `BLOCKED`；它不再要求 yinzi/baixuejiao 双标，也不设置个人绩效指标。
- R17 测试环境使用 `SIGNED_LOCAL_PILOT`：LEO（`019f6b65-4cf5-71d1-b75c-a6c908912f58`）是唯一批准人。私钥只允许保存在被 Git 忽略的根目录 `.env`；提交的批准包只包含签名、公钥、哈希和有效期。生产环境仍拒绝该模式并保持企业 OIDC/SSO。
- 签名安装器会在同一事务中验证完整20源清单、安装LEO绑定和授权，并自动补录缺失的 `NRA-001`。自动登记只产生 `CANDIDATE/enabled=false` 和审计事实，不会绕过策略、配置、真实试运行或事件化门禁授予 ACTIVE。
- 真实运行只允许 PostgreSQL 权威 ACTIVE 来源，逐次物理请求在 I/O 前执行域名、租约和预算校验；重试/重定向计入频率，回放固定为无网络 `FIXTURE + REPLAY`。
- R17 真实链路仍未启动。来源特定的 raw-first Document→accepted Claim/Evidence→Event→PublicationService 配置不能在来源/DOM 未验证时编造；T0 必须由数据库权威事件化准备事实逐源放行。

完整的逐源诚实状态、工程命令和外部阻断见[第17轮验收记录](docs/acceptance/phase-2/round-17-20-source-pilot.md)，机器可读状态见 [`round-17-flat-readiness.json`](docs/acceptance/phase-2/round-17-flat-readiness.json)。结论保持：**第17轮未完成/BLOCKED；本次横切工程优化不构成第17轮晋级、20来源真实联网授权或168小时窗口启动。**

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
- 以下 OIDC/SSO、R17 签名身份和企业角色说明仅记录旧流程的兼容边界；PERS-01 新个人页面和 API 只接受固定本地 Owner，远程认证尚未开放。

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
- 个人来源界面：<http://127.0.0.1:3000/sources>
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
- 自动化来源发现、隔离资格审查与单步启用：[自动化来源治理验收记录](docs/acceptance/phase-2/round-18-source-automation.md)
- 自动化来源预算、停机、修复与回滚：[运行手册](docs/operations/runbooks.md#自动化来源发现资格审查与启用)
- 第17轮20来源真实试运行准备与阻断：[Round 17 验收记录](docs/acceptance/phase-2/round-17-20-source-pilot.md)
- 第17轮机器可读工程准备状态：[Round 17 readiness](docs/acceptance/phase-2/round-17-flat-readiness.json)
- 二阶段产品与架构基线：[二阶段实施总规范](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Optimization-Codex-Spec.md)
- 二阶段执行顺序：[11F、11P 及第 12—21 轮指令](docs/codex-kit/docs/phase-2/SRBG-Phase-2-Rounds-11F-21-Codex-Commands.md)
- 初始工程证据：[Round 00 验收记录](docs/acceptance/round-00-foundation.md)
