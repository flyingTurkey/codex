# 土木工程情报 v2：下一轮开发与维护入口

更新时间：2026-07-23
状态：`AUTONOMOUS_POLICY_MECHANISM_COMPLETE / PRODUCTION_CLOSEOUT_NOT_CLAIMED`

本文是当前状态的维护入口，不替代历史验收记录。历史文档中的数字只描述当时的验收事实；下一轮执行前必须按下列权威顺序重新核验。

## 权威阅读顺序

1. 根目录 `AGENTS.md`：强制产品、证据、PublicationService、R3/R4、UI、安全和质量规则。
2. `CONTEXT-MAP.md` 及 Acquisition、Intelligence Qualification、Evidence & AI、Publication & Reader Projection 四个 Context：领域术语和边界。
3. GitHub 父 Spec [#40](https://github.com/flyingTurkey/codex/issues/40) 与当前 ticket：自主内容机制、依赖和验收。
4. ADR-0002 至 ADR-0006：投影、engineering/production 隔离、自主策略、生产切换与策略生命周期。
5. 当前验收记录与 handoff：只证明其时间点已经形成的事实，不自动代表当前运行态。
6. README、研究报告和历史 Codex kit：用于操作导航或设计溯源，不得覆盖以上规则。

遇到冲突时，停止执行会扩大生产状态的动作，并把冲突交给 Owner；不得靠降低阈值、构造 fixture 或追加绕过标记获得 `GO`。

## 当前自主机制基线

Issue #41、#43、#44、#45 与 #46 形成一条唯一真实最高层路径：

`SourceStream -> raw/document -> policy-bound pipeline run -> automatic decision -> evidence/PublicationService -> Feed`

- 0054 在 run 创建事务中固定 `policy_bundle_id`；回调、技术重试、语义 recheck 和恢复复制或读取该固定值。
- 离线评估固定 `authorizes_production=false`；SHADOW 决策与聚合窗口固定 `affects_production=false`，并在任何生产物化前终止。
- 通过完整离线门禁的 Challenger 由固定 canary 自动产生 SHADOW 事实。至少 20 个终态的聚合窗口通过稳定性、技术、安全、suppression、类别漂移和零违规门禁后，才可追加 `PROMOTE`。
- 激活和回滚只追加 `qualification_policy_activation_v2`；`active_qualification_policy_v2` 是派生指针，不修改 bundle、decision、evaluation、shadow 或历史 activation。
- 每分钟健康任务监测 Feed yield、技术异常、安全、suppression、Schema/投影失败、硬负例、成本预算和类别漂移；达到失败条件时追加一次幂等 `ROLLBACK` 到前任 Champion。
- Prometheus 只暴露低基数晋级、shadow-window 和回滚结果；自动回滚与晋级拒绝均有告警。

私有 replay 的持久化入口：

```powershell
.\.venv\Scripts\python.exe scripts\replay_autonomous_policy_private_benchmark.py `
  --pack-root <private-pack-root> `
  --code-version <candidate-code-version> `
  --source-stream-policy-version <exact-stream-policy-version> `
  --attempt-manifest-sha256 <sha256> `
  --response-artifact-sha256 <sha256> `
  --persist-evaluation
```

该命令只追加聚合事实，不能输出或提交逐案私有内容。记录成功也只表示 Challenger 获得 SHADOW 资格，不表示晋级或 production closeout。

## 历史工程基线

提交 `8e5bb02` 是目前已验证的 v2 工程基线。核心产品票 #2–#13 和全部 SourceStream 发现/替代研究票已经关闭；这些工作已经交付以下稳定边界：

- 三轴领域模型、唯一 `PrimaryType`、锁定负例和分类失败关闭；
- accepted claims、连续原文摘录、结构化 AI 总结与七种摘要状态；
- `PublicationService` 唯一发布边界，以及 FULL/R3/404、R4 隔离和空 v2 投影；
- 统一 v2 Feed、搜索、热点、Event Reader、ReaderAppendix、媒体和 Owner 复核契约；
- Nuxt Owner Reader 的 B 布局方向，以及首页搜索位于“今日精选”和时间线之前；
- DeepSeek durable 终态、补偿、Schema 校验和结果投影基础；
- 二十个目标机构的 SourceStream 发现证据。发现结论不是 SourceAdmission，也没有授予运行权。

基线验收见 `docs/acceptance/phase-2/intelligence-v2-engineering-baseline-2026-07-20.md`。该基线没有宣称真实来源、真实 DeepSeek、Owner Gold、Feed precision 或 production closeout `GO`。

## 历史 Owner Gold `.4` NO-GO（不得改写）

#36 要求冻结 40 条语料、40 条真实 `HUMAN_OWNER` 标注和标注前独立封存的 40 条预测。冻结协议仍要求：

- Owner 分布为正例 20、边界例 10、锁定负例 10；
- 正例三主类型为 7/7/6，并覆盖十一类工程对象、隧道瓦斯专项和施工机械设备域；
- precision 与 recall 均至少 90%；
- 锁定负例泄漏为 0；
- 只有服务端校验通过的精确版本 `GO` 才能授权自动通过。

2026-07-20 的早期只读核验曾记录正例 20、边界例 0、负例 20，precision 55.55%、recall 75% 和 9 条锁定负例泄漏。#41 最终验收中的同一历史 `.4` replay 聚合记录为 precision 70%、recall 70%、5 条锁定负例泄漏。两次点时记录都明确为原阈值下的 `NO_GO`；不得删除、挑选或改写任一历史记录来制造通过。ADR-0005/0006 后，该历史失败也不再是自主机制的全局阻断。

不要公开、提交或复制私有逐案正文、标签和预测。仓库文档只记录以上聚合结论；私有验收材料继续保存在仓库外。

## 2026-07-20 本地环境 override 风险（历史时点）

本节只描述 2026-07-20 当时的工作树和本地数据库，不描述当前 integration 或 Issue #46 独立工作树。当时的只读核验显示：

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

## 2026-07-20 旧生产票顺序（已被 Spec #40 后续决策覆盖）

真实 blocking chain 为：

`#36 → #14 → #16 → #18 → #20 → #22 → #23 → #25 → #27 → #29 → #31 → #33 → #34 → #35`

- #14–#22：首批五个双来源波次；每票只接入两个来源。
- #23：首十来源共同 24 小时组合收口。
- #25–#33：第二批五个双来源波次。
- #34：二十来源组合收口与 30–50 源扩展保护。
- #35：DeepSeek、Feed Owner 抽检和三个最高层 seam 的最终诚实 readiness。

这些生产票有原生依赖，不能并行越过 blocker。与生产链无状态冲突的文档归档、历史入口标记和只读审计可以并行，但不得修改同一工作树中的 #36 代码。

## 当前后续动作

1. 只从当前父 Spec #40 integration 创建新工作树；不得从旧 Owner Gold 或单票分支接续。
2. 为候选策略使用新的不可变 bundle 身份和精确 SourceStream policy version，运行私有 replay 并追加真实聚合结果；失败结果同样保留。
3. 等待真实 SHADOW canary 累积完整聚合窗口。单文档 shadow、0 precision/recall 占位或人工改表都不能晋级。
4. 观察激活账本、health windows、低基数指标和告警。自动回滚后先诊断回归，不修改旧 activation、decision、evaluation 或 shadow。
5. 分别报告 `MECHANISM_ENGINEERING`、`CHALLENGER_PROMOTION` 和 `PRODUCTION_CLOSEOUT`；没有真实来源、真实 DeepSeek、真实 Feed 抽检和运行窗口证据时，最后一项保持未完成。

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
