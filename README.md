# 四川路桥·智安情报

本仓库是绑定本机回环地址、由单一 `owner` 使用的个人研究平台。它覆盖公开来源添加与探测、受控采集、来源健康与画像、证据化内容、Feed、搜索、日报和自动关系；不提供企业模式开关、审批工作台或 `source_admin`、`platform_admin`、`reviewer` 等产品角色。

## 当前维护状态

父 Spec #40 的自动内容机制已推进至 Issue #46：SourceStream 内容 run 在创建时固定不可变 `policy_bundle_id`，离线回放与 SHADOW 事实不具备生产授权，Champion/Challenger 通过独立追加式激活账本切换，并由生产健康窗口自动回滚。Issue #36 的历史 Owner Gold `.4` 仍是 70% precision、70% recall、5 条锁定负例泄漏的标准 `NO_GO`；该事实未被改写、降阈值或伪造通过，也不再作为 ADR-0005/0006 自主机制的全局阻断。

机制工程完成不等于某个 Challenger 已晋级，更不等于 `PRODUCTION_CLOSEOUT`。真实来源、真实 DeepSeek、真实 Feed 抽检和运行窗口仍必须分别形成可审计证据。下一轮开始前请先阅读[土木工程情报 v2 维护入口](docs/operations/intelligence-v2-maintainer-guide.md)与 [ADR-0006](docs/adr/0006-qualification-policy-activation-and-rollback.md)。

## Qualification Policy 生命周期

- LIVE run 的 bundle 在 PostgreSQL handoff 事务中固定；同一 run 的回调、重试、recheck 和技术恢复不读取后来激活的策略。
- 私有 replay 可通过 `scripts/replay_autonomous_policy_private_benchmark.py --persist-evaluation` 追加聚合评估；`authorizes_production` 固定为 `false`。
- 通过离线门禁的 Challenger 只进入固定 canary 的 SHADOW 执行；SHADOW 在 Item、claim、Event 和 Feed 之前终止，`affects_production` 固定为 `false`。
- 每分钟策略生命周期任务只消费完整聚合窗口。晋级要求离线与 SHADOW 两套门禁同时通过；生产回归会追加一次回滚到前任 Champion。
- 当前激活状态来自 `active_qualification_policy_v2` 派生视图；历史 bundle、decision、evaluation、shadow、activation 和 health 事实均不修改。

## 当前架构

- Web：Nuxt 4、Vue 3、TypeScript strict、Tailwind CSS、Nuxt UI 4。
- API/Worker：Python 3.12、FastAPI、Pydantic、Celery。
- 权威事实：PostgreSQL；Redis 只用于缓存、锁和任务队列。
- 原始证据：私有对象存储，始终先保存原始响应再解析。
- 发布边界：`PublicationService` 是 Feed、搜索和日报投影的唯一写入路径。
- 身份：仅回环地址固定 `owner` 和必要的内部数据库/Worker 服务主体。

公网安全、robots、条款、逐跳 SSRF 校验、限速、预算、熔断和原始证据保留不会因个人模式降低。证据事实与 AI 判断保持不同语义；无证据的关键数字和日期不得发布，未验证 AI 不得进入事实索引。

## 土木工程情报 v2 分类门禁

候选文档在事实抽取和 Event 创建前必须先通过服务端 `DirectRelevance` 门禁。输出固定包含唯一 `PrimaryType`、十一类 `EngineeringObject`、可选 `TUNNEL_GAS_MONITORING` / `CONSTRUCTION_MACHINERY`、受控内容形态、证据块定位、置信和复核原因；服务端同时要求正文包含工程生命周期的实质性新事实。交通隧道瓦斯必须组合 `TUNNEL` 与 `HIGHWAY` 或 `RAILWAY`；矿井瓦斯只属于 `MINING`。锁定负例、分类失败、低置信、主类并列、证据定位不匹配或需要 Owner 判断时只创建非公开复核 case，不进入抽取或阅读投影。

结构回放评估只消费外部预测 JSON，不内置或生成 Owner 标注：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_intelligence_v2_qualification.py `
  --input .\path\to\predictions.json
```

输入包含精确的 `corpus_version` 和 360 条 `{case_id, directly_relevant, primary_type}`。输出始终标记 `label_authority=STRUCTURAL_REPLAY`、`authorizes_auto_pass=false`；它只能验证结构与失败关闭行为，不能冒充 HUMAN_OWNER Gold、来源准入、真实 DeepSeek Schema 成功、运行窗口或 GO 证据。

20 条人工试标只用于熟悉流程：10 条正例、5 条边界例、5 条锁定负例。它应保留真实哈希、UTC 标注时间和证据定位，但固定不授权自动通过，也不输入生产校准器冒充完整语料。Issue #36 的独立 40 条协议与 `.4` NO-GO 作为历史校准事实保留；现行自主策略生命周期由父 Spec #40、ADR-0004/0005/0006 和对应聚合门禁约束。

真实生产 Owner Gold 校准使用独立私有标注与候选预测文件；仓库不附带这些私有文件。`.1` 已以 Owner 分布 `NO_GO` 退役，仅保留 15 条正例培训回放；`.2` 因标注前发现正例中心事实错配而整版退役；`.3` 因标注前发现三个工程对象元数据没有正文证据而整版退役。生产消费者只接受重新封存的 `.4`：

```powershell
.\.venv\Scripts\python.exe scripts\calibrate_intelligence_v2_owner_gold.py `
  --annotations D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\annotations\owner-gold.jsonl `
  --predictions D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\predictions\qualification-predictions.jsonl `
  --prediction-seal D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\predictions\prediction-seal.json `
  --output D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\calibration\qualification-calibration.json `
  --corpus-version owner-gold-2026-07-20.4 `
  --rule-version intelligence-v2-qualification-1.0.0 `
  --model-id deepseek-v4-flash `
  --prompt-version ai01-classify-v1 `
  --calibrated-at <UTC-ISO-8601>
```

`.4` 标注必须从盲包逐案输入，不能读取 prediction 目录，也不能自动填充 Owner 判断：

```powershell
.\.venv\Scripts\python.exe scripts\annotate_intelligence_v2_owner_gold.py `
  --pack "D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\blind\blind-pack.json" `
  --draft "D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\annotations\owner-gold-draft.json" `
  --output "D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\annotations\owner-gold.jsonl"
```

Issue #36 校准入口严格要求 40 条冻结语料：20 条正例、10 条边界例和 10 条锁定负例；正例三主类型固定为 7/7/6，并要求 40 条预测在 40 条 `HUMAN_OWNER` 标注之前独立封存。每条保存 UTC 时间、规范化内容与原始对象 SHA-256、稳定证据定位以及 corpus/rule/model/prompt/schema 版本。阈值从实际预测置信分布中派生；缺失、哈希或版本错配、precision/recall 低于 90% 或锁定负例泄漏都会输出确定性 `NO_GO`，不会回退到硬编码 0.90。旧 360 条 `STRUCTURAL_REPLAY` 仍只用于结构回归，不能签发生产授予。生产 qualification、SourceAdmission、PublicationService 和 production closeout 只消费版本完全匹配的追加式校准事实；没有校准事实时自动通过保持禁用。

## PERS-10 企业治理退场

PERS-10 迁移序列截至 `0033_controlled_ai_budget_bridge`。`0029` 在同一事务中归档旧治理关系；`0030` 补齐三个企业数据库角色的规范快照并删除最后的来源治理角色；`0031` 新增无人值守真实试点的内部预算与停止账本，`0032` 只允许 Worker 读取该账本，`0033` 原子联动受控 AI 费用与既有月度账本，均不恢复任何企业治理能力。归档保存规范化 JSON、逐行 SHA-256、分类计数和分类汇总 SHA-256；数量、哈希、角色状态或跨数据库依赖不一致时拒绝退场。正常业务角色没有归档 Schema 使用权，业务代码禁止读取归档。

已提交工程基线的迁移头为 `0045_t12_media_delivery`；当前 #36 工作树另有未提交的 `0046_owner_gold_prediction_seal`，本地数据库还已应用未批准的 `0047_owner_gold_override_go`。这三个状态不得混写成同一个可复现基线。0033 复用既有 AI 月度账本，并把受控运行费用预留、结算、释放与 10 元保守上限原子联动；它不恢复企业治理结构。降级先重新验证每行和每类 manifest，损坏时以 `PERS10_ARCHIVE_CORRUPT`/`PERS10_ARCHIVE_HASH_MISMATCH` 中止；验证通过后恢复旧表、数据、约束、触发器、授权和 0029 前调度函数。含受控试点、T09 热点或 Owner Gold seal/override 事实的当前业务库拒绝未备份的破坏性降级，应从已验证备份在隔离实例恢复。操作见[迁移回滚 Runbook](docs/operations/pers10-migration-rollback-runbook.md)和[备份恢复说明](docs/operations/personal-backup-restore.md)。

旧 `/api/v1/admin/**` API、企业后台任务、生成契约、页面组件、运行时模块和企业产品角色均已退场；只保留 `owner` 语义及必要内部服务主体。历史企业文档的状态总表见[失效企业流程说明](docs/ENTERPRISE-PROCESSES-RETIRED.md)。

## 本地运行

首次安装依赖并构建镜像：

```bash
make setup
```

```bash
make dev
make smoke
```

正式业务数据、备份与验收报告的持久化根目录是 `D:\SRBGData`。七类在线服务数据位于 `srbg-data.vhdx` 的 ext4 文件系统；`make dev` 和 `make runtime-ready` 会先执行 `scripts/mount_personal_data.ps1`，挂载或目录校验失败时拒绝启动。切换前必须按备份恢复说明完成隔离恢复验证，不得直接移动仍在使用的数据目录；原 Docker 数据卷只停用并保留。

Web 与 API 默认只绑定 `127.0.0.1`。不要把固定本地身份头、端口或数据库凭据代理到局域网或公网。Secret 只允许通过环境变量或 Git 忽略的本地 Secret 文件提供，不得提交到仓库。

个人操作说明见[个人使用手册](docs/user-guide/personal-research-platform.md)，架构和边界见[个人研究模式架构](docs/architecture/personal-research-mode.md)。

正式 Web 界面采用低饱和牛油果渐变窗格和高密度证据卡：`/` 将带可见标签的搜索作为首要入口，DOM 与视觉顺序固定为“搜索区域 → 今日精选 → 时间线”，过滤 Feed 页面不重复该入口；`/sources` 将添加、健康概览和来源操作集中展示；`/events/{id}` 使用 Owner Reader B 统一详情页，宽屏为证据正文主栏与 sticky 来源上下文侧栏，窄屏恢复来源上下文、原文摘录、AI 总结、材料动作和折叠附录的单列语义顺序。所有点击反馈使用设计令牌并尊重系统“减少动态效果”设置。

## 质量门禁

```bash
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make quality-gate
make personal-source-test
make personal-content-test
make personal-migration-test
make t06-ai-runtime-test
make t08-evidence-search-test
make t09-hotspot-test
make web-e2e
make web-a11y
```

## 证据化内容准备候选

土木工程情报 v2 的内容准备只消费当前文档版本中 active、已接受且带有效证据的 claims。服务端从同一证据块截取一段连续 `SourceExcerpt`（最长 500 字），再把最小必要 claims 与摘录交给协议等价摘要 stub；返回值必须满足 `docs/codex-kit/assets/schemas/summarize-v2-output.schema.json`，正文总长为 300–500 字，并明确区分引用 claim 的事实段和 AI 判断段。

候选以追加式事实保存并进入仅 Owner 可见的复核投影。文档版本或 accepted claims 变化、来源撤回或更正都会使旧候选失效；事实复核与 AI 摘要复核是两个独立决定。该链路不直接写 Reader 投影或发布状态，正式发布仍只能经过 `PublicationService`。协议 stub、fixture 和本地回放不代表真实 DeepSeek Schema 成功、Owner Gold、来源准入、运行窗口或 GO。

验收范围与证据见[本票验收记录](docs/acceptance/phase-2/t04-evidence-content-preparation.md)。

## T06 DeepSeek 运行与结果投影

T06 使用非测试环境唯一允许的真实 provider `deepseek`，公网请求固定发送目录模型 `deepseek-v4-flash`；数据库保存并核验版本化 profile、prompt、Schema、输入文档版本、延迟、Token 与成本。Secret 是否存在只表示“已配置”的一个条件，不表示“当前可用”。“可用”还要求 60 秒内 Worker 心跳、队列与预算健康、运行 provider/model 与当前配置完全匹配，并且 24 小时内存在一条真实获准内容通过 `summarize-v2-output-1.0.0` 的成功事实；runtime probe、固定 canary、CI 协议 stub 和单独 Secret 均不能生成该事实。

每次物理调用前、回调处理时和成功事实落账时都会重新核验当前 SourceAdmission、Source/Owner 运行意图、当前 DocumentVersion、raw CLEAN 与安全事实、TRIAL/PRODUCTION 执行域、DeepSeek 激活配置和剩余预算。撤权后只允许结算回调中可验证的 Token/费用，不再解析、修复、保存或发布模型内容。网络瞬时失败使用 5/15/45 分钟、两小时封顶的持久补偿；永久 Schema 拒绝不重试。

原文摘录独立于 AI 结果持久化。Reader 的七种摘要状态由服务端投影确定；AI 不可用时，已通过 PublicationService、R3/R4 和当前 accepted-claim 指纹门禁的内容仍展示来源与 `SourceExcerpt`，恢复后由耐久 outbox 自动重建且不会重复 Event、claim、摘要或投影。`make t06-ai-runtime-test` 只执行一次性 PostgreSQL 迁移回放、协议 stub 和 UI 状态回归，不调用真实 DeepSeek，也不构成 Owner Gold、来源准入、运行窗口或 GO。详见 [T06 验收记录](docs/acceptance/phase-2/t06-deepseek-runtime-projection.md)。

## T05 Reader 发布投影

土木工程情报 v2 的普通 Reader 只读取 `PublicationService` 从 PostgreSQL 权威事实重建的当前投影。FULL 投影要求当前分类资格、文档版本、accepted claims、证据和内容候选一致；R3 只返回标题、主类型、来源官方性、两个可空时间、原文链接和待审核状态；R4、未决、claim/summary 失配及隔离内容在普通 API 中统一不可见。Owner 可通过独立的隔离端点读取 R4 安全元数据与隔离原因，正文、摘录、claims、AI 摘要和媒体不会进入该响应。

`make t05-publication-test` 会在一次性 PostgreSQL 数据库、Redis 和私有 MinIO 桶中执行 `0039 → 0040 → 0039 → 0040`，并验证 FULL/R3/404、重试无物化重复、许可媒体读取和 v1 归档逐行/汇总 SHA-256。Fixture 只证明协议与持久化行为，不代表 Owner Gold、真实 DeepSeek 成功、来源准入、运行窗口或 GO。详见 [T05 验收记录](docs/acceptance/phase-2/t05-reader-publication-projection.md)。

## T10 Owner Reader B 统一详情页

正式 `/events/{id}` 只消费既有 `/api/v2/events/{id}` 判别联合。FULL 在标题区、证据主栏和来源上下文侧栏中分别呈现 PrimaryType/facets、ClaimBasis、来源官方性、独立人工复核状态、两个可空时间、热点理由（不显示总分）、SourceExcerpt、结构化 AISummary、许可媒体和更正提醒；AI 事实段显示 AcceptedClaim 引用，判断段明确标识，七种 SummaryState 使用服务端确定性文案。R3 只显示服务端白名单元数据与待审核状态，R4、分类未决和 claim 失败仍由服务端返回 404，前端不接收完整对象后再隐藏。

页面在 1024px 起使用无嵌套滚动的 sticky 上下文侧栏，在更窄视口按“标题与提醒 → 来源上下文 → SourceExcerpt → AISummary → 媒体与单一 ReaderActions → ReaderAppendix”回流。同一原文或附件动作只渲染一次；无许可附件只链接原站。正式验收覆盖 320、640（200% 等价）、768、1024、1280、1440、1920px、长标题、缺失时间、键盘、屏幕阅读器、axe、减少动画和横向溢出。详见 [T10 验收记录](docs/acceptance/phase-2/t10-owner-reader-b.md)。

## T11 ReaderAppendix 治理附录

FULL Reader 底部的治理附录默认折叠，首次展开才读取 `/api/v2/events/{event_id}/appendix`，随后折叠/展开复用已加载结果。附录明确区分 AcceptedClaims／证据与自动处理结果，分开展示人工审核关系和自动关系，并按时间倒序呈现事故初报、续报、最终调查、处罚、整改及结构化更正。加载失败只影响附录，保留主阅读内容和可聚焦重试；空内容、重内容和截断分组均有独立状态。

普通读取只消费 PostgreSQL `security_barrier` 治理视图中的当前 FULL、R1/R2 投影；R3/R4、未决或失效内容保持 404，底表和审核备注不授予 projection reader。阅读页不复制治理表单，只在存在安全 case 时深链 `/review?case_id=...`，否则回退 Owner 复核列表；所有纠正写操作继续使用既有 v1 边界。`make t11-reader-appendix-test` 回放 `0043 → 0044 → 0043 → 0044` 并验证真实 PostgreSQL 权限、组合读取、R3 失败关闭、契约和组件状态机。Fixture 不代表 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口或 GO。详见 [T11 验收记录](docs/acceptance/phase-2/t11-reader-appendix.md)。

## T12 许可媒体与附件安全交付

媒体登记只消费服务端权威的当前 `CLEAN` 附件、raw 对象、成功采集尝试、原始 URL 哈希与许可证据。可预览图片在字节、像素、实际 MIME 和解码边界内重新编码为内容寻址 PNG，正式 Reader 只引用 `/api/v2/media/{id}/preview` 的同源安全派生物；解码失败或无安全派生物时 `preview_url` 为 `null`，页面不会生成 `<img>` 或退回远程原图。

`PublicationService` 只向 FULL 投影当前许可且扫描状态仍为 `CLEAN` 的预览或下载动作；R3 不投影媒体，R4 普通读取保持 404。无再分发许可的附件只显示名称与原站链接；获许可附件在每次下载时重新验证权威事实和私有对象存在性，再返回最长 300 秒的签名 URL。`make t12-media-delivery-test` 在一次性 PostgreSQL 与私有 MinIO 中回放 `0044 → 0045 → 0044 → 0045`，覆盖缺失对象、存储失败和扫描状态变化。Fixture 不代表 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口或 GO。详见 [T12 验收记录](docs/acceptance/phase-2/t12-licensed-media-delivery.md)。

## T07 受控 SourceStream 影子采集

土木工程情报 v2 将机构级 `Source` 与其有界 API、RSS、站点地图、列表或集合路径 `SourceStream` 分开建模。同一机构的多个栏目只增加流数量，不增加机构数量。`ADMISSION_READY`、`BOUNDARY_DISCOVERY`、`MANUAL_SHADOW` 仅记录研究去向；Owner 的 `desired_enabled` 仅记录个人意图；二者都不能直接启动采集。

逐流 SourceAdmission 只有在公网安全、robots、条款、版权、访问边界、限速、预算、质量、熔断和运行事实全部明确通过且仍在有效期内时才可能授予影子运行。Worker 在发现前和每次抓取前重新核验服务端授权，使用统一 `SourceAdapter`，先保存不可变 raw 响应、元数据和服务端 SHA-256，再按真实 MIME 解析 HTML、PDF 或 RSS。解析失败保留 raw；成功只把 DocumentVersion ID 交给既有 DirectRelevance、AcceptedClaims、SourceExcerpt 和 PublicationService 链路。AI 不可用时，已经通过证据门禁的内容仍可走 excerpt-only 降级路径。

`make t07-source-shadow-test` 在一次性 PostgreSQL 数据库中回放 `0041 → 0042 → 0041 → 0042`，验证机构/流计数、流级准入、Owner 撤权、追加不可变和 raw-first HTML/PDF/RSS 行为。测试 fixture 不代表真实来源准入、真实运行窗口、Owner Gold、DeepSeek 成功或 closeout GO。详见 [T07 验收记录](docs/acceptance/phase-2/t07-controlled-source-shadow.md)。

## T16 水利部与国家能源局 SourceStream 发现

Issue #17 在机构级 Source `GOV-MWR` 与 `GOV-NEA` 下各保存一条精确流。水利部使用官方政务服务平台的 HTTPS 通知公告集合，只读取列表题录，不追随其中降级为 HTTP 的外链详情；过滤器只接受水利工程建设、监理、质量、安全、数字化和科技成果事实。国家能源局使用煤炭司持续更新栏目，只接受直接涉及能源工程、矿山、工程装备及其生命周期的事实，单篇煤矿智能化文章或批次材料不再被当作持续集合。

两条流都已固定集合入口、允许主机/路径、连接器、MIME、日频、策略版本与点时公网/响应证据。robots 404 按 RFC 9309 的 unavailable 规则处理；访问和版权范围限定于《政府信息公开条例》允许获取的主动公开信息及《著作权法》第二十四条的单一 Owner 个人研究合理使用，禁止公开再分发。两流达到 `BOUNDED + ADMISSION_READY` 研究去向，但仍保持 `desired_enabled=false`、无 SourceAdmission、无实际运行。

`make t16-source-discovery-test` 离线验证精确边界、metadata-only 不追随详情、未知合规事实不得升级、正负领域过滤，以及研究写能力隔离；同时回归 T20 共用模型。完整证据与哈希见 [T16 验收记录](docs/acceptance/phase-2/t16-mwr-nea-source-stream-discovery.md)。

## T20R 首批 W5 替代 SourceStream

原 W5 中国中铁与三一集团研究因中国中铁版权条款与 raw-first 冲突而不再继续。替代组合使用既有 `ENT-002` 中国建筑“企业动态”和新增候选 `ENT-010` 徐工集团“施工案例”；首批来源总数仍为十个，没有把栏目虚增为机构，也没有复用原两源身份。

中国建筑仅接受在域工程对象与规划、设计、施工、竣工、运营、养护、安全或监测事实同时出现的项目记录，排除党建、人事、资本市场、奖项、纯商业和品牌内容，ClaimBasis 固定为 `PROJECT_FIRST_PARTY_RECORD`。徐工列表通过固定 same-host POST 表单枚举施工案例，只接受施工机械直接服务工程生命周期的事实，排除制造 ERP、产线、工厂、交付和品牌内容，性能与效果固定为 `MANUFACTURER_CLAIM`。

两流研究结论均为 `BOUNDED + ADMISSION_READY + DISABLED`；仅允许 Owner 私有 raw HTML、题录、必要短摘和原链，禁止附件、图片、视频、全文及公开再分发。清单不写 Owner 意图、SourceAdmission 或运行状态；真实启用仍必须通过服务端全部门禁。详见 [T20R 验收记录](docs/acceptance/phase-2/t20r-cscec-xcmg-source-stream-discovery.md)。

## T20 中国中铁与三一集团 SourceStream 发现（已被替代）

Issue #21 的发现清单只复用既有机构 Source `ENT-003` 与 `ENT-009`，每个机构各登记一个精确、可审计的集合边界。三一限定为官方 `/case/` 施工案例列表/详情路径，按一天一次、单分钟最多一次请求的研究策略保存，流级预过滤要求“既定工程对象 + 工程生命周期事实”，并锁定排除制造 ERP、灯塔工厂、产线改造及泛工业数字化。所有产品参数和应用效果只能标记为 `MANUFACTURER_CLAIM`。

中国中铁限定为 `/web/xwzx61/zfgsdt39/` 子分公司动态列表/详情路径，使用“工程对象 + 生命周期事实”正向门禁并排除经营、党建、品牌、人事和投资者内容；合格材料也只能是 `PROJECT_FIRST_PARTY_RECORD`。该集合虽已形成稳定分页且 GET/robots 可核验，但官网条款禁止未经书面许可自动存入信息检索系统，与平台 raw-first 不变量冲突，所以当前保持 `MANUAL_SHADOW` 和停用，不能解除后续真实准入波次。

`make t20-source-discovery-test` 离线验证精确 URL/主机/路径/MIME/频率边界、公网 IP 与重定向约束、正负例、ClaimBasis 以及“只追加研究 disposition”的能力隔离。测试不联网，也不会改变 Owner 意图、SourceAdmission 或实际运行。真实核验记录与响应 SHA-256 见 [T20 验收记录](docs/acceptance/phase-2/t20-crec-sany-source-stream-discovery.md)。

## T29R《建筑科学与工程学报》与中国交建替代 SourceStream

Issue #39 用新增候选 `RES-013`《建筑科学与工程学报》替代中国建研院的受阻席位，并复用 `ENT-001` 中国交建和其既有工程简讯流。期刊只锁定 `publicationIndexId=1474` 的当前刊期 JSON 入口，以及由该入口返回的刊期 ID 所限定的文章列表；query 只允许 `size<=50` 与 `showCover=true`。根站、搜索、全文、附件和单篇任意 URL 都不属于该流。

期刊只接受直接涉及十一类工程对象的论文研究结论，排除纯材料化学且无工程对象、公告、征稿、会议和排行，ClaimBasis 固定为 `RESEARCH_CONCLUSION`，不因同行评审或出版升级为独立验证。两流均为研究态 `BOUNDED + ADMISSION_READY`，但保持候选、停用、无 SourceAdmission、无运行、无 PAUSE 和无覆盖信用；robots 404 仅表示未发布，不表示许可。`make t29r-source-discovery-test` 验证替代、精确 API/query、ClaimBasis、版权投影和运行权限失败关闭。详见 [T29R 研究报告](docs/research/2026-07-20-issue-30-replacement-source-stream.md)与[验收记录](docs/acceptance/phase-2/t29r-jace-cccc-source-stream-discovery.md)。

## T29 中国建研院与中国交建 SourceStream 发现（已被替代）

> **已被 T29R 替代。** 原始研究与法律 blocker 证据继续保留；Issue #30 的关闭不表示中国建研院获得复制许可或原两流验收通过。

Issue #30 继续复用 `RES-003` 中国建筑科学研究院和 `ENT-001` 中国交建两个机构级 Source；“中国交通建设集团”等全称只作为 canonical alias，不重复建源。中国交建只锁定官网 `/news/jcxw/jx/` 的稳定分页“简讯”列表与详情路径，逐条要求既定工程对象和中标、开工、合龙、贯通、完工、验收、通车、投运等生命周期事实同时成立，并排除经营业绩、资本市场、党建、人事、招聘和无工程新事实的企业新闻。工程节点是 `PROJECT_FIRST_PARTY_RECORD`，效果或领先性仍是 `MANUFACTURER_CLAIM`，两者都不是独立验证。

中国建研院当前公开 origin 为 `cabr.cn`，但科研项目与获奖情况都只是陈旧静态汇总，且法律声明禁止未经书面许可复制、传递和设置链接，与平台 raw-first 约束冲突。因此该候选保持 `CANDIDATE + MANUAL_SHADOW`，自动轮询频率为空；中国交建仅获得研究态 `BOUNDED + ADMISSION_READY`。两个 Source 仍为 `desired_enabled=false`、无 SourceAdmission、无运行。浏览器观察未同步固化 raw 字节时，清单将 SHA-256 显式保存为 `null`，不会用 DOM、截图或边缘错误体伪造。`make t29-source-discovery-test` 离线验证这些边界，详见 [T29 研究记录](docs/research/2026-07-20-cabr-cccc-bounded-stream-discovery.md)与[验收记录](docs/acceptance/phase-2/t29-cabr-cccc-source-stream-discovery.md)。该组合后由 #39 替代，原 blocker 未被改写。

## T31 广联达与中国煤炭科工集团 SourceStream 发现

> **已被 T31R 替代。** 原始研究证据仍保留；广联达和中国煤炭科工集团并未通过自动采集法律边界，也未被伪装成准入成功。

Issue #32 分别只保留一个机构 Source：既有 `ENT-007` 广联达，以及第二批 campaign 中尚未写入来源注册表的中国煤炭科工集团候选。广联达锁定 `/case/index/5.html` 数智施工案例集合与同主机数字详情；中国煤科锁定 `idss=183` 的“煤科硬核”集合与同主机详情。根站、全部案例、集团综合新闻、搜索、采购公告、外部媒体和单篇材料均不属于这两个 SourceStream。

两个集合均形成 `StreamReadiness=BOUNDED`，并保存精确主机、路径/查询、HTML list-detail 连接器、MIME、日频、限速、策略版本、内容正负过滤以及真实 DNS、HTTP、robots、条款、版权和响应 SHA-256。广联达协议禁止未经书面授权的爬虫、复制和镜像；中国煤科法律声明要求复制网站内容前取得书面许可。两项都与 raw-first 强制保存冲突，因此当前只能是 `MANUAL_SHADOW + DISABLED`，不能升级为 `ADMISSION_READY` 或解除后续准入波次。

`make t31-source-discovery-test` 离线验证版本化研究契约、两个机构计数、精确集合、研究/运行隔离、内容正负例、ClaimBasis，以及矿井瓦斯只归 `MINING` 且不得自动授予 `TUNNEL_GAS_MONITORING`。详见 [T31 研究报告](docs/research/2026-07-20-glodon-ccteg-source-stream-discovery.md)和[验收记录](docs/acceptance/phase-2/t31-glodon-ccteg-source-stream-discovery.md)。

## T31R 四川省住房城乡建设厅与贵州省能源局替代流

Issue #38 以两个独立政府公开栏目替代 Issue #32 的法律阻断席位。四川省住房城乡建设厅只锁定科技栏目，且必须同时出现房屋建筑/市政工程对象与智能建造、BIM/CIM、城市生命线或工程监测生命周期事实；贵州省能源局只锁定能源科技管理栏目中的智能煤矿、智能采掘、矿山安全监测、矿山装备/机器人或煤矸石工程技术事实。矿井瓦斯仍只归 `MINING`，不得自动授予 `TUNNEL_GAS_MONITORING`。

两流均为研究态 `BOUNDED + ADMISSION_READY`，但 Source 仍是 `CANDIDATE + disabled`，无 SourceAdmission、无实际运行、无 PAUSE、无覆盖信用。robots 404 只记录为“未发布”，不解释为许可；公开投影仍限题录、accepted claims、必要短摘和原文链接，禁止图片、附件和全文再分发。`make t31r-source-discovery-test` 验证替代关系、精确边界、合规状态、正负过滤和运行权限隔离。详见 [T31R 研究报告](docs/research/2026-07-20-issue-32-replacement-source-streams.md)和[验收记录](docs/acceptance/phase-2/t31r-sichuan-housing-guizhou-energy-source-stream-discovery.md)。

## T23 四川省交通运输厅 SourceStream 发现

四川省交通运输厅继续只计一个 Source（`GOV-015`）。T23 排除综合门户、建设管理聚合页、搜索和单篇材料，锁定四个精确 `HTML_LIST_DETAIL` 流：科技与信息化 `c101567`、建设动态 `c101544`、质量监督 `c102110` 和安全监督 `c102111`。每条流只允许 `jtt.sc.gov.cn` 的固定分页与同栏目详情路径，候选频率为每日一次、每分钟最多一次请求；科技流必须经过工程对象与生命周期正向过滤，其他三流也排除招采、党建、会议、道路运输经营等非工程中心事实。

点时核验确认 HTTPS 列表和样本详情均公开零跳可达，`robots.txt` 为 404，HTTP 不自动升级；官网网站声明要求引用注明来源并限制原版原式转载。因此记录只允许题录、必要短摘、来源标注和原文链接，禁止全文再分发。四流达到 `BOUNDED + ADMISSION_READY` 仅表示可提交后续 SourceAdmission Probe；Source 仍为 `CANDIDATE`、`desired_enabled=false`，无准入、运行、PAUSE 或覆盖信用。

`make t23-source-discovery-test` 离线验证版本化研究记录、精确边界、合规证据、能力隔离，以及与既有应急管理部事故调查报告流组成第二批 W1 时的四川/全国法域分离。详见 [T23 研究报告](docs/research/2026-07-20-sichuan-transport-bounded-stream-discovery.md)和[验收记录](docs/acceptance/phase-2/t23-sichuan-transport-source-stream-discovery.md)。

## T25 中国土木工程学会 SourceStream 发现

中国土木工程学会继续只计一个 Source（`RES-011`）。T25 保留“标准发布”和“詹天佑奖”两个精确集合，排除根站、搜索、单篇材料、陈旧学术成果栏目、会议宣传、会员活动和无工程新事实的组织动态；学会发布和奖励事实只使用 `PROJECT_FIRST_PARTY_RECORD`，不得自动提升为权威认定或独立验证。

学会旧站仍因 HTTP-only 不可准入；标准流改用国家标准委组织、中国标准化研究院建设的全国团体标准信息平台，以 CCES 唯一机构 ID 调用固定 HTTPS POST 元数据接口，并排除标准正文、PDF、账户和附件。该流形成 `BOUNDED + ADMISSION_READY` 研究输入，使 Issue #26 满足关闭条件；Source 仍为 `CANDIDATE/DISABLED`，无 SourceAdmission、运行、PAUSE 或覆盖信用。后续第二批 W2 明确与既有全国标准信息公共服务平台 `GOV-008-STANDARD-METADATA-CANDIDATE` 配对，但本票不重复该标准流研究或授予准入。专项离线验证命令为 `.\.venv\Scripts\python.exe -m pytest tests/infrastructure/test_t25_cces_source_stream_discovery.py -q`；完整证据与响应 SHA-256 见 [T25 研究报告](docs/research/2026-07-20-cces-source-stream-discovery.md)和[验收记录](docs/acceptance/phase-2/t25-cces-source-stream-discovery.md)。

## T27 中国公路学会与《隧道建设（中英文）》SourceStream 发现

Issue #28 继续复用两个既有机构 Source：`RES-001` 中国公路学会与 `RES-005`《隧道建设（中英文）》，没有把学会栏目或期刊当前期虚增为机构。学会流锁定动态加载的 `/cgtg/CGTGTZ/index.html` 成果推广通知集合，只接受包含公路工程对象、工程生命周期和公布／公示／入库结果语义的材料，明确排除会议宣传、论坛培训、会员活动、党建、征集和无实质工程新事实的综合新闻。

期刊官方站的 HTTPS 证书与越界重定向阻断继续保留，不再作为候选入口。替代流使用万方 `https://c.wanfangdata.com.cn/magazine/sdjs` 的 ISSN `2096-4498` 精确期刊集合及 `d.wanfangdata.com.cn/periodical/sdjs{九位期次序号}` 详情；ClaimBasis 只能是 `RESEARCH_CONCLUSION`，Reader 只保留题录、公开摘要和原链，排除内部 API、在线阅读、下载、PDF、图片和全文。该替代流达到研究态 `BOUNDED + ADMISSION_READY`，使 #28 满足关闭条件，但仍为 disabled、无 SourceAdmission、无运行授权。

`make t27-source-discovery-test` 离线验证精确 URL/主机/路径/MIME/频率边界、研究与运行能力隔离、未知合规失败关闭、私网和重定向逃逸拒绝、学会正负例、期刊版权投影边界及 `TUNNEL_GAS_MONITORING` 必须同时具备 `TUNNEL` 与 `HIGHWAY` 或 `RAILWAY`。详见 [T27 研究报告](docs/research/2026-07-20-chts-tunnel-construction-source-stream-discovery.md)和[验收记录](docs/acceptance/phase-2/t27-chts-tunnel-construction-source-stream-discovery.md)。

## T14 住房和城乡建设部流发现

住房和城乡建设部继续只计一个 Source（`GOV-005`）；其公开目录中的建筑市场监管 `F`、工程质量安全监管 `G` 和标准定额 `K` 被记录为三个带精确主题过滤、主机、路径、MIME 与候选频率的 `LIST_DETAIL` SourceStream。门户首页和无过滤综合目录不属于 SourceStream；正式 W2 候选使用 `GOV-005-G`，与既有国家矿山安全监察局通知公告流配对，矿井瓦斯仍只归 `MINING`，不取得交通隧道瓦斯监测覆盖。

2026-07-20 点时核验确认目录、详情和同主机 PDF 附件公开可达；站方未发布 `robots.txt`，公开目录、网站地图和官方导航未链接独立自动化访问条款，页脚转载声明要求注明来源。三条流据此形成 `StreamReadiness=BOUNDED`、`SourceResearchDisposition=ADMISSION_READY` 的后续准入核验输入，但仍保持 `CANDIDATE`、`enabled=false`。`ADMISSION_READY` 不表示 robots、条款、版权、频率或运行门禁通过，也不构成 SourceAdmission、Owner 意图、运行授权或真实采集证据；后续不足必须失败关闭。详见 [T14 研究报告](docs/research/2026-07-20-mohurd-bounded-stream-discovery.md)和[验收记录](docs/acceptance/phase-2/t14-mohurd-stream-discovery.md)。

## T18 民航局机场工程与《中国公路学报》流发现

中国民用航空局与《中国公路学报》继续分别只计一个 Source。T18 将民航局机场司 `fl=60` 机构分类集合锁定为机场工程 `LIST_DETAIL` 流，将期刊 `/CN/current` 锁定为正式当期目录流；根站、通用搜索、单篇材料、过时 RSS、PDF 和下载端点都不属于这两个 SourceStream。民航内容仍逐文档排除航班经营、时刻、旅游消费和无工程事实的新闻；期刊主张固定使用 `RESEARCH_CONCLUSION`，只保留题录、官网公开摘要边界和原文链接。

两条记录只是 `BOUNDED + ADMISSION_READY` 研究输入，仍为 `CANDIDATE`、`desired_enabled=false`、无 SourceAdmission、无实际运行、无 PAUSE、无覆盖信用。专项研究契约可运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/infrastructure/test_t18_source_stream_discovery.py -q
```

详见 [T18 研究报告](docs/research/2026-07-20-caac-cjht-bounded-stream-discovery.md)和[验收记录](docs/acceptance/phase-2/t18-caac-cjht-source-stream-discovery.md)。

## T08 证据优先搜索与共享 Feed／Card

`/api/v2/search` 只读取 `PublicationService` 已物化的 v2 阅读与搜索投影。标题、来源、当前 AcceptedClaims 和 `SourceExcerpt` 共同组成 A 级主搜索向量；结构化 `AISummary` 只进入 D 级低权重向量。连续中文短查询使用经过 `%`、`_` 和转义符处理的子串补充召回，证据命中固定获得 1,000,000 排名增量，AI 命中只获得 1,000，AI 不能凭辅助召回超过证据命中。FULL 搜索结果说明命中的证据字段以及是否使用“AI 总结低权重辅助召回”；R3 仍只返回原有服务端元数据白名单，不附加解释、摘录、claims、AI 或媒体。

`/`、`/selected`、`/all`、`/digital`、`/safety`、`/industry`、`/hot` 和搜索结果继续复用 `IntelligenceFeedPage`、`TimelineFeed` 与 `IntelligenceCard`。FULL Card 固定显示两行原文摘录；AI 成功时显示两行总结，其他状态显示服务端确定文案，且不会隐藏已过证据门禁的摘录。卡片只导航到 `/events/{event_id}` 的统一 Reader；页面不显示演示总结、演示评分、热点总分或“可信度”聚合分。`make t08-evidence-search-test` 使用协议 fixture 和当前单一 Alembic head 验证 durable 搜索、严格契约与共享 Card，不调用真实 DeepSeek，也不构成 Owner Gold、来源准入、运行窗口或 GO。详见 [T08 验收记录](docs/acceptance/phase-2/t08-evidence-search-feed-card.md)。

## T09 永久热点授予

热点是 Event 的服务端派生展示资格，不是第四种主类型。模型只能提交引用 claims 的候选理由；`PublicationService` 使用当前分类资格、AcceptedClaims/证据、SourceAdmission、来源机构与转载谱系、7 天窗口和服务端评分事实执行 `hotspot-v2.0.0`。五项上限固定为影响范围 25、工程实质性 25、新颖性 20、紧迫性 15、证据权威 15；只有两个去重后的独立合格来源，或单个权威一手来源且总分至少 70，才追加永久 Award。

重评与规则升级只追加候选、完整评估输入快照、评估结论和 Award，不覆盖或删除历史事实。普通 Feed 和 `/hot` 只显示触发路径、独立来源数及由评估时 AcceptedClaims 支持的理由，不显示总分；三种 `PrimaryType` 均保持原值。`make t09-hotspot-test` 在一次性 PostgreSQL 中回放 `0042 → 0043 → 0042 → 0043` 并验证真实角色权限和不可变约束。Fixture 中的准入、评分与协议模型候选不是真实来源准入、Owner Gold、DeepSeek 成功、运行窗口或 GO。详见 [T09 验收记录](docs/acceptance/phase-2/t09-permanent-hotspot-awards.md)。

`personal-migration-test` 使用隔离的真实 PostgreSQL 执行 `0028 → 0029 → 0030 → 损坏降级拒绝 → 0029 → 0028 → 0029 → 0030`，并覆盖已应用 0029 缺失角色快照的修复路径，再运行 30 个来源与 30 个内容固定样本评估。Fixture 和固定样本只用于确定性回归，不得冒充真实联网验收。

`personal-pilot-control-test` 另行执行 `0030 → 0031 → 0032 → 0033 → 0032 → 0030 → 0033`，并验证受控 AI 费用、详情证据兜底、事件去重和 Fixture 状态隔离。真实试点入口为 `powershell -File scripts/run_personal_pilot.ps1`；`-PreflightOnly` 只检查条件且绝不联网。试点严格绑定版本化来源集合；DeepSeek 只有在月度预算与受控运行费用账本均通过时才可启用，否则明确降级。

PERS-10 实现与归档统计见[本轮验收记录](docs/acceptance/personal/round-pers10-legacy-retirement.md)；真实交通运输部链路、受控原文变化和失效证据见[最终个人平台验收](docs/acceptance/personal/final-personal-platform.md)。
