# v2 T01：领域分类失败关闭验收记录

日期：2026-07-19

对应 GitHub Issue：`flyingTurkey/codex#2`；父 Spec：`#1`。

## 范围与不变量

- 只交付 `候选文档/证据块 → ClassificationOutput → 抽取候选或 QualificationReviewCase` 纵向行为；没有新增发布入口、来源启用、生产切换或 AI 可用性结论。
- `EngineeringObject` 固定为十一类；`PrimaryType` 恰好一个，模型不能通过交叉属性授予热点、风险、复核或发布状态。
- `TUNNEL_GAS_MONITORING` 只接受 `TUNNEL + HIGHWAY|RAILWAY`，并拒绝 `MINING` 组合；矿井瓦斯不补交通隧道专项。
- `CONSTRUCTION_MACHINERY` 必须有正文中的工程生命周期事实；ERP、生产线和泛工业互联网命中服务端锁定负例后失败关闭。
- 模型证据定位必须属于本次最小输入的 document block；虚构 locator 进入复核，不进入抽取。
- 模型不能写风险、复核、发布或热点授予；额外字段继续由严格 Pydantic/JSON Schema 拒绝。

## TDD 证据

- 首个 RED：分类测试因缺少 `QualificationReason`、结构回放报告类型而在收集阶段失败。
- 第二个 RED：锁定负例纵向测试显示原链路虽停止抽取，但没有把服务端原因写入复核 payload；实现后持久原因固定为 `LOCKED_NEGATIVE`。
- 第三个 RED：模型虚构 evidence locator 未被识别；实现后稳定返回 `EVIDENCE_LOCATOR_MISMATCH`。
- 第四个 RED：结构回放中的瓦斯专项未保存合法交通隧道组合；实现后同时覆盖公路与铁路隧道。
- 定向 GREEN：分类契约、结构回放、AI 准备/Worker、Schema 与 CLI 相关测试全部通过；最终全量门禁结果记录在下节。

## 版本化评估边界

- Corpus 版本为 `civil-intelligence-structural-replay-v2.0.0`，分布保持 180 正例、90 边界例、90 负例。
- CLI 只读取调用者提供的预测，不生成预测，不写 HUMAN_OWNER 标记，不保存自动通过阈值。
- 报告固定为 `label_authority=STRUCTURAL_REPLAY`、`authorizes_auto_pass=false`；即使结构回放 precision/recall 为 100%，也不能用于 Issue #3 的 Owner Gold 校准或生产授权。
- 本票没有调用 DeepSeek、没有探测 Secret、没有启用来源、没有制造来源观察窗口；engineering/production 继续沿用现有 `NO_GO` 证据。

## 门禁结果

- `lint`：全仓 Ruff 通过；设计令牌检查、UI/Web ESLint 通过。
- `typecheck`：mypy strict 检查 138 个源文件通过；UI `vue-tsc`、Nuxt typecheck 和生成契约 TypeScript 检查通过。
- `test`：Python `1102 passed, 27 skipped`；既有 27 个 skip 未由本票增加。UI `53 passed`，Web 单元测试 `92 passed`。
- `contract-test`：生成契约可复现，契约测试 `93 passed`。
- 定向覆盖：标准库 `trace` 执行分类契约、结构回放和 CLI 共 `25 passed`；`qualification.py`、`structural_corpus.py` 与评估 CLI 的已发现可执行行覆盖率均为 100%。仓库未安装额外 coverage 插件，未修改依赖或阈值。
- `fixture-replay`：`355 passed`；Round09 对抗 fixture 报告为 `provider=mock`、`cost_microusd=0`、`passed=true`，只证明离线协议行为。
- `security-check`：pip-audit 与 pnpm production audit 无已知漏洞；Trivy Secret/Misconfiguration 无 HIGH/CRITICAL 发现。
- `quality-gate`：当前 Windows PowerShell 没有 `make`/`uv` 命令入口，已使用仓库 `.venv` 与可用 pnpm 逐条执行该目标的 lint、typecheck、test、contract-test、security-check 全部底层命令，未省略组成门禁。
- 本票不修改正式 Web 页面，因此没有把 `web-e2e` / `web-a11y` 作为本票新增门禁；全量 Web 单元、lint 与 strict typecheck 仍已通过。

最终结论：本票代码与离线门禁通过。它不产生 Owner Gold、自动通过阈值批准、真实 DeepSeek Schema 成功、SourceAdmission、来源运行窗口或 engineering/production GO；这些外部事实继续失败关闭并由后续 tickets 独立验收。
