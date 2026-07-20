# T09 永久热点授予验收记录

## 票据、依赖与边界

- 父 Spec：GitHub Issue #1；本票：GitHub Issue #10。
- GitHub 原生 `blockedBy` 仅包含 Issue #6；实现开始前已确认 #6 为 `CLOSED`，关闭时间为 2026-07-19。
- 已完整读取根 `AGENTS.md`、父 Spec、本票、Issue #6、`CONTEXT-MAP.md`、acquisition、intelligence-qualification、evidence-ai、publication-reader 四个 CONTEXT，以及 ADR-0001、ADR-0002、ADR-0003。
- 本票只实现永久 HotspotAward 候选、服务端评估、追加持久化和正式热点展示，不新增来源、运行窗口、主类型、发布入口或运营按钮。

## 纵向行为

1. `HotspotCandidateV2` 只允许模型给出 claim IDs 和逐条引用这些 claims 的理由；契约拒绝 award、score、trigger 和 rule version 等权威字段。
2. 唯一授予入口是 `PublicationService.evaluate_hotspot`。Repository 从 PostgreSQL 读取当前资格、当前文档 AcceptedClaims 及 evidence、最新 SourceAdmission、来源机构/转载谱系、发布时间和当前服务端 score set；任何必要事实缺失均失败关闭。
3. `hotspot-v2.0.0` 固定五项上限：影响范围 25、工程实质性 25、新颖性 20、紧迫性/运营后果 15、证据权威 15。只有 7 天内至少两个按机构和转载谱系去重的合格独立来源，或单个权威一手来源且总分至少 70，才能授予。
4. `DIGITAL_TRANSFORMATION`、`SAFETY_INTELLIGENCE`、`INDUSTRY_UPDATE` 均可获得同一正交展示资格；评估和投影不会修改 `PrimaryType`。
5. 候选、完整评估输入快照、评估结论和 Award 均追加不可变。重新评估或规则升级追加新记录；数据库拒绝 UPDATE/DELETE，已有 T09 事实时拒绝破坏性降级。
6. 普通 Feed/热点响应只投影触发路径、独立来源数和评估时由 AcceptedClaims 支持的理由；总分、组件分、规则内部输入和模型候选权威字段不进入普通页面。热点列表按 Event 读取最新 Award，不因重评重复展示。
7. 指标只使用 `outcome` 低基数标签；连续拒绝有 Prometheus 告警，event/source/URL/正文不进入标签或日志。

## TDD 与持久化证据

- RED：严格候选契约和领域测试最初因类型/评估器不存在而失败；0043 迁移测试因迁移不存在而失败；真实 PostgreSQL seam 依次暴露 publication writer 缺少准入事实只读权限和空 cursor SQL 类型不明确；可回放输入快照与告警测试也在实现前失败。
- GREEN：补齐严格契约、领域规则、服务端权威读取、追加式持久化、普通投影、页面理由与低基数观测；未删除断言、降低门槛或新增 skip。
- 隔离迁移回放：`0042 → 0043 → 0042 → 0043`。真实角色 seam 验证两次评估形成两条 evaluation 和两条 Award、热点列表仍为一个 Event、UPDATE Award 被 `T09_APPEND_ONLY_FACT` 拒绝。
- 一次性 fixture 中的 `ADMIT`、服务端评分和 `protocol-test-stub` 仅验证协议/权限/持久化；它们不是实际来源准入、真实模型成功或运行证据。

## 门禁结果

- `make t09-hotspot-test`：20 passed；迁移回放 `0042 → 0043 → 0042 → 0043` 通过。包含观测告警测试的扩展定向集为 21 passed；命令未输出本地凭据。
- `make lint`：PASS；Ruff、设计令牌、UI/Web ESLint 均通过。
- `make typecheck`：PASS；mypy strict 检查 146 个 source files，UI Vue、Nuxt 和生成契约 TypeScript 均通过。
- `make test`：PASS；Python 1214 passed / 27 个仓库既有条件性 skipped，UI 53 passed，Web 94 passed。本票未增加 skip。
- `make contract-test`：PASS；生成契约可复现，105 passed。
- `make security-check`：PASS；Python/Node 高危依赖检查无已知漏洞，Trivy HIGH/CRITICAL secret 与 misconfiguration 扫描通过。
- `make fixture-replay`：PASS；356 passed，既有 mock 评估报告通过。该 mock 仍不构成 DeepSeek 成功证据。
- `make quality-gate`：PASS；lint、typecheck、test、contract-test、security-check 聚合复跑通过。
- `make web-e2e`：63 passed；`make web-a11y`：18 passed。正式 Compose Web 镜像在测试前由当前工作区重建；热点页断言覆盖触发路径、独立来源数、AcceptedClaims 理由以及普通页面无总分/置信度。

## 非证据声明

本次未生成或使用 Owner Gold，未调用或宣称 DeepSeek 成功，未准入或启用真实来源，未开启真实运行窗口，也未生成 ENGINEERING_CLOSEOUT/PRODUCTION_CLOSEOUT GO。测试 fixture、迁移回放、页面 mock 和协议 stub 均不得作为这些事实的替代证据。PublicationService、R3/R4、robots、版权、公网安全、预算、限速和熔断边界未被绕过。
