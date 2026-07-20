# T23 四川省交通运输厅 SourceStream 发现验收

## 范围

本轮只实现 Issue #24：为既有 `GOV-015` 锁定四川省交通运输厅有界流并交付后续第二批 W1 的研究输入。不重复应急管理部研究，不执行 SourceAdmission、启用、采集或真实准入波次。

## TDD 证据

- RED：新增 `tests/infrastructure/test_t23_sichuan_transport_stream_discovery.py` 后首次运行，因版本化 Schema 和机器记录不存在得到 `6 failed`。
- GREEN：最小加入 Schema 与研究记录后，同一专项得到 `6 passed`。
- 测试覆盖一个机构/四个流、精确 URL/主机/分页与详情路径、MIME/频率/策略、合规证据、受限版权、根页/搜索/单篇拒绝、控制能力隔离和 W1 法域分离。

## 一手核验

核验时间为 2026-07-20 11:10:48（Asia/Shanghai）。HTTPS 列表与样本详情均为零跳 `200 text/html`；机器记录保存响应 SHA-256。`robots.txt` 为 404；官网网站声明要求注明来源并限制原版原式转载；HTTP 不自动升级。因此清单只允许 HTTPS，公开使用只限题录、必要短摘、来源标注和原链，禁止全文再分发。

## 验收结果

- `GOV-015` 仍只计一个 Source；四个栏目是 SourceStream，不虚增机构数。
- 四流均为 `BOUNDED + ADMISSION_READY`，且所有合规事实均有明确点时结果；`ADMISSION_READY` 不等于 SourceAdmission。
- Source 仍为 `CANDIDATE`、`desired_enabled=false`；未写准入、未运行、未追加 PAUSE、未授予覆盖信用。
- 与 `GOV-007` 应急管理部事故调查报告流组成第二批 W1 的边界已明确，四川地方工程事实与全国事故调查保持来源和法域分离。
- 未产生或宣称 Owner Gold、DeepSeek 成功、真实来源准入、运行窗口或 closeout GO；PublicationService、R3/R4、robots、版权和公网安全边界未改变。

## 门禁

- `make t23-source-discovery-test`：通过，`6 passed`。
- `make lint`：通过。
- `make typecheck`：通过。
- `make contract-test`：通过，`109 passed`。
- `make security-check`：通过；`pip-audit`、pnpm audit 与 Trivy secret/misconfiguration 扫描无已知高危问题。共享 Trivy 输入目录曾因并行门禁产生瞬态目录竞争；等待占用释放后原命令完整通过，未清理其他任务产物或跳过扫描。
- `make fixture-replay`：通过，`357 passed`，离线评估 `passed=true`。
- `make test`：通过；Python `1331 passed, 27 skipped`，UI `53 passed`，Web `101 passed`。
- `make quality-gate`：通过；包含 lint、typecheck、Python/UI/Web 测试、契约生成复现与 `109 passed` 契约测试，以及完整依赖、secret 和 misconfiguration 安全扫描。

未新增 skip、未删除或放宽断言，也未伪造任何并行任务来源记录。T29、T20R 与 T25 的并行中间态均通过只读等待自然收口，本票未覆盖其文件；仓库级 `test` 与 `quality-gate` 最终全绿，GitHub Issue #24 已于 2026-07-20 正常关闭。
