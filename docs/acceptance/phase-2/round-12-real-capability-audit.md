# 第12轮真实能力审计验收记录

- 日期：2026-07-15
- 审计基线：`c9ffd4b2c70d3fa7a1c52fbb194dbba943039372`
- 环境：本地TEST Compose
- 进入时工作树：clean
- 业务代码、迁移、契约、依赖、配置和测试阈值变更：无
- 独立验收入口提交：`9a300cdfbb49141448d89f7bfc573373445f034e`
- 结论：`当前轮未完成/BLOCKED`

独立验收于`2026-07-15T12:01:07.7527716Z`从clean工作树开始，分支为`codex/round-10-feed-search-daily`。静态和运行Alembic head均为`0012_operations_readiness`；API版本为`v1`、内容Schema `1.1.0`、搜索Schema `1.0.0`且语义搜索关闭；本地TEST Compose的API、Web、PostgreSQL、Redis、MinIO、Worker、Parser、Publisher、Scheduler、AI Worker和观测组件健康。

## 审计问题与证据规则

本轮从第一性原理验证“平台是否能把获准真实来源转为可追溯Event并安全投影给内部用户”，而不是统计已写代码。状态只使用 IMPLEMENTED、PARTIAL、FIXTURE_ONLY、MOCK_ONLY、BROKEN、MISSING、NOT_APPLICABLE；E1代码、E2确定性测试、E3当前运行、E4真实外部证据逐级区分。

## 交付文件

1. `docs/audit/phase-2/current-architecture.md`
2. `docs/audit/phase-2/capability-matrix.csv`
3. `docs/audit/phase-2/source-and-connector-inventory.csv`
4. `docs/audit/phase-2/runtime-baseline.md`
5. `docs/audit/phase-2/test-baseline.md`
6. `docs/audit/phase-2/end-to-end-trace.md`
7. `docs/audit/phase-2/mock-fixture-todo-inventory.csv`
8. `docs/audit/phase-2/security-publication-audit.md`
9. `docs/audit/phase-2/metrics-baseline.json`
10. `docs/audit/phase-2/metrics-definition.md`
11. `docs/audit/phase-2/gap-and-migration-plan.md`
12. `docs/audit/phase-2/documentation-drift.md`

## 关键事实

- 46条种子来源全部CANDIDATE/disabled；运行库54条ACTIVE均为测试来源，108次fetch_run全为FIXTURE。真实追踪为NOT_AVAILABLE。
- Worker Beat只有MEM安全规定单一来源任务；其他适配器没有接入统一运行链。
- Event、event_item、topic_cluster运行计数均为0；Publication、Search、Daily、Saved仍以Item为身份。
- 普通用户API声明CurrentPrincipal，但TEST默认本地身份；普通读连接直接访问业务表，专用只读发布投影角色不存在。
- API/Worker不能写publication，但可直接INSERT自造audit_log事件和hash；UPDATE/DELETE由触发器拒绝。无独立hash根锚定。
- R3白名单在Feed/详情和UI实测成立，R4有确定性隔离测试；搜索/日报/缓存缺真实运行数据。
- 新被动usage写匿名小时桶；旧usage_event仍有250条带actor_id的SEARCH记录，缺保留、删除和专门管理员边界。
- 真人金标五类样本均为0；Round08的300/100为INTERNAL_TEST_FIXTURE。
- AI provider为mock、费用0；通知、国际来源、真实浏览历史策略和连续运行均不存在或未确认，指标为null。

## 命令结果

通过：`make lint`、`typecheck`、`test`、`contract-test`、`security-check`、`fixture-replay`、`quality-gate`、`source-fixture-test`、`digital-case-test`、`paper-test`、`product-test`、`round08-test/eval`、`round09-test/eval`、`round10-test/eval`、`round11-test`、`observability-test`、`load-test`、`recovery-drill`、`runbook-test`、`round11-evidence-test`、`resilience-test`、`web-e2e`、`web-a11y`。

独立验收修复前失败证据：

- `make safety-regulation-test`、`make pdf-ocr-test`、`make safety-case-test`：退出1；隔离runner停在0009，当前查询引用0010 `ai_pipeline_run`。
- `make smoke`：退出1；脚本要求旧两字段version对象，当前契约合法增加search schema和semantic flag。
- `make golden-replay`、`make readiness-evidence`：退出1且decision=BLOCKED；五类真人金标数量均为0。这两项是诚实生产阻断，不应修成绿色。

独立验收采用测试优先完成三项最小修复：隔离集成默认迁移到当前0012 head；smoke校验完整版本契约并依据权威Feed区分空态/有数据态；统一Feed的selected查询要求存在当前score_set，阻止未评分已发布内容进入精选。没有修改迁移、来源状态、真实凭据、金标或阈值。

修复后本次通过：`make safety-regulation-test`（3 passed）、`pdf-ocr-test`（23 passed/1 skipped）、`safety-case-test`（5 passed）、`smoke`、`quality-gate`（Python 482 passed/11 skipped、UI 53、Web 69、契约56）、`fixture-replay`（164）、`web-e2e`（42）和`web-a11y`（13），以及其余Round01—11专项、观测、负载、恢复、Runbook、发布路径与证据完整性验证。

完整数量和环境见 `test-baseline.md`。

## 未核验与风险

未核验真实OIDC、真实来源连续采集、生产告警、PITR、模型费用、通知送达、国际翻译、150来源容量和真人运营。数据库权限、Item主身份、审计写入和历史usage数据是第13—14轮前的高优先级风险。

## 停止与提交边界

独立验收获得了“范围内一般问题先写失败测试并最小修复”的授权；仅修改查询过滤、运行验证脚本、回归测试和第12轮证据文档。没有开始第13轮，也没有启用真实来源、模型或通知。提交哈希由最终执行结果报告，避免文件自引用不可能问题。

## 结论

所有工程门禁和前11轮专项现已通过，审计产物可复核；但本次独立验收要求真实外部证据齐全，严格金标/readiness仍因五类真人标注均为0返回BLOCKED。该证据必须由业务标注责任人提供，不能由Codex生成。结论：当前轮未完成/BLOCKED。
