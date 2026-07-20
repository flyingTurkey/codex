# 土木工程情报质量与阅读体验 v2 验收记录

日期：2026-07-19

## 2026-07-19 tracer-bullet tickets 发布验收

- GitHub Spec #1 已拆分为 #2–#35 共 34 张纵向 tickets；34/34 保持 open，唯一标签均为 `ready-for-agent`，正文均引用父 #1，父 Spec 未被修改。
- GitHub 原生 `blockedBy` 与批准依赖图逐票一致；正文同时保存 blocker 编号。来源发现票不执行准入或 `PAUSE`，真实来源波次只有两源分别满足样本、连续 72 小时和质量门槛后才可关闭。
- UTF-8 回读覆盖全部 34 张正文：每票包含有效中文、必需章节和验收条件，无字面量问号替换或 Unicode replacement character；来源、UI 与总体依赖三个独立只读审查均为 `PASS`。
- 首页独立 ticket 明确 DOM 与视觉顺序为“搜索区域 → 今日精选一级标题 → 时间线”；AI/UI、来源发现和实际 rollout 的并行及串行边界均由原生依赖表达。
- 本次只发布 tickets 和登记验收，不运行 triage、不启用来源、不调用真实 DeepSeek 内容任务、不执行生产投影切换；engineering/production 继续沿用现有真实证据结论。

## 已实现范围

- v2 三主类型、工程对象/facets、claim basis、摘要状态和严格 FULL/R3 联合契约。
- raw-first 后按 MIME 解析；相关性自动通过阈值只能来自精确 corpus/rule/model/prompt 的 Owner Gold 校准事实，缺失时失败关闭。0.90 仅为已废止的待验证初值；失败、低置信和需复核结果先进入 Owner case，不预建 Event。
- v2 空投影、append-only Owner decision、版本化 AI summary、永久热点授予、媒体权利和证据优先搜索迁移。
- `/api/v2` Feed、搜索、热点、Event、附录、媒体和复核接口；普通读取面对无投影/R4 返回 404。
- Nuxt 首页“今日精选”、搜索前置、行业视图、派生热点、reader-first 详情第一版和底部折叠附录；Owner 后续确认的 B 双栏布局尚未进入正式页面。
- 生产环境禁用 mock provider；DeepSeek 仍通过受控 smoke/canary 验证，CI 使用协议等价测试实现。
- `0035_intelligence_v2_closeout` 追加 Owner 复核 Outbox、AI 观察/补偿和来源评估事实，包含 append-only、最小权限和有事实 downgrade 阻断。
- Owner 决定与重处理 Outbox 同事务提交；客户端不能上送投影或风险事实，Worker 只消费 Outbox ID，并由 `PublicationService` 基于当前版本和权威上下文刷新。
- Feed/搜索/热点使用版本化且 surface-bound 的 keyset cursor；无效 cursor 返回 `INVALID_CURSOR` Problem Details。
- 10 个旧阅读 E2E spec 已迁移到 v2，完整 Web E2E 和 a11y 门禁已通过，无新增 skip。
- 私有验收工具提供显式双 profile：engineering 覆盖 1 小时 AI/来源窗口、无人工标注的 200 条 Feed 服务端结构审计；production 完整保留 24 小时 AI、360 条 Owner gold、200 条人工 Feed 抽检和 72 小时/14 天来源门槛。仓库不保存私有正文。
- AI 队列每 30 秒执行无网络 runtime probe；验收类环境每 6 小时可在最新来源准入、当前 DocVersion、raw CLEAN、运行授权和预算全部成立后，使用固定公开文本执行 SHADOW CLASSIFY canary。其输出只写步骤/运行事实，不物化 claim/Event/投影；内容处理的瞬态真实调用错误以持久补偿事实记录并按 5/15/45 分钟最多重试 3 次。

## 切换边界

迁移只创建空 v2 代际和归档清单能力，不在开发任务中暂停生产调度、操作生产租约、启用真实来源或执行破坏性数据切换。正式切换必须先完成备份、对象清单、审计尾锚和 v1 归档哈希验证。

## 验收 Profile

- `ENGINEERING_CLOSEOUT`：真实 DeepSeek 连续 1 小时、至少一次 Schema 成功；20 源可并行观察且每源至少 1 小时；qualification 不要求人工标注，Feed 对真实 v2 快照的至少 200 条投影只做服务端结构安全审计。
- `PRODUCTION_CLOSEOUT`：继续要求原 24 小时/五次真实成功、360 条 Owner gold、200 条人工 Feed precision、每源 72 小时及首批 14 天后启动第二批。
- 两个 profile 都要求 queue/budget/heartbeat/外部余额健康、20/20 来源结论、合规硬门禁、补偿无重复副作用和只读归档预检。engineering `GO` 不表示生产就绪。

## 验证命令

最终结果在本文件末次更新时补录；任何未通过门禁均意味着本轮不能宣称完成。

## 2026-07-19 验证结果

- `make lint`、`make typecheck`：通过；Ruff 无问题，mypy strict 覆盖 137 个源文件，UI/Web/Contracts TypeScript 通过。
- `make test`：Python `1058 passed, 26 skipped`，UI `53 passed`，Web `92 passed`。skip 为仓库既有的可选隔离集成用例，本轮未新增 skip。
- `make contract-test`：`93 passed`，生成契约可重现。
- `make fixture-replay`：`354 passed`；Round09 对抗回放通过，未支持扩写率为 0。
- `make quality-gate` 及其包含的安全检查：通过；pip-audit 无可审计第三方漏洞，pnpm production audit 为 0，Trivy 无 HIGH/CRITICAL secret/misconfiguration。
- `make web-e2e`：`58 passed`；`make web-a11y`：`18 passed`。FULL/R3、R4/无投影 404、媒体权限、折叠附录、桌面/移动键盘和 axe 均通过。
- closeout 双 profile 专项测试 `14 passed`；必须显式执行 `make intelligence-v2-closeout ACCEPTANCE_PROFILE=engineering|production`，缺省 profile 失败关闭。

## 0036 诊断结束时的未闭环快照（由后续 0037 campaign 更新）

- 2026-07-19 DeepSeek 诊断轮已将本地 compose 数据库升级到 `0036_ai_content_result_lifecycle`，并重建 API、通用 Worker、Parser、Publisher、Scheduler 和隔离 AI Worker。Secret 文件仅以“存在、可读、非空”布尔元数据核验；未读取或记录内容。
- runtime probe 已实际经过 Scheduler → 通用 Worker → AI Worker → callback 并形成新鲜 heartbeat；Owner AI 投影为 `configured=true`、`available=false`、`CONFIGURED_UNAVAILABLE/NO_RECENT_REAL_SCHEMA_SUCCESS`，不再把 Secret/activation 误报为真实可用。
- 当时权威事实为 `admitted_running_sources=0`、`trial_current_documents=0`，因此没有合法内容任务可触发真实 DeepSeek Schema 调用；本轮没有绕过来源准入、运行态、文档版本、raw CLEAN 或预算门禁，也没有伪造 real-schema success。engineering 当时仍有 `AI_RUNTIME_WINDOW_INCOMPLETE`。
- 迁移将 10 条“outbox 仍为 WAITING_AI、pipeline 已终态且无成功步骤”的历史不一致归零；历史 callback 已丢失的 7 条 `RESERVED` 预算记录缺少可信 provider usage，保持遗留未决，不事后伪造 Token 或费用。
- 0036 诊断结束时，隔离验收环境尚未形成同一快照的 200 条真实 v2 Feed 结构审计事实、20/20 一小时来源结论、补偿故障注入摘要和只读归档预检，分别保持 `FEED_SAMPLE_INSUFFICIENT`、`SOURCE_ASSESSMENT_INCOMPLETE`、`AI_COMPENSATION_INCOMPLETE`、`ARCHIVE_PREFLIGHT_INCOMPLETE`；后续 0037 campaign 已更新其中的来源结论与归档预检事实。
- engineering 不再要求 Owner gold；production 仍会在缺少 360 条人工标注时报告 `OWNER_GOLD_INCOMPLETE`。

当时结论：两个 profile 均为 `NO_GO`。代码与本地运行版本已经一致，runtime probe 健康，但真实 Schema 成功、一小时运行、20 源、Feed、补偿和归档证据尚未形成。本轮未执行生产切换、未启用生产来源、未回放或复活 v1 内容。当前最新证据以本文后续 0037 campaign 最终结果为准。

## 2026-07-19 DeepSeek 诊断增量验证

- lint/typecheck 等价命令通过：Ruff、设计令牌、UI/Web ESLint、mypy strict 137 个源文件、UI/Web/Contracts TypeScript 全部通过。
- 全量测试通过：Python `1063 passed, 26 skipped`，UI `53 passed`，Web `92 passed`；本轮未新增 skip。
- 契约门禁 `93 passed` 且生成结果可重现；fixture replay `354 passed`，Round09 对抗评估通过。
- 安全门禁通过：pip-audit 与 pnpm production audit 无已知漏洞，Trivy secret/misconfiguration 无 HIGH/CRITICAL 发现。
- 正式 Web 构建通过；E2E `58 passed`，a11y `18 passed`。
- Windows 环境没有 `make` 可执行文件，以上逐条执行 Makefile 中对应的底层命令，未省略门禁步骤。

## 2026-07-19 ENGINEERING_CLOSEOUT campaign 增量

- 新增迁移 `0037_engineering_closeout_campaign`，工程活动头与事件均为 append-only，包含最小 RBAC、有事实 downgrade 阻断和只读归档/审计验证函数。历史迁移的单一 head 回归断言已同步到 0037，各轮既有迁移链保持不变。
- 新增 `make intelligence-v2-engineering-campaign ACTION=prepare|start|status|finalize`。活动可按 UUIDv7 幂等续跑；`start` 显式重申 `acceptance` 环境，`finalize` 恢复原环境后才执行门禁。普通 closeout 命令只读取当前活动导出的同一组证据，不混用不同 campaign。
- 固定清单包含 20 个唯一官方 HTTPS origin；本地原有 15 源之外的 5 源仅登记为 `CANDIDATE_ONLY`。来源结论按固定 cutoff、最近 90 天、去重后最多 30 条服务端事实计算，任何 policy/robots/条款/版权/公网安全事实不完整均失败关闭；活动不会更改 `desired_enabled` 或生产 `ACTIVE`。
- 当前环境没有耐久 locked-negative 评估集；导出因此显式保存 `hard_negative_evaluated=false` 并强制来源 `PAUSE`，不会把数值上“观测到 0 个泄漏”误报为已完成 hard-negative 零泄漏验证。
- AI 瞬态/永久故障注入仅在 acceptance 且真实调用前置门禁成立时执行。瞬态恢复仍使用 5/15/45 分钟持久补偿；永久 Schema 错误不得重试；两类均不进入发布链。没有合格来源和当前 CLEAN 文档时返回稳定拒绝原因，不伪造 DeepSeek 成功。
- 证据导出包括 runtime、20 源、真实 v2 Feed、补偿、历史 `RESERVED` 对账、备份/对象清单/审计尾锚/v1 归档预检及 context；正文和 Secret 不写入仓库，归档预检保持 `mutation_performed=false`。
- 专项测试当前为 `40 passed`，后续新增的恢复/迁移镜像/当前证据发布回归为 `10 passed`；`make lint`、`make typecheck`、`make test`、`make contract-test`、`make fixture-replay` 已通过。其中全量测试为 Python `1078 passed, 27 skipped`、UI `53 passed`、Web `92 passed`，本轮未新增 skip。`make security-check` 首次因 Docker bind mount 瞬时不可见失败，未修改规则，原命令重跑后通过且无已知依赖漏洞或 HIGH/CRITICAL secret/misconfiguration。
- 真实活动 `019f79e1-5d04-73e5-880b-ab9ce5fb37f7` 使用本地生产等价隔离栈。一次在活动中误调用 `runtime-ready` 导致服务重建，真实 runtime observation 最大间隔达到 138.68 秒，超过 90 秒门禁；该缺口保留在证据中，不修改时间戳。

### Campaign 最终结果

- 活动实际跨越 1 小时，导出的 runtime observation 有 115 条，首末 observation 跨度 3628 秒；queue/budget 未产生失败原因，但无真实 DeepSeek Schema 成功，external balance 为 `UNKNOWN`，且存在 138.68 秒间隔。因此 AI 项为 `NO_GO`，原因是 `AI_RUNTIME_OBSERVATION_GAP`、`AI_EXTERNAL_BALANCE_UNKNOWN`、`AI_REAL_SCHEMA_SUCCESS_INSUFFICIENT` 和 `AI_REAL_SCHEMA_SUCCESS_STALE`。
- 20/20 来源均形成 append-only `PAUSE` 结论；20 源在固定 cutoff 的最近 90 天合格样本均为 0，`hard_negative_evaluated=false`。来源完整性检查通过，但这些结论不授权任何生产来源启用。
- 真实 v2 FULL/R3 投影为 0，保持 `FEED_SAMPLE_INSUFFICIENT`；没有使用 v1、fixture 或生成内容补齐。由于没有合格真实调用前置条件，瞬态/永久注入均失败关闭，保持 `AI_COMPENSATION_INCOMPLETE`。
- 只读归档预检通过，`mutation_performed=false`；7 条历史 `RESERVED` 仅形成 `UNSETTLED_NO_TRUSTWORTHY_PROVIDER_USAGE` 对账，不补造 token/cost，也不阻断新活动。
- finalize 首次在外层工具 124 秒超时后已留下 `FINALIZED/RESTORED` 事实和恢复后的 `test` 环境；按 campaign ID 续跑从缺失 readiness 处完成九项门禁，`engineering.json` 中 lint、typecheck、test、contract、security、fixture replay、quality gate、Web E2E 和 a11y 均为 true。
- 最终 engineering readiness 为 `NO_GO`，manifest 内部 SHA-256 为 `4ae61768e8ef9131b869e300125397773e8a617b28dda83cbe483f96d526e4a0`，文件 SHA-256 为 `a10b0b84b834d1f403506492a052b1a0b5acc8314845cc9b58982ac9e2819f09`。同一证据在 production profile 下也为 `NO_GO`，并额外保留 24 小时、Owner gold、72 小时/14 天等未满足项。

当前结论：工程实现和所有仓库门禁通过，但真实运行证据仍不满足工程 profile，故 `decision=NO_GO`。本轮未执行生产切换、未启用生产来源、未复活 v1 内容。

## 2026-07-19 Owner Reader UI Prototype 决策回传

- Owner 已确认选择 B：宽屏使用正文主栏与受约束的 sticky 上下文侧栏，窄屏恢复为单列语义顺序；该选择来自独立 throwaway prototype，不把 prototype 组件或 fixture 提升为生产依赖。
- 标题区先展示类型、标题、来源和原文发布日期；存在撤回或更正时必须首屏提醒。正文主栏按“原文摘录 → AI 总结及状态 → 图片 → 附件与原文动作”组织，AI 的视觉权威不得高于原文。
- 上下文侧栏承载来源、官方一手状态、人工复核状态、两个时间、PrimaryType/facets、ClaimBasis、原文链接与许可附件动作；移动端按“标题/更正提醒 → 来源上下文 → 原文摘录 → AI 总结 → 媒体与动作 → 折叠附录”排序，关键信息不得只存在于 drawer 或 hover。
- 自动处理、证据事实、关系、更正记录和 Owner 纠正继续位于页面底部并默认折叠；FULL/R3/R4、accepted claims、AI 状态和服务端投影边界保持不变。正式实现继续复用 Nuxt/Vue、现有组件和权威设计令牌。

## 2026-07-19 共同理解与规格就绪确认

- Owner 确认十一类 `EngineeringObject` 是产品领域边界。来源研究报告中的公路、铁路、桥梁、隧道、房屋建筑和矿山六类只是本轮 `SourceCoverageMatrix`；市政、水利、港航、机场和能源工程未纳入该子矩阵，不等于被排除，也不要求首批来源立即覆盖。
- v2 不新增数字成熟度枚举或 `DEPLOYED+` 阅读门禁。研究、概念和产品内容在直接相关时继续使用统一 Feed/Card/详情；部署与效果只由 accepted claims、证据和 `ClaimBasis` 表达。
- 工程 campaign 的 20 个机构是验收与战略来源组合，不是 20 条已准入 SourceStream。每条实际流仍须先经过研究 disposition、路径级 `SourceAdmission` 和 rollout 门禁；当前 20/20 `PAUSE` 不授权启用。
- Owner Reader 的 B 方案是已确认的正式重建输入，不是已经生产实现的页面。当前正式 `/events/{event_id}` 仍为单列第一版；契约和页面差距应进入后续 Spec，而不是通过复制 prototype 解决。
- 产品规格已经没有未决决策，`to-spec=READY`。当前 `ENGINEERING_CLOSEOUT=NO_GO` 与 `PRODUCTION_CLOSEOUT=NO_GO` 是运行及上线证据状态，只阻止 GO 和切换，不阻止规格工作。

## 2026-07-19 正式 Spec 发布

- Owner 确认三个顶层测试 seams：版本化 Gold Corpus 领域 seam、真实 PostgreSQL/Redis/对象存储下的 durable 后端纵向 seam，以及正式 Nuxt 浏览器故事 seam；原先独立描述的 v2 契约/API/ACL/空投影/只读归档断言合并到 durable seam。
- 正式 Spec 已发布为 GitHub Issue [#1](https://github.com/flyingTurkey/codex/issues/1)，状态为 open，且唯一标签为 `ready-for-agent`。发布正文包含完整模板、57 条用户故事、Implementation Decisions、Testing Decisions 和 Out of Scope，未包含本地文件路径或代码片段。
- `ready-for-agent` 仅表示规格完整；当前 engineering/production closeout 继续为 `NO_GO`，本轮未修改业务代码、启用来源、调用真实内容任务或执行生产切换。
