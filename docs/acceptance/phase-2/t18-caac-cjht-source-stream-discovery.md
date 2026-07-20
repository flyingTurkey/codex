# T18 中国民用航空局与《中国公路学报》流发现验收记录

- 日期：2026-07-20
- Issue：flyingTurkey/codex #19
- 父 Spec：#1
- 原生 blocker：#8，已于 2026-07-19T22:00:25Z 关闭
- 规则版本：`t18-stream-discovery-w4-v1`

## 验收结果

本票形成两个可复核的 `BOUNDED + ADMISSION_READY` 研究记录：民航局机场司机构分类集合与《中国公路学报》正式当期目录。清单固定集合入口、允许主机、路径/查询边界、连接器、MIME、候选频率、策略版本、内容正负边界、合规观察、UTC 时间和证据链接。

研究状态保持失败关闭：两个 Source 均为 `CANDIDATE`，`desired_enabled=false`、`source_admission=null`、`actual_running=false`，没有追加 `PAUSE` 或覆盖信用。`ADMISSION_READY` 只路由后续 SourceAdmission Probe，不是 ADMIT、启用、运行或生产授权。

《中国公路学报》使用 `/CN/current`，因为核验时官网显示 2026 年第 39 卷第 6 期，而“当期目录” RSS 仍是 2023 条目；没有用失真的 RSS、固定 fixture、单篇论文或搜索结果补造持续流。期刊只允许题录、公开摘要边界和原文链接，ClaimBasis 固定为 `RESEARCH_CONCLUSION`。

## TDD 证据

1. RED：先新增研究契约行为测试，初次运行因实现/Schema 缺失失败。
2. GREEN：新增严格 JSON Schema 与机器可读清单后，专项测试 `4 passed`。
3. 并发保护：检测到工作区同时新增 T14/T20 来源发现实现后，没有修改对方文件；本票撤回自己创建的重复运行时模型，收敛为独立研究 Schema/清单，避免第二套业务模型。

专项命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/infrastructure/test_t18_source_stream_discovery.py -q
```

覆盖行为：

- 两个机构身份与两个 SourceStream 不混计；
- 根站、单篇材料、错误集合 URL 和运行权声明被 Schema 拒绝；
- 七类合规观察齐全且无 `UNKNOWN`；
- 民航局内容过滤与期刊 `RESEARCH_CONCLUSION`/版权边界；
- 无 Owner 意图、SourceAdmission、实际运行、PAUSE 或覆盖信用副作用。

## 非证据声明

本票没有生成或使用 Owner Gold，没有调用或宣称 DeepSeek 成功，没有形成真实 SourceAdmission、真实采集样本、72 小时运行窗口、ENGINEERING/PRODUCTION GO，也没有改写 PublicationService、R3/R4、robots、版权或公网安全边界。

## 门禁

当前 PowerShell 环境没有 `make` 可执行文件，因此严格按 Makefile 展开的等价底层命令执行：

- `lint`：通过；Ruff、设计令牌检查、UI/Web ESLint 全部通过。
- `typecheck`：通过；mypy strict（148 个源文件）、UI/Web TypeScript 及生成契约类型检查通过。
- `test`：通过；Python `1264 passed, 27 skipped`（均为仓库既有环境条件 skip，本票未新增），UI `53 passed`，Web `101 passed`。
- `contract-test`：通过；生成结果可复现，契约测试 `109 passed`。
- `fixture-replay`：通过；`357 passed`，Round09 对抗回放报告 `passed=true`。
- `security-check`：pip-audit 与 pnpm audit 均无已知漏洞；共享 Trivy 目录因并发门禁重建出现两次文件消失竞态，随后对校验为 1154 个文件的冻结同内容快照使用相同 Trivy 0.69.3、secret/misconfig、HIGH/CRITICAL、exit-code 1 参数复跑并通过。
- `quality-gate`：其 `lint + typecheck + test + contract-test + security-check` 组成项已分别按 Makefile 定义通过。

未通过降低阈值、删除断言、增加 skip 或吞异常使门禁变绿。
