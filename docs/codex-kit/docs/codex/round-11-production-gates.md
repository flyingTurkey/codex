# 第 11 轮：质量、运维、安全与上线门禁

```text
执行第11轮：把平台从功能完成提升为可内测、可监控、可恢复的生产候选版本。

读取：docs/codex-kit/docs/07-slo-test-acceptance.md、docs/codex-kit/docs/08-security-threat-model.md、docs/codex-kit/docs/09-operations-runbook.md、docs/codex-kit/docs/06-ui-ux-spec.md、docs/codex-kit/docs/ui/04-responsive-accessibility.md、docs/codex-kit/assets/validation/quality_gates.json、docs/codex-kit/assets/validation/readiness_evidence.schema.json。

必须交付：
- 来源健康、队列、解析、AI、审核、API、搜索和成本指标；
- Prometheus/Grafana/Sentry/OpenTelemetry配置；
- 失败队列、来源熔断、人工重放和优先级恢复；
- 500文档、300重复对、100事件、200事实证据和100搜索问题的金标集目录与评测工具；
- SLO看板、告警路由、错误预算和周报；
- PostgreSQL PITR、对象存储备份、Redis任务重建；
- 自动备份验证和一次完整恢复演练记录；
- SSRF、XSS、IDOR、越权、恶意文件、Prompt Injection、密钥和依赖扫描；
- 负载、容量和单文档成本基线；
- 开发/测试/预生产/生产配置隔离；
- 发布、回滚、撤回、来源故障和模型异常Runbook可执行验证；
- 内测种子用户和反馈指标埋点；
- 上线验收报告。
- 来源健康、运行中心和质量看板必须复用方案1设计系统；完成用户端与管理端的视觉回归、键盘、200%缩放、axe和性能验收；
- 上线验收证据必须通过 `readiness_evidence.schema.json`，每项结论记录策略版本与哈希、金标集版本与哈希、原始测试/监控/演练证据引用、执行时间和执行主体；
- 将 Schema 校验、金标回放、发布门禁对抗测试、安全扫描和 readiness 证据校验设为 CI required checks，提供分支保护/CODEOWNERS 配置说明，不得由普通合并、跳过检查或修改候选输出绕过；

不得伪造连续14天运行结果。可交付自动统计器和当前实测窗口；Codex 不得自行声称、设置或写入 `PRODUCTION_READY`，即使自动门禁全部通过，也只能提交可审核的就绪证据包，由独立的有权验收人作出生产决定。

强制门禁：
- 已发布关键事实证据覆盖100%；
- 无官方证据高风险误发布为0；
- 来源和性能达到 docs/codex-kit/docs/07-slo-test-acceptance.md 定义；
- 无高危安全问题；
- RPO≤15分钟、RTO≤4小时经演练；
- 所有质量指标由版本化金标集产生，报告携带金标和策略哈希并链接原始证据；
- 20名种子用户两周验收由真实记录确认。

结束时 Codex 只能给出三态结论之一：`BLOCKED`、`INTERNAL_PILOT_READY`、`READY_FOR_INDEPENDENT_ACCEPTANCE`，并逐项列出可验证原始证据。`PRODUCTION_READY` 仅能由独立有权验收人在审阅证据包后赋予。
```
