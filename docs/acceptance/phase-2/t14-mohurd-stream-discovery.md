# T14 验收记录：住房和城乡建设部有界流发现

Issue：`flyingTurkey/codex#15`。父 Spec：`#1`。原生 blocker：`#8`，核验时已关闭。

## 验收结果

本轮锁定一个 Source 下的三个有界 SourceStream：建筑市场监管 `F`、工程质量安全监管 `G`、标准定额 `K`。正式 W2 候选使用 `GOV-005-G`，与既有国家矿山安全监察局通知公告流配对。

三个精确集合均为 `StreamReadiness=BOUNDED`、`SourceResearchDisposition=ADMISSION_READY`，`admission_ready=true`，满足 Issue 的研究票关闭条件。点时证据把 robots 404 记录为“已核验未发布、绝不推定许可”，把公开目录、网站地图和官方导航未链接独立自动化访问条款记录为 `VERIFIED_NO_SEPARATE_TERMS`，并把页脚转载须注明来源记录为 `VERIFIED_RESTRICTED`。

这里的 `ADMISSION_READY` 严格沿用仓库既有语义：只表示有界集合已找到、未发现必须绕过的访问控制，可以进入后续 SourceAdmission Probe；不表示 robots、条款、版权、频率或运行门禁通过。Source 继续是 `CANDIDATE` 且 `enabled=false`，404 robots 和未链接独立条款不被解释为自动采集许可，后续证据不足必须失败关闭。

本轮没有改变 `desired_enabled`，没有写 `SourceAdmission`，没有改变运行状态，没有追加 `PAUSE`，没有执行真实采集、准入波次或运行窗口；也没有产生或宣称 Owner Gold、DeepSeek 成功、工程 GO 或生产 GO。PublicationService、R3/R4、robots、版权与公网安全边界均未变更。

## TDD 证据

- 初始 RED：`tests/infrastructure/test_t14_mohurd_stream_research.py` 首次运行 `4 failed`，原因是版本化 Schema 与研究记录尚不存在。
- 关闭语义 RED：先把预期收紧为 `BOUNDED + ADMISSION_READY` 后运行，得到 `2 failed, 2 passed`；失败分别来自旧的 `closure_eligible=false` 与 `BOUNDARY_DISCOVERY`。
- GREEN：最小修改 Schema、记录和文档后，专项 pytest `4 passed`；本票测试文件 Ruff `All checks passed`。

## 门禁结果

- `make typecheck`：通过。
- `make contract-test`：通过，`109 passed`。
- `make security-check`：通过；Python/Node 依赖无已知漏洞，Trivy 无 HIGH/CRITICAL secret 或 misconfiguration 发现。
- `make fixture-replay`：通过，`357 passed`，固定评估 `passed=true`。
- `make lint`：未通过；只命中未执行、未跟踪的 T16 测试文件 `apps/api/tests/test_t16_source_stream_discovery.py` 的 import 排序错误。本票专项 Ruff 通过。
- `make test`：未通过；`1265 passed, 9 failed, 27 skipped`。9 项全部位于未执行的 T16 测试：其 Issue #17 清单被当前 T20 专用 `DiscoveryManifest` 的 Issue #21 范围校验拒绝。本票四项测试在同一次全量运行中通过。
- `make quality-gate`：未通过；停在同一未执行 T16 文件的 1 项 import 排序和 2 项行长错误。

因此本记录不宣称共享工作区全门禁完成。用户已明确 T16/T18 尚未执行且不影响本任务；本票自身关闭条件、专项测试及不受该未执行文件影响的门禁均已通过。未删除断言、降低阈值、增加 skip 或修改 T16 文件规避失败。

## 产物

- `docs/codex-kit/assets/validation/t14_source_stream_research.schema.json`
- `docs/codex-kit/assets/validation/t14_mohurd_source_stream_research.json`
- `docs/research/2026-07-20-mohurd-bounded-stream-discovery.md`
- `tests/infrastructure/test_t14_mohurd_stream_research.py`
