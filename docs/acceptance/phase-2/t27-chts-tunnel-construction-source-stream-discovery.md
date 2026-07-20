# T27 中国公路学会与《隧道建设（中英文）》SourceStream 发现验收

## 范围与前置

本记录对应 GitHub Issue #28。根 `AGENTS.md`、父 Spec #1、本 Issue、唯一原生 blocker #8、`CONTEXT-MAP.md`、四个相关 CONTEXT 以及 ADR-0001/0002/0003 均已完整读取；#8 为 `CLOSED`。

本票只增加研究事实，不更新 `desired_enabled`、SourceAdmission、运行状态、PublicationService 或 Reader 投影。两个机构继续分别只计一个 Source。

## 纵向行为

- 中国公路学会锁定动态成果通知集合，使用工程对象 + 生命周期 + 结果语义正向门禁，排除会议宣传、会员活动、征集与综合新闻；研究处置为 `BOUNDED + ADMISSION_READY`。
- 《隧道建设（中英文）》原官方站 HTTPS 阻断事实保留；持续流替换为万方 ISSN `2096-4498` 期刊专页及精确详情路径，ClaimBasis 固定为 `RESEARCH_CONCLUSION`，Reader 边界为题录、公开摘要和原链，处置为 `BOUNDED + ADMISSION_READY`。
- 两流固定 `desired_enabled=false`、`source_admission=null`、`actual_running=false`、`pause_appended=false`、`coverage_credit_granted=false`。
- 服务只接受具有 `record_research_disposition` 的窄仓储端口，不能写 Owner 意图、准入、运行或发布事实。
- `TUNNEL_GAS_MONITORING` 仅在 `TUNNEL + HIGHWAY/RAILWAY` 时成立；矿山瓦斯和单独隧道不补位。

详细公网证据、响应哈希和阻断见 [研究报告](../../research/2026-07-20-chts-tunnel-construction-source-stream-discovery.md)。

## TDD 证据

- RED 1：首次运行在测试收集阶段因 `srbg_api.source_registry.t27_source_stream_discovery` 不存在而失败。
- RED 2：API 与基础设施测试同名导致 pytest 模块冲突；仅重命名本票基础设施测试，未删除或放宽断言。
- RED 3：替代要求先把期刊预期改为万方 HTTPS 集合、`ADMISSION_READY` 和 `closure_eligible=true`；旧清单产生 4 项预期失败。
- GREEN：19 项定向测试通过，覆盖机构/流计数、替代集合精确边界、研究/运行隔离、关闭资格、未知合规失败关闭、私网与越界重定向拒绝、学会正负例、期刊 ClaimBasis/版权投影、隧道瓦斯组合不变量、只写研究 disposition 及版本化 Schema。

## 门禁结果

- `make t27-source-discovery-test`：`19 passed`。
- `make lint`：通过。
- `make typecheck`：通过（mypy strict 覆盖 149 个源文件，UI/Web TypeScript 检查通过）。
- `make test`：通过（Python `1346 passed, 27 skipped`；UI `53 passed`；Web `101 passed`）。
- `make contract-test`：`109 passed`，生成契约可复现。
- `make fixture-replay`：`357 passed`；仅使用 mock 评估，成本为 0，不能表述为真实 DeepSeek 成功。
- `make security-check`：通过；Python 与 pnpm 依赖审计无已知漏洞，Trivy 以 `secret,misconfig`、HIGH/CRITICAL、`exit-code 1` 扫描通过，无发现。
- `make quality-gate`：单次完整运行通过，包含 lint、strict typecheck、Python/UI/Web 全量测试、契约可复现检查、依赖审计与 Trivy 安全扫描。
- `make web-e2e`、`make web-a11y`：本票不涉及正式前端，按适用性不运行。

因此，本票纵向行为、独立门禁和单次完整 `quality-gate` 均为绿色。fixture 评估仍明确是 mock，不构成真实 DeepSeek 成功或 closeout GO。

## 关闭判断与诚实边界

Issue #28 规定只有两个流都形成 `BOUNDED + ADMISSION_READY` 才可关闭。万方替代入口具有有效 HTTPS、零重定向、精确 ISSN/期次/详情边界及公开题录摘要访问边界；两流因此均达到研究态条件，机器清单固定 `closure_eligible=true`。Issue #28 已于 2026-07-20 以 `completed` 关闭并解除后续准入波次。

此关闭只针对 SourceResearchDisposition。万方页面未发布有效 robots directives，也未提供自动化许可；后续 SourceAdmission 必须重新核验并决定是否可运行。内部 API、在线阅读、下载、PDF、图片和全文均不在授权范围内。

本票未生成或补写 Owner Gold、DeepSeek RealSchemaSuccess、SourceAdmission、Owner 意图、真实运行窗口、观察时长、覆盖信用或 closeout GO。未绕过 PublicationService、R3/R4、robots、版权、重定向或公网地址安全边界。
