# 第12轮测试基线

执行日期：2026-07-15。所有命令先加载 `scripts/use-local-toolchain.ps1`。环境为本地TEST Compose。

## 全局门禁

| 命令 | 退出 | 结果 |
|---|---:|---|
| `make lint` | 0 | Ruff、Token、UI/Web ESLint通过 |
| `make typecheck` | 0 | mypy strict 90文件；UI/Web/契约TS通过 |
| `make test` | 0 | Python 477 passed/11 skipped；UI 53；Web 69 |
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
| `safety-regulation-test` | 2 | 2 failed/1 passed；隔离库只迁移至0009，当前查询需要0010 `ai_pipeline_run` |
| `pdf-ocr-test` | 2 | 同一 `ai_pipeline_run` 缺表回归 |
| `safety-case-test` | 2 | 同一旧专项迁移边界回归 |
| `digital-case-test` | 0 | 16 passed |
| `paper-test` | 0 | 23 passed |
| `product-test` | 0 | 25 passed |
| `round08-test` | 0 | 14 passed |
| `round08-eval` | 0 | 300对/100事件，`evaluation_tier=INTERNAL_TEST_FIXTURE`，非真人金标 |
| `round09-test` | 0 | 41 passed；发布路径静态审计通过 |
| `round09-eval` | 0 | 4样本、mock、费用0 |
| `round10-test` | 0 | 26 passed |
| `round10-eval` | 0 | 40请求，P95 31.53ms；TEST数据 |
| `round11-test` | 0 | 41 passed；0011→0012→0011→0012 |
| `observability-test` | 0 | 6 passed |
| `load-test` | 0 | 100请求/并发10，错误0，P95 103.45ms，mock费用0 |
| `recovery-drill` | 0 | 隔离逻辑恢复RPO0/RTO0.11，非生产PITR |
| `runbook-test` | 0 | 2 passed |
| `round11-evidence-test` | 0 | 证据引用与哈希校验通过 |
| `resilience-test` | 0 | Redis down时readiness失败、恢复成功 |
| `smoke` | 2 | 版本契约脚本只接受两个字段，当前API合法增加search schema与semantic flag |

PowerShell按分号顺序执行首批专项时不会因native exit自动停止，因此重新逐目标执行并记录上述退出码；不能用组合命令最终exit=0掩盖中间失败。

## 严格真实门禁

| 命令 | 退出 | 结论 |
|---|---:|---|
| `make golden-replay` | 2 | BLOCKED：documents 0/500、pairs 0/300、events 0/100、claim/evidence 0/200、search 0/100 |
| `make readiness-evidence` | 2 | 同上；严格门禁诚实拒绝晋级 |

严格真实门禁的非零是预期生产阻断，不应改绿。旧专项和smoke失败则是工程测试漂移；本轮未获业务修复授权，已固化证据。

## 总结

主CI质量门禁通过，但“前11轮所有专项测试”没有全部通过。根据AGENTS完成定义，第12轮不能宣称完成；审计产物仍可提交供第13轮前修复排序使用。
