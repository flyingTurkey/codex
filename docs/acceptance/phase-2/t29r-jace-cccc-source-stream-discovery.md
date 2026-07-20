# T29R《建筑科学与工程学报》与中国交建替代 SourceStream 验收

本记录对应 GitHub Issue #39、父 Spec #1，并 supersede #30。中国建研院原始 blocker 保留，不改写为已解除；替代组合新增唯一候选 `RES-013`《建筑科学与工程学报》，并复用 `ENT-001` 中国交建。

## 纵向行为

- `RES-013` 固定官方当前刊期 API、由其返回的刊期 ID 驱动的文章列表 API、同一主机、两个精确路径和 query allowlist；根站、搜索、任意刊期 ID、超过 50 条、全文与附件均不在边界内。
- 期刊只接受直接在域论文，ClaimBasis 只能是 `RESEARCH_CONCLUSION`；Schema 会拒绝 `INDEPENDENT_VERIFICATION` 提升。
- `ENT-001` 原集合 `/news/jcxw/jx/`、alias、内容负例及 `PROJECT_FIRST_PARTY_RECORD`/`MANUFACTURER_CLAIM` 边界保持不变。
- 两流均固定 `BOUNDED + ADMISSION_READY`，但 `desired_enabled=false`、`source_admission=null`、`actual_running=false`、无 PAUSE、无覆盖信用、无附件和公开再分发。
- canonical registry 新增 `RES-013` 候选；第二批 rollout/campaign 仅把中国建研院替换为期刊，总机构数仍为二十。

## TDD 证据

RED：先新增 5 项行为测试，因 T29R manifest/Schema 与 `RES-013` 尚不存在、rollout 尚未替换，得到 5 个预期失败。

GREEN：新增版本化 Schema、manifest、注册表和组合替换后，5 项测试通过。反向测试会拒绝 UNKNOWN 合规、实际运行、独立验证冒充和 `size_max=500` 的 query 扩张。

## 诚实边界

本票未取得或伪造 Owner Gold、DeepSeek 成功、SourceAdmission、实际运行、72 小时窗口、覆盖信用或 GO。浏览器 API 响应未固化官方原始字节时哈希保持 `null`。robots 404 只表示未发布；未来运行仍由 SourceAdmission 重查。PublicationService、R3/R4、版权、raw-first 与公网逐跳安全边界未被绕过。

## Issue 收口

- #39：两条替代流满足本票研究态关闭条件后以 `COMPLETED` 关闭。
- #30：以 `NOT_PLANNED / SUPERSEDED` 关闭，不表示中国建研院 blocker 已解除。
- #31：标题、正文与原生依赖改为消费 #39 的《建筑科学与工程学报》和中国交建，#29 仍是另一原生 blocker。

## 门禁结果

- `make t29r-source-discovery-test` 等价命令：5 passed；共享 registry/rollout/campaign 定向回归：41 passed。
- `make lint`：Ruff、设计 token、Nuxt UI 与 Web ESLint 全部通过。
- `make typecheck`：mypy strict、Nuxt UI/Web typecheck 与生成契约 TypeScript 检查全部通过。
- `make test`：Python 1346 passed、27 skipped（仓库既有条件型跳过）；UI 53 passed；Web 101 passed。
- `make contract-test`：生成契约可复现，109 passed。
- `make fixture-replay`：357 passed；离线质量评估为 `provider=mock` 且通过，不构成真实 DeepSeek 成功。
- `make security-check`：pip-audit 与 pnpm audit 无已知漏洞；Trivy secret/misconfiguration HIGH/CRITICAL 为 0。
- `make quality-gate` 的 lint/typecheck/test/contract-test/security-check 组成项全部通过。
- 本票不涉及正式前端行为，`make web-e2e` 与 `make web-a11y` 不适用。
