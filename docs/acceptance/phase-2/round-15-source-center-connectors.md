# 第 15 轮验收：来源中心 V2 与声明式连接器契约

## 结论

第15轮验收通过，来源中心V2和声明式连接器契约成立，可以进入第16轮。

开始前执行 `git rev-parse HEAD` 得到 `586d725f2c9a3150ee6053cdbd8477c5df878d75`，执行 `git status --short` 无输出，因此没有预存用户脏改动；随后出现的 dirty 文件均为本轮共享实现与验收证据，最终交付以 `git diff --check` 和本节门禁复核。真实外网请求: 0；未批准、试运行或激活任何具体来源，46 条种子仍全部为 `CANDIDATE/enabled=false`。

本次独立验收于 2026-07-16（Asia/Shanghai）在 Windows、Python 3.12.13、Node 24.14.0、pnpm 11.12.0、Docker 29.6.1、Compose 5.3.0、GNU Make 4.4.1 上从上述基线重新执行，不复用旧日志。验收期间首先以失败测试发现并修复结构化治理日志、告警/Runbook 可操作性和已经打过开发版 `0015` 的数据库同 revision 漂移；随后重新运行专项与全部全局门禁。浏览器插件在 Codex 更新后不可用，因此浏览器证据使用仓库固定 Playwright/Chromium 门禁，不声称采集人工截图。

## 状态兼容映射

V2 权威生命周期为 `CANDIDATE → COMPLIANCE_REVIEW → TRIAL → ACTIVE → PAUSED → RETIRED`。早期状态可直接退役；`ACTIVE` 必须先暂停再退役；`RETIRED` 为终态。旧列为兼容读取保留，但迁移会把运行行的旧 `enabled` 统一置为 `false`；迁移前的 `state/enabled` 原值保存在不可变迁移快照和状态事件中，仅在满足 downgrade 保护条件时恢复。客户端、CSV、模型输出和 Fixture 均不能写入或自报生产授权。

| 旧事实 | V2 初始状态 | 原因/试运行域 | 生产授权 |
| --- | --- | --- | --- |
| `CANDIDATE` | `CANDIDATE` | 原样保留 | 拒绝 |
| `COMPLIANCE_REVIEW` | `COMPLIANCE_REVIEW` | 原样保留 | 拒绝 |
| `FIXTURE_TEST` | `TRIAL` | `FIXTURE_REPLAY`；`LEGACY_FIXTURE_TEST` | 拒绝 |
| `APPROVED` | `TRIAL` | `FIXTURE_REPLAY`；`LEGACY_UNVERIFIED` | 拒绝 |
| `ACTIVE/enabled=false` | `PAUSED` | `LEGACY_DISABLED` | 拒绝 |
| `ACTIVE/enabled=true` 且仅有 Fixture 证据 | `TRIAL` | `FIXTURE_REPLAY`；`LEGACY_FIXTURE_ONLY` | 拒绝 |
| `ACTIVE/enabled=true` 且证据不足 | `PAUSED` | `V2_REAUTHORIZATION_REQUIRED` | 拒绝 |

迁移为 expand-only：保留旧列，追加迁移快照、状态事件和规则版本，任何旧行都不会自动映射为 V2 `ACTIVE`。应用回滚读取旧字段，但不得删除 V2 事件、审批、策略、配置、试运行和审计事实；数据库 downgrade 仅允许在没有迁移后治理事实的隔离环境执行，并从快照恢复旧语义。降级保护同时覆盖来源治理责任人、五维覆盖属性、声明角色、登记人、当前策略/配置/审批引用、生命周期/试运行域及其迁移快照基线；迁移后写入任一治理事实都会以 `ROUND15_DOWNGRADE_BLOCKED` 默认拒绝破坏性降级。`0015b_source_center_convergence` 是数据保留型收敛迁移：用于已经记录 `0015_source_center_v2`、但因开发期同 revision 漂移而缺少回放表、边界函数或扩展枚举的数据库；它补齐并事务内验证结构、触发器和角色权限，不删除既有治理事件。隔离回放实际经过 `0014b → 0015 → 0015b → 0014b → 0015 → 0015b`。

## 权威准入与治理模型

- `ACTIVE` 和生产采集资格由服务端根据当前生命周期、未过期政策、robots/条款/版权证据、治理责任人、合规决定、当前连接器配置、成功的 `LIVE_TRIAL`、异人生产审批共同计算；任一项缺失或过期即默认拒绝。这里的 `ACTIVE` 仅代表生产 eligibility，不代表本轮已经绑定生产执行器或动态调度；旧 MEM 调度入口固定返回零任务，并记录 `srbg_source_production_scheduling_blocked_total{reason="executor_binding_unavailable"}`。
- `FIXTURE_REPLAY` 与 `LIVE_TRIAL` 分域保存，Fixture 永不形成生产审批证据。暂停、退役或授权失效后不产生新调度资格，历史原始证据、文档版本、状态事件和审计保留。
- 登记人、政策/配置作者和试运行发起人不能审批自己的生产激活；审批者必须是具备 step-up 的不同 `source_admin` 或 `platform_admin`。
- 来源级允许域、最小抓取间隔、速率、User-Agent、存储、展示、下载、保留、法律保全、自动发布资格和 SLO 属于政策，不接受连接器覆盖。15 分钟 SLO 只有在政策明确标记适用、同时记录“来源授权已确认”和“技术条件已确认”时才可配置；不适用时目标必须为空并给出原因。
- `source_authority` 与 `source_independence` 分开保存等级、原因、证据引用和规则版本；没有 `source_trust_score`。两类评估的 `assessed_at` 必须携带时区，服务端统一归一为 UTC；无时区时间在契约和 API 边界均以 422 拒绝。来源属性不能替代具体事实的 claim/evidence、冲突和人工审核。

## 连接器能力

| 连接器 | 受控输入 | Schema 版本 / SHA-256 | 统一输出 | 本轮执行状态 |
| --- | --- | --- | --- | --- |
| RSS / Atom | 固定 feed URL、精确允许域 | `1.0.0` / `4691b104889eeb16f6cb006d8284b6a8f5bb4b0c58ea2fd331ddf63f7eb2830d` | DiscoveryRecord、FetchResult、RawObject、DocumentVersion | 固定 Fixture 回放 |
| JSON API | 固定 endpoint、RFC 6901 指针、首版分页仅允许 `NONE`、密钥引用 | `1.0.0` / `73b72a68d11b0da0698871e34f80534b1386d6ce7500a27b57f3c3792ed38447` | 同上 | 固定 Fixture 回放 |
| Sitemap | 固定 sitemap URL、精确允许域 | `1.0.0` / `7965a06972afb19af66f82ccbb5f21b7f4e88be33d64cc3548cff9cb62921ae5` | 同上 | 固定 Fixture 回放 |
| 列表 / 详情 | 固定列表 URL、受限 CSS 选择器 | `1.0.0` / `d6c892a10eb61d372e44f1156f48676fdd549027dcd91b20aaff4e1f01938ef6` | 同上 | 固定 Fixture 回放 |
| PDF | 固定 PDF URL 列表 | `1.0.0` / `daa3e6ded77fd467da20f21961b84177eb6b84a2bd5e60adf45ab110012883b8` | 同上 | 固定 Fixture 回放 |
| 人工 URL / 文件导入 | 受允许域约束的 URL 或受检文件 | `1.0.0` / `2abc649e1f15fbb452e27f452fca1eb27e5538bac2e7c07eaab42bd6345c860d` | 同上 | 固定 Fixture 回放 |

六类固定回放实现复用现有 `SourceAdapter` 发现/抓取语义和同一套解析协议，并通过隔离的 Fixture evidence store 验证 raw-first、幂等与版本行为，不复制整套站点管线。这里的固定回放是内存契约实现，不宣称已经交付动态调度或六类真实联网执行器；来源试运行中的人工 Fixture 上传另经 PostgreSQL/私有对象存储形成持久证据。配置预览是纯校验与脱敏，`network_io_performed=false`，既不写审计也不会建立试运行或生产采集；保存配置版本才写受控审计。没有交付特殊站点适配器；未来若通用连接器不足，必须另附不足说明、代码评审、固定样本、契约测试和失效监测。

## 配置 Schema

每个 `connector_definition` 固定 `connector_type`、`definition_version`、JSON Schema draft、schema SHA-256、内置执行器键和能力；每个 `connector_config_version` 只追加，引用定义版本、上一版本、规范化配置哈希、精确允许域、作者和时间。所有根对象 `additionalProperties=false`。

允许的配置只有无查询参数的固定 URL/URL 列表、精确主机、RFC 6901 JSON Pointer、受限选择器、首版固定为 `NONE` 的分页字段和人工导入开关。V1 对初始目标与每一跳重定向统一拒绝全部 URL query；需要静态非敏感查询参数的来源必须等待后续经评审的字段白名单，不能把 query 塞入配置。禁止 Python、JavaScript、Shell、模板表达式、动态主机、危险 scheme/port、内网/回环/保留/云元数据目标、URL 内凭据和未知字段。凭据只保存 `vault://source-connectors/...` 引用的受控列；配置 JSON 与 API 响应不含引用明文，读取投影只返回 `credential_configured`。

## 原始证据与安全边界

本轮六类固定响应（包括 RSS/API/Sitemap/列表发现响应）只在 `FIXTURE` 域执行；统一契约能够表达 `FIXTURE/TRIAL/PRODUCTION` 三域，但没有把 schema 能力冒充已执行的真实试运行或生产连接器。固定回放均先形成不可变 RawObject，再解析 DiscoveryRecord 或 READY DocumentVersion。Fixture store 的幂等键包含执行域和响应哈希，并可按 RawObject ID 回读原始字节及稳定的解析失败原因；持久人工 Fixture 另经 PostgreSQL/raw capture/私有对象存储落库，对象字节使用全局 SHA-256 内容寻址，来源、试运行和执行域隔离由 raw capture、领域关联和 ACL 表达，而不是伪造路径级隔离。保存 ETag、Last-Modified、内容/响应 SHA-256、发现时间和抓取时间；原文 `published_at` 只取明确发布日期，Sitemap `lastmod`、Atom `updated` 与 HTTP `Last-Modified` 分别保留为来源修改时间或响应元数据，不冒充原文发布时间。解析失败追加失败事实，不能替换已有 READY 版本。

试运行质量由数据库按试运行域重算：`raw_count` 只统计具备文档捕获关系的 document raw，discovery-only raw 不进入 READY 分母；`ready_ratio_bps = ready_count / raw_count`（基点、确定性取整）。在形成文档关系前被拒绝的原始提交单独计为 `rejected_raw_attempt_count`，同时属于 `security_failed_count`，但不进入 `raw_count`。来源级 rejected-raw attempt 与附件 `RECEIVED/ACCEPTED/REJECTED_CONTEXTUAL/QUARANTINED_INTRINSIC/INCONCLUSIVE/REJECTED_SECURITY_HISTORY` attempt 均追加保存私有元数据和对象绑定；恶意字节的历史负面事实不可被后续 CLEAN 覆盖，元数据/批次上下文失败和扫描不确定不会错误地永久污染同一哈希。

HTTP 客户端对每次请求、重试和重定向逐跳重新解析全部 DNS 地址，并核对实际 peer IP；拒绝任一非公网地址、回环、内网、保留、组播、IPv4-mapped/6to4、云元数据、DNS rebinding、HTTPS 降级、非允许域和危险端口。DNS 答案有固定数量上限，连接候选共享总 deadline；DNS、连接、读取和对象存储均有显式超时。请求还具备有限重试、封顶的 `Retry-After`/指数退避、按来源最小间隔与每分钟上限取更严格值的串行限速、受控 User-Agent、熔断、重定向上限和流式响应大小上限。携带凭据的请求不得跨源重定向，逐跳 URL 拒绝 userinfo 和全部 query。上传/附件在进入 CLEAN/READY 或可用状态前校验 Content-Length、实际字节、单项与聚合大小/数量、扩展名、声明/探测 MIME、PDF 页数、ZIP 条目/EOCD 尾随/展开大小/压缩比/路径/符号链接、嵌套危险 PDF、polyglot 和 HTML/PDF 主动内容；拒绝字节仅可作为私有隔离证据保留。

## 覆盖矩阵样例

覆盖矩阵按“工程行业 × 内容域 × 来源类型 × 地区 × 语言”聚合 `candidate/trial/active`，缺口由核心单元没有获准 ACTIVE 来源计算；Fixture 不计入 ACTIVE，也不使用网址总数或 1000 候选目标。

| 工程行业 | 内容域 | 来源类型 | 地区 | 语言 | Candidate | Trial | Active | 缺口 |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| 公路 | 安全规定 | 政府 | CN | zh-CN | 样例 | 0 | 0 | 是 |
| 桥梁 | 标准/指南 | 标准机构 | CN | zh-CN | 样例 | 0 | 0 | 是 |
| 隧道 | 事故调查 | 政府 | CN | zh-CN | 样例 | 0 | 0 | 是 |
| 铁路/轨道交通 | 数字化案例 | 综合/研究 | CN | zh-CN | 样例 | 0 | 0 | 是 |

这是结构样例，不代表具体来源已准入。分类词表增加 `RAIL_TRANSIT`，首批规划仍聚焦公路、桥梁、隧道、铁路/轨道交通及少量综合安全、标准和通用数字技术来源。

## 后台、RBAC 与审计

来源列表、详情、策略版本、连接器配置版本/纯预览、试运行、审批、暂停、恢复、退役、状态事件、审计和覆盖缺口复用 `AppShell` 与既有管理组件。普通 `viewer/editor/reviewer` 无来源后台权限；`auditor` 只读；`source_admin/platform_admin` 写操作要求 step-up，生产审批还要求职责分离。页面只渲染服务端 `available_actions`，不在浏览器推导下一状态；敏感配置只显示已配置状态。

结构化审计记录登记、政策决定、配置版本、试运行、审批、暂停、恢复和退役的主体、目标类型/标识、事件类型、请求 ID 和时间；当前后台只读投影展示事件、主体、受控原因文本、请求 ID 和时间，不声称展示完整 before/after。纯配置预览不写事实或审计。结构化 before/after 不写连接器 URL、密钥引用、Cookie、正文或响应体；自由原因字段由契约和数据库边界拒绝明显的 URL、凭据赋值、Bearer、Cookie 与控制字符，Runbook 同时要求管理员不得录入敏感信息。

## 指标与告警

交付 `srbg_source_lifecycle_state`、`srbg_source_runtime_authorization_mismatches`、`srbg_source_policy_rejections_total`、`srbg_source_trial_runs_total`、`srbg_source_trial_quality_count`、`srbg_source_trial_ready_ratio_basis_points`、`srbg_source_production_scheduling_blocked_total`、`srbg_connector_config_versions_total` 和 `srbg_source_coverage_gap_cells`。质量计数的 measure 明确区分 document raw、READY、解析失败、安全失败和 rejected raw attempt；并加入来源健康仪表盘、低基数告警和 `source_governance_v2` 默认拒绝 Runbook。登记、策略、配置、试运行、生命周期、覆盖缺口和生产调度阻断均产生字段白名单的结构化日志；日志只允许低基数动作/结果/原因、UUID 和质量计数，不记录 URL、配置正文、凭据引用、Cookie 或原始响应。Runbook 为每条来源告警明确响应角色、停止条件、恢复、验证与升级路径；配置回滚通过追加新版本完成，不篡改历史版本。

## 明确未做

- 没有动态数据库调度、自动候选发现、20 来源真实试运行或批量激活。
- 没有管理员代码输入、登录/验证码/付费墙/robots 绕过，也没有特殊站点适配器。
- 没有在条款、版权、下载或保留策略不明确时联网；真实外网请求: 0。
- 没有把 Fixture、E2E mock、CSV 或 46 条候选来源宣称为生产证据。

## 需求—实现—测试—证据矩阵

| 需求 | 最小实现 | 失败优先/回归测试 | 本次证据 |
| --- | --- | --- | --- |
| 权威生命周期、审批和兼容迁移 | V2 状态机、合规/异人审批、策略时效、状态/审计事件、旧状态快照、`0015` + `0015b` | 生命周期/API/迁移/真实数据库 RBAC | 非法跳转、自报 ACTIVE、Fixture 授权、职责分离、过期/缺证据均拒绝；隔离迁移往返通过 |
| 声明式连接器和密钥隔离 | 六个 `1.0.0` 定义、严格 Schema、固定执行器键、精确允许域、Vault 引用 | 六类契约、配置拒绝、API 脱敏、数据库列权限 | 未知字段、代码/表达式、动态目标、内嵌凭据均拒绝；仅 API 受控角色可读引用列 |
| 外部 I/O 与 SSRF/附件安全 | 逐跳 DNS/IP/peer/redirect 校验、deadline/重试/退避/限速/UA、流式大小与文件主动内容检查 | HTTP 安全、采集安全、上传/PDF/ClamAV/对象存储安全 | Fixture 349 项及 R15 专项安全测试通过；真实来源联网 0 |
| 六类统一 raw-first 链路 | `SourceAdapter` 语义、统一四段契约、内存固定回放、PG/私有对象存储持久 Fixture | connector replay、source fixture integration | 六类 Fixture 契约通过；持久 Fixture 隔离回放 1 项通过；解析失败不替换 READY |
| 来源策略不能被配置覆盖 | 政策权威的频率、SLO、存储/展示/下载/保留/法律保全/自动发布 | 生命周期、连接器契约、发布边界 | 配置覆盖字段由 Schema 拒绝；生产资格由服务端现查事实计算 |
| 暂停/退役、审计和生产旁路防护 | 调度入口默认阻断、数据库执行域触发器、历史事实保留、PublicationService 边界 | scheduled gate、publication boundary/integration、Round14 审计 | 零新调度；伪造 PRODUCTION 文档版本拒绝；发布路径审计通过 |
| 来源后台完整闭环 | 列表/详情、策略、配置预览、Fixture 上传/完成、审批/暂停/退役、审计、覆盖矩阵 | Web 单测、R15 E2E、全站 E2E/a11y | R15 3 E2E + 1 axe；全站 45 E2E + 14 axe；auditor 只读 |
| 观测与运维 | 低基数指标、字段白名单结构化日志、告警、仪表盘、Runbook | logging、metrics、observability/delivery | 日志敏感字段负向测试及 4 项基础设施观测测试通过；Compose 服务健康 |

运行库复核显示 Alembic head 为 `0015b_source_center_convergence`、Fixture replay 表和 DocumentVersion 执行域触发器存在；迁移前已有治理事件 `019f690d-8efb-7202-bfc0-6aad226a61c5` 仍存在。`srbg_api_role` 可在受控服务内读取 `credential_ref`，`srbg_runtime`、`srbg_worker_role`、`srbg_publication_writer`、`srbg_model_role` 均无该列读取权限。

## 门禁证据

| 命令 | 最终结果 |
| --- | --- |
| `make phase2-round14-test` | 退出 0；27 passed；Round14 迁移回放与发布路径审计通过 |
| `make phase2-round15-test` | 退出 0；351 后端/契约/安全/基础设施、84 Web 单测、3 管理端 E2E、1 axe；Round15 `0015b` 迁移回放通过 |
| `make source-fixture-test` | 退出 0；1 个隔离 PostgreSQL/MinIO 来源 Fixture 纵向回放通过；迁移链 `0014b → 0015 → 0015b → 0014b → 0015 → 0015b` |
| `make lint` / `make typecheck` | 退出 0；Ruff、令牌、ESLint 通过；mypy 104 个源文件、Nuxt/TypeScript strict 通过 |
| `make test` / `make contract-test` | 退出 0；Python 805 passed/26 按环境跳过、UI 53、Web 84、契约 75；生成契约可复现 |
| `make security-check` | 退出 0；pip/pnpm 审计无 high/critical，Trivy secret/misconfiguration 无 high/critical；仅 1 个 low npm 发现 |
| `make fixture-replay` / `make quality-gate` | 退出 0；Fixture 349 passed，Round09 对抗评估通过；总质量门禁再次完整通过（Python 805、UI 53、Web 84、契约 75） |
| `make web-e2e` / `make web-a11y` | 退出 0；全站 Playwright 45 passed；axe 14 passed；Compose 服务全部健康 |

以上结果均来自最终实现文件上的实际命令，不以计划、旧日志或 Fixture 自报代替证据；所有来源联网计数仍为 0。
