# T11 ReaderAppendix 治理附录验收记录

- GitHub Issue：`flyingTurkey/codex#12`
- 父 Spec：`#1`
- 验收日期：2026-07-20
- 结论：实现完成；以本记录最终门禁表为准

## 前置确认

开始实现前已完整读取根 `AGENTS.md`、父 Spec #1、Issue #12、`CONTEXT-MAP.md`、四个领域 CONTEXT 与 ADR-0001～0003。GitHub 原生依赖链确认：直接 blocker #11 已 `CLOSED`；#11 的原生 blockers #6、#7 也均已 `CLOSED`。本票只实现 ReaderAppendix 纵向行为，不扩展来源准入、模型运行、媒体登记或发布写入。

## 第一性原则与测试接缝

目标是让 Owner 在不干扰主阅读叙事的前提下查看治理来源；不可再分事实是：普通 Reader 只能读取已经通过服务端发布与风险门禁的权威投影，模型输出不是证据，R3/R4 不能靠浏览器隐藏，纠正写入不属于 v2 阅读票。因此实现固定为两个接缝：

1. PostgreSQL `reader_appendix_governance_v2` security-barrier 视图组合当前 FULL、R1/R2 投影、AcceptedClaims 证据、个人自动结果、人工/自动关系、结构化更正和安全 ReviewCase；projection reader 只获视图 `SELECT`，不获底表或写权限。
2. Nuxt `ReaderAppendix` 在 FULL 详情底部懒加载只读契约；复核只提供安全深链或列表回退，所有写操作继续使用既有 v1 边界。

## TDD 证据

RED 阶段先出现并保留了以下预期失败：契约缺少关系/更正/复核/重内容字段；服务仍只回显浅层 appendix；迁移治理视图不存在；组件缺少七态、懒加载、重试和分组；可观测性指标不存在。真实 PostgreSQL 首轮还拒绝了无权威定位的 HTML evidence fixture；测试随后改用真实 `document_page → document_text_block → PDF_TEXT claim_evidence` 链，没有关闭触发器或降低证据约束。

GREEN 阶段完成：

- 七态：`UNLOADED / LOADING / EMPTY / SUCCESS / ERROR / RETRYING / HEAVY`；首次展开单次请求，折叠复用，错误局部化，收起恢复触发按钮焦点。
- 分组：AcceptedClaims 与 evidence、自动处理结果、人工审核关系、自动关系、事故阶段、倒序结构化更正；自动结果明确不作为证据事实。
- ReviewCase：只有服务端返回安全 case 才生成 `/review?case_id=...`；否则固定回退 `/review`。Reader 内没有表单或 v2 mutation。
- 安全：治理视图仅见当前 FULL R1/R2；R3 改写后同一 Event 立即 404，R4 无行；低权限角色无法读取底表。没有绕过 `PublicationService` 或改变发布状态。
- 可观测性：`srbg_intelligence_v2_appendix_reads_total{outcome}` 只使用 `AVAILABLE / EMPTY / HEAVY / FAIL_CLOSED` 四种低基数结果，不记录 Event ID、正文或证据内容。

## 定向验证

| 命令 | 结果 |
| --- | --- |
| `make t11-reader-appendix-test` | PASS：10 backend/contract/integration tests + 3 component tests |
| `pnpm --filter @srbg/web test` | PASS：34 files / 101 tests |
| `pnpm --filter @srbg/web typecheck` | PASS |
| 隔离迁移与纵向测试（`verify_t11_migration.py`） | PASS：`0043 → 0044 → 0043 → 0044`，10 tests |
| T11 可观测性单测 | PASS：3 tests（与服务单测合并） |

## 全量门禁

| 门禁 | 结果 |
| --- | --- |
| `make lint` | PASS |
| `make typecheck` | PASS：mypy strict 148 files、UI/Web vue-tsc、生成类型 tsc |
| `make test` | PASS：Python 1264 passed / 27 existing environment skips；UI 53；Web 101 |
| `make contract-test` | PASS：109 |
| `make security-check` | PASS：pip/pnpm 无已知漏洞，Trivy 无 HIGH/CRITICAL secret/misconfiguration |
| `make fixture-replay` | PASS：357；Round09 mock replay 通过 |
| `make quality-gate` | PASS；首次 PyPI TLS EOF 后原样重跑通过，未更改审计门槛 |
| `make web-e2e` | PASS：74 |
| `make web-a11y` | PASS：21 |

## 证据边界

测试数据、协议 stub、迁移回放和本地浏览器结果只证明本票工程行为。它们不构成或声称 Owner Gold、真实 DeepSeek Schema 成功、任何真实来源准入、实际连续运行窗口或 GO 证据；也不改变 robots、条款、版权、限速、预算、熔断、重定向和公网地址安全门槛。
