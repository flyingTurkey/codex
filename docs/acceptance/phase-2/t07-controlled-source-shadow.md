# T07 Owner 意图到 SourceAdmission 和受控影子采集验收

## 范围与结论

本记录对应 GitHub Issue #8，只验收一个受控 SourceStream 从研究事实、Owner 意图、逐流准入、影子授权、raw-first 保存到既有 qualification handoff 的纵向行为。父 Spec #1 已读取；原生 blockers #2、#6 均为 CLOSED。Acquisition、Intelligence Qualification、Evidence & AI、Publication & Reader Projection 四个 CONTEXT，以及 ADR-0001、ADR-0002、ADR-0003 均已核对，无冲突。

结论：工程实现与确定性测试通过；真实来源准入、真实运行窗口、Owner Gold、DeepSeek RealSchemaSuccess、ENGINEERING_CLOSEOUT 和 PRODUCTION_CLOSEOUT 均未在本票产生，继续按外部权威事实失败关闭。

## 可观察行为

- `Source` 按机构计数；两个 `SourceStream` 可以归属同一机构而不会虚增机构数。
- 研究 disposition、Owner 意图、SourceAdmission 和 runtime event 是四类不同的追加式事实；研究记录不参与影子授权 SQL。
- SourceAdmission 是逐流、限时的服务端决定。十项门禁任一为未知或失败均记录 `PAUSE`；`ADMIT` 受到数据库完整性约束，不能携带缺失/失败门禁。
- `authorize_source_stream_shadow_v2` 和 `start_source_stream_shadow_v2` 在数据库内复核当前流、Owner 意图、人工停用、准入结论和有效期。Owner 在授权后撤权时，开始运行失败关闭。
- 受控 collector 只实现统一 `SourceAdapter`；发现前和抓取前复核授权。HTML、PDF、RSS 均先保存 raw bytes，再按实际 MIME 建立文档并只交接 DocumentVersion ID。
- 不支持 MIME 或解析失败只追加失败事实并保留 raw；撤权不产生 raw、DocumentVersion 或下游 handoff。
- 下游继续复用 T01 的 DirectRelevance/锁定负例门禁、T04 的 AcceptedClaims/SourceExcerpt 内容准备和 T05 的 `PublicationService` FULL/R3/404 投影，没有新增 Event、claim 或发布写入口。
- 指标只使用 `phase/outcome` 与 `outcome/document_kind` 低基数标签；URL、正文、source ID 和 stream ID 不进入指标标签。

## TDD 证据

RED 阶段：

- `test_t07_controlled_source_stream.py` 和 `test_t07_shadow_raw_first.py` 首次运行因模块不存在在收集阶段失败。
- `test_0042_t07_controlled_stream_migration.py` 首次运行因 migration 不存在且 Alembic head 未推进而失败。
- `test_t07_controlled_stream_repository.py` 首次运行因 PostgreSQL repository 不存在而失败。

GREEN 阶段：

```text
pytest T07 unit/infrastructure: 35 passed
make t07-source-shadow-test: 39 passed
T07 migration replay: 0041 -> 0042 -> 0041 -> 0042
```

最终门禁：

```text
make lint: PASS
make typecheck: PASS (mypy strict + Vue/Nuxt + generated contracts)
make test: PASS (Python 1207 passed, 27 conditional skips; UI 53 passed; Web 94 passed)
make contract-test: PASS (generated contracts reproducible; 105 passed)
make security-check: PASS (pip/pnpm audit clean; Trivy HIGH/CRITICAL clean)
make fixture-replay: PASS (355 passed; deterministic mock evaluation passed)
make quality-gate: PASS
```

本票未修改正式前端，故 `make web-e2e` 与 `make web-a11y` 不属于 T07 适用门禁。上述 27 个 skip 均为仓库既有、依赖外部隔离环境的条件性测试；本票未增加 skip。

## 诚实边界

- 测试中的 `ADMIT`、source/stream、HTML/PDF/RSS 和运行事件只存在于一次性隔离数据库或内存 fake，不能作为真实来源准入或真实采集证据。
- 未创建、补写或宣称 `HUMAN_OWNER` Gold、DeepSeek 成功、AIAvailability、来源观察时长、运行窗口或 closeout GO。
- 未降低 precision/recall、Feed precision、R3/R4、PublicationService、robots、版权、公网安全、重定向、预算、限速和熔断门槛；未增加 skip、删除断言或吞掉失败。
