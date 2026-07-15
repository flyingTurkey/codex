# 第12轮测试基线

执行日期：2026-07-15。所有命令先加载 `scripts/use-local-toolchain.ps1`。环境为本地TEST Compose。

## 全局门禁

| 命令 | 退出 | 结果 |
|---|---:|---|
| `make lint` | 0 | Ruff、Token、UI/Web ESLint通过 |
| `make typecheck` | 0 | mypy strict 90文件；UI/Web/契约TS通过 |
| `make test` | 0 | Python 482 passed/11 skipped；UI 53；Web 69 |
| `make contract-test` | 0 | 生成可复现；56 passed |
| `make security-check` | 0 | pip-audit无已知漏洞；pnpm 1 low、无high；Trivy无HIGH/CRITICAL |
| `make fixture-replay` | 0 | 164 passed；Round09恶意样本6/6拒绝；provider=mock |
| `make quality-gate` | 0 | lint/typecheck/test/contract/security全通过 |
| `make web-e2e` | 0 | 42 passed |
| `make web-a11y` | 0 | 13 passed |

## 专项目标

| 目标 | 退出 | 结果/证据等级 |
|---|---:|---|
| `source-fixture-test` | 0 | 1 passed；FIXTURE_ONLY |
| `safety-regulation-test` | 0 | 3 passed；隔离库回放0011→0012→0011→0012；未评分精选回归测试通过 |
| `pdf-ocr-test` | 0 | 23 passed/1 skipped；真实OCR 3/3页可用；隔离库到0012 |
| `safety-case-test` | 0 | 5 passed；隔离库到0012 |
| `digital-case-test` | 0 | 16 passed |
| `paper-test` | 0 | 23 passed |
| `product-test` | 0 | 25 passed |
| `round08-test` | 0 | 14 passed |
| `round08-eval` | 0 | 300对/100事件，`evaluation_tier=INTERNAL_TEST_FIXTURE`，非真人金标 |
| `round09-test` | 0 | 41 passed；发布路径静态审计通过 |
| `round09-eval` | 0 | 4样本、mock、费用0 |
| `round10-test` | 0 | 26 passed |
| `round10-eval` | 0 | 40请求，P95 31.72ms；TEST数据 |
| `round11-test` | 0 | 41 passed；0011→0012→0011→0012 |
| `observability-test` | 0 | 6 passed |
| `load-test` | 0 | 100请求/并发10，错误0，P95 500.01ms，mock费用0 |
| `recovery-drill` | 0 | 隔离逻辑恢复RPO0/RTO0.1，非生产PITR |
| `runbook-test` | 0 | 2 passed |
| `round11-evidence-test` | 0 | 证据引用与哈希校验通过 |
| `resilience-test` | 0 | Redis down时readiness失败、恢复成功 |
| `smoke` | 0 | 完整版本契约、依赖探针、权威Feed对应空态/有数据状态和品牌均通过 |

PowerShell按分号顺序执行首批专项时不会因native exit自动停止，因此重新逐目标执行并记录上述退出码；不能用组合命令最终exit=0掩盖中间失败。

## 严格真实门禁

| 命令 | 退出 | 结论 |
|---|---:|---|
| `make golden-replay` | 2 | BLOCKED：documents 0/500、pairs 0/300、events 0/100、claim/evidence 0/200、search 0/100 |
| `make readiness-evidence` | 2 | 同上；严格门禁诚实拒绝晋级 |

严格真实门禁的非零是预期生产阻断，不应改绿。独立验收已按测试优先修复旧专项和smoke工程漂移，没有生成真人金标或降低阈值。

## 总结

主CI质量门禁、前11轮工程专项、fixture、smoke、E2E和a11y现全部通过。严格真实评测仍因五类真人金标为空返回BLOCKED；这是必须由业务标注责任人解决的外部证据阻断。
