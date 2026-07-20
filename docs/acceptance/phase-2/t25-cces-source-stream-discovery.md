# T25 中国土木工程学会 SourceStream 发现验收记录

- 日期：2026-07-20
- Issue：flyingTurkey/codex #26
- 父 Spec：#1
- 原生 blocker：#8，已于 2026-07-19T22:00:25Z 关闭
- 规则版本：`t25-cces-source-stream-discovery-v2`

## 验收结论

本票在一个 `RES-011` Source 下保留两个精确流边界。旧站詹天佑奖流继续因 HTTP-only 保持 `BOUNDARY_DISCOVERY`；标准流没有绕过 TLS，而是替换为国家标准委组织、中国标准化研究院建设的全国团体标准信息平台中的 CCES 固定机构集合。

替代流使用唯一 CCES 机构 ID、固定 HTTPS POST API 和固定详情路径，点时返回 73 条中国土木工程学会标准记录。公网地址、TLS、重定向、robots、平台服务范围、版权、访问边界和公开可达性均已保存证据、UTC 时间和 raw SHA-256。标准正文明确为“不公开”，所以连接器只处理公开元数据。

`RES-011-STANDARD-RELEASES` 达到 `BOUNDED + ADMISSION_READY`，ticket `closure_eligible=true`，满足 Issue #26 关闭条件。研究清单仍固定 `desired_enabled=false`、`source_admission=null`、`actual_running=false`、`pause_appended=false`、`coverage_credit_granted=false`；没有执行真实 SourceAdmission、W2 波次或采集运行。

## TDD 证据

1. 初始 RED：先新增 9 项基础设施行为测试，Schema 与研究清单不存在时为 `9 failed`；最小实现后 `9 passed`。
2. 阻断替换 RED：测试先改为要求 HTTPS 公共平台替代流、固定机构 ID、精确 POST 边界和 `closure_eligible=true`，旧清单运行结果为 `5 failed, 4 passed`。
3. 边界收紧 RED：新增 API 必须 POST/JSON、robots 必须 text/plain 的篡改测试，旧 Schema 为 `1 failed, 8 passed`。
4. GREEN：Schema 与机器清单升级到 v2 后，专项测试 `9 passed`。

覆盖行为：

- #8 必须已关闭，且只有替代流达到 `BOUNDED + ADMISSION_READY` 后 ticket 才可关闭；
- 固定 `www.ttbz.org.cn`、CCES 唯一机构 ID、POST API、请求体、详情路径、MIME、候选频率和策略版本；
- robots 禁止路径、登录、账户、PDF/附件和标准正文均在边界外；
- 学会标准与奖项只使用 `PROJECT_FIRST_PARTY_RECORD`，不得提升为权威认定或独立验证；
- Schema 拒绝伪造 SourceAdmission、运行、PAUSE、覆盖信用、请求方法、机构 ID 或允许主机；
- W2 明确引用既有全国标准信息公共服务平台标准元数据候选，不重复研究或授予准入。

## 非证据声明

本票没有生成或使用 Owner Gold，没有调用或宣称 DeepSeek 成功，没有形成真实来源准入、真实采集样本、72 小时运行窗口或 ENGINEERING/PRODUCTION GO，也没有绕过 PublicationService、R3/R4、robots、版权、公网地址或 TLS 安全边界。

## 门禁

- T25 专项 pytest：`9 passed`。
- lint 等价步骤：Ruff、design token 检查、UI/Web ESLint 均通过。
- typecheck 等价步骤：mypy strict（`149 source files`）、UI/Web TypeScript 与 contracts TypeScript 均通过。
- test 等价步骤：Python `1331 passed, 27 skipped`，UI `53 passed`，Web `101 passed`；本票未新增 skip。
- contract-test 等价步骤：生成结果可复现，契约测试 `109 passed`。
- security-check 等价步骤：`pip-audit` 与 `pnpm audit` 无已知漏洞；Trivy `0.69.3` 扫描 1186 个文件，HIGH/CRITICAL secret 与 misconfiguration 均为 0。
- fixture-replay：`357 passed`；Round09 质量评估 `passed=true`，仅使用 mock provider，费用为 0。
- 前端 E2E/a11y：本票未修改前端，不适用。
- `make` 在当前 Windows 环境不可用；上述命令按 Makefile 目标逐项执行，`quality-gate` 的 lint、typecheck、test、contract-test 和 security-check 组成项全部通过。
