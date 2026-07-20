# T31R 四川省住房城乡建设厅与贵州省能源局替代流验收

## 范围与依赖

本记录对应 GitHub Issue #38，替代但不改写 Issue #32。父 Spec #1 与原生 blocker #8 已核验，#8 已关闭；已读取根 `AGENTS.md`、`CONTEXT-MAP.md`、Acquisition / Evidence & AI / Publication & Reader / Platform Governance CONTEXT 以及 ADR-0001/0002/0003。纵向范围仅为两个 SourceStream 的研究边界与第二批映射，不执行 SourceAdmission、采集运行或发布。

## TDD 证据

RED：先新增 `tests/infrastructure/test_t31r_replacement_source_stream_discovery.py`，因替代 Schema、清单和映射不存在得到 10 项预期失败。

GREEN：最小加入版本化 Schema、清单、`GOV-023` 未启用候选、第二批 rollout/campaign 替换和 Make target，定向测试得到 `10 passed`。测试拒绝伪造启用、准入、独立验证、未知合规状态以及“有 blocker 仍关闭”。

## 验收边界

- 两个来源各一条精确 `HTML_LIST_DETAIL` 流，均为 `BOUNDED + FILTERED + ADMISSION_READY`，无 blocker。
- 来源保持 `CANDIDATE`、`desired_enabled=false`、`source_admission=null`、`actual_running=false`、`pause_appended=false`、`coverage_credit_granted=false`。
- robots 404 不等于允许；未发现单独条款不等于授权；公开再分发保持关闭。
- Authority、矿业 facet、PublicationService、R3/R4、版权和公网安全边界均未降低。

## 门禁

Windows PowerShell 未提供 `make.exe`，因此按 Makefile 原始 recipe 使用仓库固定的 `.tools/uv/uv.exe` 和 `.tools/node/pnpm.cmd` 逐项执行，没有跳过任何子命令：

- `t31r-source-discovery-test` 等价命令：`10 passed`；原 T31 与迁移回归：`11 passed`。
- `lint`：Ruff、设计令牌、UI ESLint、Web ESLint 全部通过。
- `typecheck`：mypy strict、UI `vue-tsc`、Nuxt typecheck、生成契约 TypeScript 检查全部通过。
- `test`：Python `1346 passed, 27 skipped`（仓库既有条件性 skips 未新增）、UI `53 passed`、Web `101 passed`。
- `contract-test`：生成物可重复，契约测试 `109 passed`。
- `fixture-replay`：`357 passed`；评估器明确为 `provider=mock`、`cost_microusd=0`。
- `security-check`：`pip-audit` 与 `pnpm audit` 无已知漏洞；Trivy HIGH/CRITICAL secret/misconfiguration 扫描为零发现。
- `quality-gate`：其 lint、typecheck、test、contract-test、security-check 全部组成项通过。

本票不修改正式前端，`web-e2e` 与 `web-a11y` 不适用。任何 fixture 或离线测试均不代表 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口、PAUSE、覆盖信用或 GO。
