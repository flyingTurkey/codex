# 土木工程情报质量与阅读体验 v2 验收记录

日期：2026-07-19

## 已实现范围

- v2 三主类型、工程对象/facets、claim basis、摘要状态和严格 FULL/R3 联合契约。
- raw-first 后按 MIME 解析，相关性自动通过阈值为 0.90；失败、低置信和需复核结果先进入 Owner case，不预建 Event。
- v2 空投影、append-only Owner decision、版本化 AI summary、永久热点授予、媒体权利和证据优先搜索迁移。
- `/api/v2` Feed、搜索、热点、Event、附录、媒体和复核接口；普通读取面对无投影/R4 返回 404。
- Nuxt 首页“今日精选”、搜索前置、行业视图、派生热点、reader-first 详情和底部折叠附录。
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

## 当前未闭环运行证据

- 2026-07-19 DeepSeek 诊断轮已将本地 compose 数据库升级到 `0036_ai_content_result_lifecycle`，并重建 API、通用 Worker、Parser、Publisher、Scheduler 和隔离 AI Worker。Secret 文件仅以“存在、可读、非空”布尔元数据核验；未读取或记录内容。
- runtime probe 已实际经过 Scheduler → 通用 Worker → AI Worker → callback 并形成新鲜 heartbeat；Owner AI 投影为 `configured=true`、`available=false`、`CONFIGURED_UNAVAILABLE/NO_RECENT_REAL_SCHEMA_SUCCESS`，不再把 Secret/activation 误报为真实可用。
- 当前权威事实为 `admitted_running_sources=0`、`trial_current_documents=0`，因此没有合法内容任务可触发真实 DeepSeek Schema 调用；本轮没有绕过来源准入、运行态、文档版本、raw CLEAN 或预算门禁，也没有伪造 real-schema success。engineering 仍有 `AI_RUNTIME_WINDOW_INCOMPLETE`。
- 迁移将 10 条“outbox 仍为 WAITING_AI、pipeline 已终态且无成功步骤”的历史不一致归零；历史 callback 已丢失的 7 条 `RESERVED` 预算记录缺少可信 provider usage，保持遗留未决，不事后伪造 Token 或费用。
- 隔离验收环境尚未形成同一快照的 200 条真实 v2 Feed 结构审计事实、20/20 一小时来源结论、补偿故障注入摘要和只读归档预检，分别保持 `FEED_SAMPLE_INSUFFICIENT`、`SOURCE_ASSESSMENT_INCOMPLETE`、`AI_COMPENSATION_INCOMPLETE`、`ARCHIVE_PREFLIGHT_INCOMPLETE`。
- engineering 不再要求 Owner gold；production 仍会在缺少 360 条人工标注时报告 `OWNER_GOLD_INCOMPLETE`。

当前结论：两个 profile 均为 `NO_GO`。代码与本地运行版本已经一致，runtime probe 健康，但真实 Schema 成功、一小时运行、20 源、Feed、补偿和归档证据尚未形成。本轮未执行生产切换、未启用生产来源、未回放或复活 v1 内容。

## 2026-07-19 DeepSeek 诊断增量验证

- lint/typecheck 等价命令通过：Ruff、设计令牌、UI/Web ESLint、mypy strict 137 个源文件、UI/Web/Contracts TypeScript 全部通过。
- 全量测试通过：Python `1063 passed, 26 skipped`，UI `53 passed`，Web `92 passed`；本轮未新增 skip。
- 契约门禁 `93 passed` 且生成结果可重现；fixture replay `354 passed`，Round09 对抗评估通过。
- 安全门禁通过：pip-audit 与 pnpm production audit 无已知漏洞，Trivy secret/misconfiguration 无 HIGH/CRITICAL 发现。
- 正式 Web 构建通过；E2E `58 passed`，a11y `18 passed`。
- Windows 环境没有 `make` 可执行文件，以上逐条执行 Makefile 中对应的底层命令，未省略门禁步骤。
