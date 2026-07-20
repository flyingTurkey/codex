# T29 中国建筑科学研究院与中国交建 SourceStream 发现验收

> **SUPERSEDED：** Owner 于 2026-07-20 授权替换存在法律与持续集合阻断的中国建研院席位，改由 Issue #39 的《建筑科学与工程学报》承接。本文保留 #30 原始研究和 blocker 证据；关闭 #30 不表示复制许可已取得或原两流均达到 `ADMISSION_READY`。

## 范围与前置条件

本记录对应 GitHub Issue #30 和父 Spec #1。执行前已完整读取根 `AGENTS.md`、Issue #1/#30、Issue 跟踪与领域文档、`CONTEXT-MAP.md`、Acquisition CONTEXT、ADR-0001/0002/0003。GitHub 原生依赖接口确认 #30 唯一 blocker 为 #8，且 #8 已于 `2026-07-19T22:00:25Z` 关闭。

本票只补齐 `RES-003` 中国建筑科学研究院与 `ENT-001` 中国交建的来源研究 disposition，不执行 SourceAdmission、Owner 意图变更、采集、准入波次或发布。中国交建、中国交通建设集团及其有限公司/股份有限公司名称映射到同一个 canonical Source。

## 纵向行为

版本化清单 `t29_cabr_cccc_source_stream_discovery.json` 由严格 Pydantic 模型读取，并固定：

- 精确入口、允许主机/路径、连接器、预期 MIME、超时、重定向上限、限速、User-Agent、策略版本与 UTC 观察时间；
- `desired_enabled=false`、`source_admission=null`、`actual_running=false`，研究仓储接口只能追加 SourceResearchDisposition；
- 中国交建 `/news/jcxw/jx/` 为 `BOUNDED + ADMISSION_READY` 的后续 Probe 候选，按“工程对象 + 生命周期事实”过滤经营、资本市场、党建、人事、招聘和泛宣传；
- 中国建研院只有静态成果页且条款阻断 raw-first，保持 `CANDIDATE + MANUAL_SHADOW`，不写自动轮询频率；
- `RESEARCH_CONCLUSION`、`PROJECT_FIRST_PARTY_RECORD`、`MANUFACTURER_CLAIM` 和 `INDEPENDENT_VERIFICATION` 互不混淆；两个官方来源都不授予独立验证身份。

研究使用公开官网一手页面；没有登录、绕过验证码/WAF/付费墙或调用未公开接口。浏览器观察未固化官方 raw 字节时，响应 SHA-256 显式为 `null`；没有把 DOM、截图、事后重取内容或 CCCC 的 521 错误体填成官方 raw 哈希。完整证据见 `docs/research/2026-07-20-cabr-cccc-bounded-stream-discovery.md`。

## TDD 记录

1. RED 1：先新增专项行为测试，因 `T29DiscoveryManifest` 尚不存在而在收集阶段失败。
2. RED 2：加入模型骨架后，9 项测试因版本化研究清单不存在而失败。
3. 研究校正：一手证据证明 CABR 不满足持续集合和条款门槛，测试由预期“双流 ready”校正为 CABR 失败关闭、中国交建 ready；没有删除安全断言或降低门槛。
4. GREEN：专项与既有 T20 回归共 `20 passed`，定向 Ruff 通过。

专项命令：

```powershell
make t29-source-discovery-test
```

## 关闭判断与非证据声明

Issue #30 要求两个机构都形成 `BOUNDED + ADMISSION_READY` 才能关闭。中国交建满足研究态条件；CABR 同时存在 `NO_CONTINUOUS_COLLECTION` 和 `TERMS_PROHIBIT_COPYING`，因此 Issue #30 必须保持 OPEN，也不能解除 #31。

本票没有生成 Owner Gold、DeepSeek 成功、SourceAdmission、desired-enabled 意图、实际运行、运行窗口、PAUSE、覆盖信用或 ENGINEERING/PRODUCTION GO；没有绕过 PublicationService、R3/R4、robots、版权、条款、重定向或公网安全边界。

## 门禁结果

当前 Windows 环境没有全局 `make`，以下均使用 Makefile 中同一冻结工具和原始参数执行：

- `t29-source-discovery-test`：`20 passed`（含既有 T20 回归）。
- `lint`：Ruff、设计令牌一致性、UI/Web ESLint 全部通过。
- `typecheck`：mypy strict（149 个源文件）、UI/Web strict TypeScript 和生成契约类型检查通过。首次 UI 运行因 workspace 模块解析瞬态失败；执行冻结 `pnpm install --frozen-lockfile` 恢复现有依赖链接后原样重跑通过，没有改配置或跳过检查。
- `test`：Python `1331 passed, 27 skipped`（仓库既有环境条件 skip，本票未新增）；UI `53 passed`；Web `101 passed`。第一次全量 Python 运行时，共享工作区另一流程的 T20R 测试已出现但 manifest/注册事实尚未写完；其所属流程补齐后，T20R 专项 `5 passed`，全量原样复跑通过，本票未修改 T20R 产物。
- `contract-test`：生成结果可复现，契约测试 `109 passed`。
- `security-check`：pip-audit 与 pnpm audit 无已知漏洞；Trivy 0.69.3 首次因共享快照并发重建出现文件消失竞态，随后重新生成 1186 文件快照并使用完全相同的 secret/misconfig、HIGH/CRITICAL、exit-code 1 参数复跑通过。
- `fixture-replay`：`357 passed`；Round09 离线评估 `passed=true`、`provider=mock`、成本为零，没有冒充真实 DeepSeek 成功。
- `quality-gate`：其 lint、typecheck、test、contract-test 和 security-check 组成项均按 Makefile 原始定义通过。

本票未修改正式前端，`web-e2e` 和 `web-a11y` 不适用。没有删除断言、降低阈值、增加 skip 或吞异常。
