# 四川路桥·智安情报

## 平台是什么

这是一个绑定本机回环地址、由单一 `owner` 使用的土木工程行业数智与安全情报研究平台。平台围绕公开来源、原始证据、结构化 claims、发布门禁和统一阅读体验组织工作，不提供企业模式、角色审批工作台或远程多用户服务。

内容使用三种主类型：数字化转型、安全情报和行业动态。“热点”只是服务端派生的展示资格，不是第四种内容类型。

## 当前具备的功能

下表描述基线代码、API、页面和验收证据实际证明的能力。这里的“确定性测试”包括单元、契约或隔离集成测试，不等同于真实来源、真实 AI 或正式数据闭环。

| 能力 | 当前状态 | 已证明的边界 |
| --- | --- | --- |
| 来源登记、URL 探测、画像、启停意图与健康状态 | 已实现并通过确定性测试 | `/sources` 与 `/api/v1/sources` 可登记公开 HTTPS URL、探测 RSS/Sitemap/API/PDF/列表页、显示流级健康和 `actual_running`；启停只记录 Owner 意图 |
| SourceStream 研究与合规记录 | 已实现并通过确定性测试 | 研究清单可保存精确入口、内容边界、robots/条款/版权结论和 disposition；研究候选不授予 SourceAdmission 或运行权 |
| 受控采集、raw-first 保存、文档解析与版本化 | 已实现但尚未完成真实外部闭环 | SourceAdapter、私有对象存储、恶意文件检查、文档版本和变更失效机制已有测试；fixture、mock 或隔离 MinIO 不证明当前真实来源已保存 raw/document version |
| 自动相关性分类 | 已实现但尚未完成真实外部闭环 | 三轴领域模型、唯一 `PrimaryType`、锁定负例、Schema 校验和失败关闭已有测试；没有把离线 replay、SHADOW 或历史 Owner Gold 当生产授权 |
| accepted claims、evidence 与 `SourceExcerpt` | 已实现但尚未完成真实外部闭环 | claim/evidence 双向约束、当前文档版本绑定、摘要只引用 accepted claims、变更失效已有测试；尚缺本次基线上的真实外部文档闭环证据 |
| AI 编排与结果状态 | 已实现但尚未完成真实外部闭环 | 受控输入、Schema 校验、耐久终态、重试/修复、成本账本和七种阅读状态已有测试；本次基线没有调用真实 AI |
| 技术异常、重试与恢复 | 已实现并通过确定性测试 | `/technical-exceptions` 与 `/api/v2/owner/exceptions` 支持查看耐久异常、幂等重试和停用来源；自动恢复与耗尽路径由隔离集成测试覆盖 |
| Feed suppression 与安全 hold | 已实现并通过确定性测试 | `/feed-suppressions`、Owner 异常控制和服务端安全投影支持隐藏、恢复、可决定安全项与不可覆盖硬阻断；R3/R4 在服务端失败关闭 |
| `PublicationService` 发布门禁 | 已实现但尚未完成真实外部闭环 | 它是 Feed、搜索、日报和相关读取投影的唯一发布写入边界；FULL/R3/R4、失效、重试和抑制恢复由测试覆盖 |
| v2 Feed、搜索、热点、详情、附录和许可媒体 | 已实现并通过确定性测试 | `/api/v2/feed`、`search`、`hotspots`、Event Reader、appendix 和媒体授权已有契约/UI/隔离集成覆盖；本地正式运行验收证明接口与 Web 可启动，不证明 Feed 中内容来自本次真实外部链路 |
| 收藏、日报、引用、版本差异和关系纠正 | 已实现并通过确定性测试 | `/saved`、`/daily`、引用导出、版本时间线/diff 与自动关系纠正继续使用 v1 边界 |
| Owner 来源与 AI 设置页面 | 已实现并通过确定性测试 | `/sources` 和 `/settings/ai` 可管理 Owner 可见配置；保存 provider 或 Secret 不表示 AI 已完成任何文档 |
| `make dev-lite` 本地轻量运行 | 已完成本地正式运行验收 | 核心与 automation 执行平面运行，来源发现、AI Worker 和完整观测栈默认不启动 |
| `make dev` 完整本地运行 | 已完成本地正式运行验收 | 完整 profile 可启动并通过 smoke；启动服务不等于来源获准运行、AI 获准调用或内容获准发布 |
| 法规库、工法库、招标资讯和内部数据集成 | 仅作为历史或预留接口 | 当前不是可用产品功能 |
| 远程认证、多用户和企业审批 | 当前不可用 | 产品只支持本机回环地址上的固定 Owner |

## 当前尚未证明或尚未完成的能力

当前最重要的未闭环事项是：尚未用本次基线证明一条真实外部链路完整通过

```text
真实来源
  → raw / document version
  → AI 与自动分类
  → accepted claims / evidence / SourceExcerpt
  → PublicationService
  → v2 Feed
```

因此，以下说法都不能由现有基线推出：

- 来源已登记，不表示完成研究、获得运行授权或正在采集。
- 研究结论为 `ADMISSION_READY`，不表示 SourceAdmission 已 `ADMIT`。
- Worker 容器正在运行，不表示某个 SourceStream 的 `actual_running=true`。
- 抓取请求成功，不表示 raw/document version 已权威保存。
- raw 已保存，不表示解析、AI、accepted claims 或 evidence 已完成。
- AI provider 已配置或 AI Worker 已启动，不表示某个文档的 AI 已成功。
- accepted claims/evidence 已形成，不表示 `PublicationService` 已发布。
- fixture、mock、canary、SHADOW、离线 replay 或接口返回成功，不表示 Event 已进入真实 v2 Feed。
- Event 已进入 Feed，也不表示内容经过人工复核；“机器整理/未人工复核”必须独立显示。

## 十个状态必须分别判断

排查一条内容时，按下列顺序读取权威事实，不使用“平台正在运行”概括多个状态：

| 顺序 | 状态 | 需要看到的事实 |
| ---: | --- | --- |
| 1 | 来源已登记 | Source 记录存在 |
| 2 | 来源已通过研究或合规评估 | 版本化研究记录、精确边界与 disposition 存在 |
| 3 | 来源已获得服务端运行授权 | 当前 SourceAdmission 与全部公网/合规/预算门禁通过 |
| 4 | Worker 正在运行 | 对应执行平面健康，且目标流的权威运行投影为正在运行 |
| 5 | raw/document version 已保存 | 私有对象、内容哈希、Document 与当前 DocumentVersion 均存在 |
| 6 | AI 已完成 | 对应文档版本的合法 LIVE 运行进入耐久成功终态 |
| 7 | accepted claims/evidence 已形成 | 当前 claims、Evidence ID、证据定位和双向引用有效 |
| 8 | `PublicationService` 已发布 | 当前权威上下文通过统一门禁并形成发布 revision |
| 9 | Event 已进入 v2 Feed | 当前 v2 读取投影可见，且没有 suppression 或安全 hold |
| 10 | 是否人工复核 | 独立的 review 状态；不得从官方来源、AI 成功或 Feed 可见性推断 |

## 日常如何启动

先准备本机 `.env`、Docker Desktop 和 `D:\SRBGData` 持久化目录。挂载、备份与恢复边界见[个人平台备份恢复](docs/operations/personal-backup-restore.md)。

首次安装锁定依赖、生成契约并构建镜像：

```powershell
make setup
```

日常轻量运行：

```powershell
make dev-lite
```

需要来源发现、AI 和完整观测能力时：

```powershell
make dev
```

停止平台：

```powershell
make down
```

两种入口都会先执行本地数据挂载检查。挂载或目录校验失败时应停止，不得临时切换到空卷继续运行。

## dev-lite 与完整 dev

| 能力组 | `make dev-lite` | `make dev` |
| --- | --- | --- |
| PostgreSQL、Redis、ClamAV、两套 MinIO、API、Web | 启动 | 启动 |
| Worker、Parser、Personal Source Worker、Publisher、Scheduler | 启动 | 启动 |
| 来源发现 `discovery` | 默认不启动 | 启动 |
| AI Worker | 默认不启动 | 启动 |
| Prometheus、Alertmanager、Grafana、OTel Collector | 默认不启动 | 启动 |
| 来源授权与发布门禁 | 不放宽 | 不放宽 |

仓库当前没有 `make dev-content` 入口。若将来新增，必须单独说明其服务集合和不具备的能力，不能把它当作 `dev-lite` 或完整 `dev` 的别名。

`dev-lite` 的正式验收状态是 12 个常驻容器和 5 个正常退出的一次性任务；完整模式的验收状态是 18 个常驻容器和 5 个一次性任务。计数只是该验收时点的运行证据，不能用于推断当前来源、AI 或 Feed 状态。

## Owner 的主要使用路径

1. 打开 `/sources` 登记公开 HTTPS 来源，查看探测结果、画像、健康和“实际运行”状态；启停开关只表达个人意图。
2. 在 `/settings/ai` 查看或配置受控 provider。Secret 只写不回显；没有授权、预算或有效配置时保持降级。
3. 在 `/technical-exceptions` 处理技术重试或安全隔离，在 `/feed-suppressions` 管理只影响展示的隐藏偏好。
4. 从首页、`/all`、`/digital`、`/safety`、`/industry`、`/hot` 或 `/search` 阅读 v2 投影，并从卡片进入统一 Event Reader。
5. 使用 `/saved`、`/daily`、版本差异、引用与关系纠正管理个人研究结果。

更具体的页面说明见[个人研究平台使用指南](docs/user-guide/personal-research-platform.md)。

## 当前已验收技术基线

- Git 基线：`a83dda41fd00175a93a864901a898d411bf53b83`
- 单一 Alembic head：`0054_policy_optimization`
- 本地正式 PostgreSQL 已从 `0047_owner_gold_override_go` 迁移到 `0054_policy_optimization`，关键业务计数保持不变。
- Docker dev-lite、完整模式和完整模式回切 dev-lite 已完成本地正式运行验收。
- Python、Node、契约、安全、浏览器端到端、无障碍和远端 CI 已在该基线上通过。

这是一份本地正式数据库与运行基线，不是外部生产部署、真实来源准入、真实 AI 调用或 production closeout。详见[正式 0054 迁移验收](docs/acceptance/personal/formal-0054-migration-2026-07-29.md)和 [Docker dev-lite 验收](docs/acceptance/personal/docker-desktop-dev-lite-2026-07-29.md)。

Issue #40 的自主机制已经取代旧的日常 Owner Gold 分类路径。Issue #36 的 Owner Gold `.4` `NO_GO` 仍作为历史事实保留，但不再是当前自主机制的运行入口；不得把该历史结果改写为通过，也不得用研究候选、fixture 或 override 代替真实闭环。

## 开发和测试入口

测试按变更风险分层：

```powershell
make check-fast
make check-pr
make check-release
make check-live
```

- `check-fast`：变更文件、受影响单测和必要类型检查；不启动 Docker、浏览器或网络。
- `check-pr`：完整廉价静态检查和单元测试，再按路径风险增加契约、迁移、前端或隔离集成。
- `check-release`：按当前精确 Git SHA 汇总已存在证据，只补跑尚未覆盖的完整门禁。
- `check-live`：正式数据、真实 Docker 栈、真实来源和外部服务验收，只能显式人工触发。

具体风险触发规则见 [AGENTS.md](AGENTS.md)。未知路径失败关闭并升级门禁；不能把其他 SHA、脏工作树或无法追溯的结果复用为发布证据。

## 架构、运维和历史索引

- 领域边界：[CONTEXT-MAP.md](CONTEXT-MAP.md)
- 当前架构：[个人研究模式架构](docs/architecture/personal-research-mode.md)
- v2 维护入口：[土木工程情报 v2 维护手册](docs/operations/intelligence-v2-maintainer-guide.md)
- 备份恢复：[个人平台备份恢复](docs/operations/personal-backup-restore.md)
- 架构决策：[docs/adr](docs/adr)
- 当前验收记录：[docs/acceptance/personal](docs/acceptance/personal)
- 历史阶段验收：[docs/acceptance/phase-2](docs/acceptance/phase-2)
- 来源研究记录：[docs/research](docs/research)
- 已退场企业流程：[docs/ENTERPRISE-PROCESSES-RETIRED.md](docs/ENTERPRISE-PROCESSES-RETIRED.md)
- 变更历史：[CHANGELOG.md](CHANGELOG.md)

历史文档中的 Txx、PERS、Owner Gold、旧迁移头和当时运行计数只描述对应时点，不得覆盖本 README 的当前基线，也不得删除或改写其历史证据。
