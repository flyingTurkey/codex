# 土木工程情报 v2：下一轮开发与维护入口

更新时间：2026-07-20  
状态：`BLOCKED_BY_OWNER_GOLD_CALIBRATION`

本文是当前状态的维护入口，不替代历史验收记录。历史文档中的数字只描述当时的验收事实；下一轮执行前必须按下列权威顺序重新核验。

## 权威阅读顺序

1. 根目录 `AGENTS.md`：强制产品、证据、PublicationService、R3/R4、UI、安全和质量规则。
2. `CONTEXT-MAP.md` 及 Acquisition、Intelligence Qualification、Evidence & AI、Publication & Reader Projection 四个 Context：领域术语和边界。
3. GitHub Spec [#1](https://github.com/flyingTurkey/codex/issues/1) 与当前 blocker [#36](https://github.com/flyingTurkey/codex/issues/36)：现行产品门槛和依赖。
4. ADR-0002、ADR-0003：投影切换以及 engineering/production 失败关闭语义。
5. 当前验收记录与 handoff：只证明其时间点已经形成的事实，不自动代表当前运行态。
6. README、研究报告和历史 Codex kit：用于操作导航或设计溯源，不得覆盖以上规则。

遇到冲突时，停止执行会扩大生产状态的动作，并把冲突交给 Owner；不得靠降低阈值、构造 fixture 或追加绕过标记获得 `GO`。

## 已稳定完成的产品基线

提交 `8e5bb02` 是目前已验证的 v2 工程基线。核心产品票 #2–#13 和全部 SourceStream 发现/替代研究票已经关闭；这些工作已经交付以下稳定边界：

- 三轴领域模型、唯一 `PrimaryType`、锁定负例和分类失败关闭；
- accepted claims、连续原文摘录、结构化 AI 总结与七种摘要状态；
- `PublicationService` 唯一发布边界，以及 FULL/R3/404、R4 隔离和空 v2 投影；
- 统一 v2 Feed、搜索、热点、Event Reader、ReaderAppendix、媒体和 Owner 复核契约；
- Nuxt Owner Reader 的 B 布局方向，以及首页搜索位于“今日精选”和时间线之前；
- DeepSeek durable 终态、补偿、Schema 校验和结果投影基础；
- 二十个目标机构的 SourceStream 发现证据。发现结论不是 SourceAdmission，也没有授予运行权。

基线验收见 `docs/acceptance/phase-2/intelligence-v2-engineering-baseline-2026-07-20.md`。该基线没有宣称真实来源、真实 DeepSeek、Owner Gold、Feed precision 或 production closeout `GO`。

## 当前阻断：Issue #36

#36 要求冻结 40 条语料、40 条真实 `HUMAN_OWNER` 标注和标注前独立封存的 40 条预测。冻结协议仍要求：

- Owner 分布为正例 20、边界例 10、锁定负例 10；
- 正例三主类型为 7/7/6，并覆盖十一类工程对象、隧道瓦斯专项和施工机械设备域；
- precision 与 recall 均至少 90%；
- 锁定负例泄漏为 0；
- 只有服务端校验通过的精确版本 `GO` 才能授权自动通过。

2026-07-20 的只读核验显示，`.4` 已经完成 40 条 Owner 标注和 40 条独立预测，但实际聚合结果为正例 20、边界例 0、负例 20；标准校准的 precision 为 55.55%、recall 为 75%，锁定负例泄漏为 9。因此标准结论必须是 `NO_GO`，#36 仍为 `OPEN / ready-for-human`，#14 仍被阻塞。

不要公开、提交或复制私有逐案正文、标签和预测。仓库文档只记录以上聚合结论；私有验收材料继续保存在仓库外。

## 本地环境的未批准 override 风险

当前工作树并不等同于已验证基线：它包含大量 #36 未提交改动，以及未跟踪的 `0047_owner_gold_override_go`、override CLI 和相关测试。只读数据库核验还显示：

- 本地 PostgreSQL 的 Alembic 版本已是 `0047_owner_gold_override_go`；
- 数据库已有一条 `authorizes_auto_pass=true` 的 Owner override `GO`；
- 同一事实仍明确记录质量门槛未满足、precision 55.55%、recall 75% 和 9 条锁定负例泄漏。

同一轮只读核验中，55 个非 fixture 来源都表达了 `desired_enabled=true`，但实际 RUNNING/ACTIVE 为 0，`SourceAdmission=ADMIT` 也为 0。当前没有证据表明真实来源正在运行，因此即时外部采集风险受 SourceAdmission 失败关闭限制；这不使 override 合法，也不授权启动调度或来源波次。

该旁路与根 `AGENTS.md`、Spec #1 和 #36 的失败关闭规则冲突，也没有可见的 Owner 产品决策授权。它不得被合并、用于来源准入、PublicationService 或 closeout，也不得被描述为 #36 已完成。下一轮应把当前本地数据库视为受污染的验收环境，不使用其中的 override `GO` 作为任何生产证据。

在 Owner 明确决定前，不要删除、降级或重写这个追加式事实；也不要在其上继续 #14。先备份并确认可恢复性，再决定是废弃该本地环境、以合法的新事实撤销其消费资格，还是通过新的产品决策、Spec 和 ticket 正式改变门槛。推荐维持现有门槛，改进语料/分类器后重新执行独立校准，而不是授权低质量自动通过。

## 现行生产收口门槛

下列数字以 Spec #1 为准。部分仓库代码和历史文档仍保留旧的 24 小时/5 次、72 小时、14 天首批窗口或 200 条人工 Feed 抽检；它们是待实现漂移，不能反向覆盖 Spec。

| 维度 | 现行要求 | 不应混同 |
| --- | --- | --- |
| Owner Gold | 40 条，20/10/10，正例主类型 7/7/6，P/R 均 ≥90%，锁定负例零泄漏 | 20 条 pilot、360 条结构回放 |
| 单个真实来源波次 | 连续 1.5 小时，并完成真实端到端执行、样本和全部硬门禁 | 纯计时、SourceStream discovery |
| 首十来源组合 | 同时 ADMIT/RUNNING 至少 1 天，规则和监控连续 | 每源窗口、长期退出窗口 |
| DeepSeek production closeout | 连续 2 小时、至少 2 次不同真实请求/文档版本的合法 Schema 成功，至少一次投影成功 | AI `available` 独立的 24 小时新鲜度 |
| 最终 Feed Owner 抽检 | 同一冻结生产快照分层抽取 50 条，precision ≥98%，最多 1 条误收；硬负例/R4/未接受 claim/无证据摘要零泄漏 | 保留的 200 条工程结构审计 |
| 来源退出 | 软指标连续两个完整 14 天窗口失败才退役 | 初始 1.5 小时准入窗口 |

可变数字应最终落到版本化规则和对应 TDD；ADR-0003 只应稳定表达 engineering 与 production 语义隔离以及失败关闭，不应继续充当易漂移的数字配置源。

## 剩余执行顺序

真实 blocking chain 为：

`#36 → #14 → #16 → #18 → #20 → #22 → #23 → #25 → #27 → #29 → #31 → #33 → #34 → #35`

- #14–#22：首批五个双来源波次；每票只接入两个来源。
- #23：首十来源共同 24 小时组合收口。
- #25–#33：第二批五个双来源波次。
- #34：二十来源组合收口与 30–50 源扩展保护。
- #35：DeepSeek、Feed Owner 抽检和三个最高层 seam 的最终诚实 readiness。

这些生产票有原生依赖，不能并行越过 blocker。与生产链无状态冲突的文档归档、历史入口标记和只读审计可以并行，但不得修改同一工作树中的 #36 代码。

## 下一轮建议动作

1. 先保持 #14 和真实来源运行暂停，检查调度、Publisher、SourceAdmission 和自动通过消费者没有使用本地 override 事实。
2. 由 Owner 决定 override 的处置。推荐结论是拒绝旁路、保留标准 `NO_GO`，并把 `.4` 作为失败样本用于修正规则、候选构成或分类器后生成新的冻结 corpus/version；不得改标签追逐 `GO`。
3. 将 #36 工作树拆成可审计范围：合法的 0046 prediction seal/40 条流程改动与未批准的 0047 override 分开处理；不要在当前 dirty worktree 上盲目提交全部文件。
4. 在 #14 前用独立 TDD 切片同步 production closeout 的新数字门槛。保留 AI 24 小时新鲜度、200 条工程结构审计和两个 14 天退出窗口。
5. 只有新的标准校准确实满足 #36 并通过服务端耐久消费验证后，关闭 #36、恢复 `ready-for-agent` 流程并开始 #14。

## 文档债务与误导入口

本轮已把 `docs/codex-kit/AGENTS.md` 收敛成 Legacy 作用域护栏，并为 codex-kit README、根 `README-1.md` 和根 `VALIDATION.md` 增加历史状态与现行入口指针；历史内容本身没有删除。

以下剩余内容不阻止当前总结，但会误导全新 Codex，建议在独立文档收口票处理：

- `docs/architecture/personal-research-mode.md` 仍描述 v1 personal-signal 补投影，和 v2 空投影/R3/R4 冲突。
- `docs/ENTERPRISE-PROCESSES-RETIRED.md` 对 `docs/acceptance/phase-2/*` 的失效范围过宽，误伤当前 v2 验收。
- `docs/operations/runbooks.md` 与 CI/保护示例仍以企业角色和双人审批为主；#14 前需要单 Owner 的 v2 真实来源准入 runbook。
- 部分 user guide、handoff 和研究文本仍含旧门槛；应增加“历史时点/已被 Spec #1 覆盖”说明，而不是改写历史事实。

`CONTEXT-MAP.md`、四个当前 Context、ADR-0002 和 `docs/agents/*` 本轮核验没有结构性问题，不需要为了整理而重复创建文档。

## 每轮维护检查

开始前：

```powershell
git status --short
git log -1 --oneline
gh issue view <issue-number> --repo flyingTurkey/codex
```

完成前按影响范围运行根 `AGENTS.md` 指定门禁。所有轮次至少运行 lint、typecheck、test、contract-test 和 security-check；涉及采集/内容处理时增加 fixture-replay、quality-gate；涉及前端时增加 web-e2e、web-a11y。文档改动还应运行 `git diff --check` 并检查相对链接。

任何 `GO` 报告都必须同时说明它属于规格、engineering 还是 production，并列出真实证据缺口；“已配置”、fixture、mock、研究结论或已运行一段时间均不是生产可用证明。
