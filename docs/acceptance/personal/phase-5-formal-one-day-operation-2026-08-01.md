# 第五阶段：正式平台第一条资讯和一个工作日稳定运行

日期：2026-08-01 起

状态：`IN_PROGRESS`。本记录当前只固定基线、正式库差异和运行门禁；正式迁移、第一条资讯、八小时运行和最终 `make check-live` 尚未完成，不得据此声称 Phase 5 PASS。

## 冻结基线

- 上一阶段分支：`codex/phase-4-real-event-acceptance`
- 第四阶段真实运行代码 SHA：`9250862f9d09b873296779558ee3bc27f65e0523`
- 第四阶段同 SHA CI：GitHub Actions `30696040807`
- 第四阶段隔离证据：`.cache/phase4-evidence/9250862f9d09b873296779558ee3bc27f65e0523-2e2bb612461b.json`
- 被排除的纯文档 SHA：`e316fb2ada3e883a66fe5f52708c2aa800452439`
- 第五阶段分支：`codex/phase-5-formal-one-day-operation`，从上述 `9250862` 精确创建。

## 正式库前置审计

容器标签和挂载确认 `srbg-intelligence-postgres-1` 是正式 PostgreSQL：Compose project 为 `srbg-intelligence`，数据挂载为 `/mnt/host/wsl/SRBGDataDisk/srv/postgres`；`srbg-issue40-postgres-1` 使用独立 `/issue40/srv/postgres`，只用于隔离测试。

正式库实际 revision 为 `0055_crossref_metadata_admission`，不是旧运行文档记录的 `0054_policy_optimization`。它来自独立 Phase 2C sibling 分支，正式库中保留：

- connector definition `019f2c00-0000-7000-8000-000000000001`：1 条；
- `stream_config_version.admission_research_id IS NOT NULL`：1 条；
- `fk_stream_config_admission_research`、`ck_stream_config_exactly_one_provenance` 和对应索引均存在。

当前 Phase 3/4 权威线则为 `0054 -> 0055_phase3_trustworthy_event -> 0056_phase4_controlled_handoff`。直接升级会因未知 sibling revision 失败；手改 `alembic_version`、正式 destructive downgrade 或丢弃 Crossref provenance 均不允许。

最小前向修复使用一个无 DDL/seed 的历史兼容锚点识别已经应用的 sibling，再由 `0057_phase5_formal_reconciliation` 汇合两个 parent。`0057` 只规范化并保留正式库已有 provenance 列、外键、XOR 约束和索引；不复制 Phase 2C connector migration，不 cherry-pick，不把该旧 connector 作为本轮第二来源。正式 legacy row 会阻断 destructive downgrade，主回滚为应用回退和本轮新备份恢复。

隔离验证已覆盖：

- 干净 `0054 -> 0057 -> 0054`；
- 重建 `0055_crossref_metadata_admission -> 0057`；
- `0057` 单一 head；
- Phase 3 automatic publication authority、Phase 4 controlled-run handoff、旧 Crossref provenance schema 同时存在；
- 一次性 PostgreSQL/MinIO 资源完成后删除。

## 正式运行边界

计划只运行现有 `RES-004`（中国公路学报）下一个经第四阶段研究和真实抓取证明的 CJHT SourceStream，内容类型限定为低风险 `INDUSTRY_UPDATE`。所有其他来源在窗口内不得产生 `fetch_run`。

运行使用完整 `make dev` profile 和现有 `personal_controlled_run` 权威预算/截止边界：

- 窗口：至少 8 小时；
- 请求上限：当前正式策略固定 80；
- 字节上限：150 MiB；单响应上限 50 MiB；
- AI 上限：当前正式策略固定 1,250,000 micro-USD；
- SourceStream 继续使用既有 1 request/minute、SSRF/robots/条款/熔断门禁；
- 到期后先关闭 Owner 来源意图并停止调度，再排空请求、fetch、content outbox、AI、预算 reservation 和发布投影工作。

最终 `phase5-formal-one-day` profile 只读复核正式 PostgreSQL 和回环接口，并读取 append-only 周期样本。它要求：revision 精确为 `0057_phase5_formal_reconciliation`、当前固定预算逐项一致、8 小时覆盖且采样间隔不超过 30 分钟、恰好一个 run source 且只产生目标 SourceStream 的 fetch、其他来源 fetch 为零、发布内容仅为 R1/R2 `INDUSTRY_UPDATE`、至少一条发现/抓取/解析/AI 成功/发布、accepted claims 与 evidence links 可追溯、零重复、零静默失败、零永久悬挂、所有未发布版本有非空 reason codes、费用不超正式上限、Worker 重启后的启动时间变化及恢复、`/all`、`/api/v2/feed` 和 Event 详情均实际包含该 Event。快照 SQL 已在一次性 0057 PostgreSQL 上编译执行，不以字符串或 mock 替代 schema 验证。

## transfer 与运行模式决策（待真实窗口收口）

- `fb86580`：当前 0051 technical exception/retry 已覆盖 current-gate recheck、幂等和审计核心语义；不移植旧 generic replay。
- `dd5923a`：当前 controlled-run 截止、预算 reservation、来源关闭和队列/数据库排空足以先执行单来源窗口；最终以真实停止/排空证据决定是否需要产品化增量，不复制旧 migration。
- `d1d9f25`：本轮使用既有 PostgreSQL 状态、Prometheus/容器状态和只读验收 profile，不先做 operations dashboard；最终按真实观测缺口决定。
- `8d4d1e0`：不移植。`make dev-lite` recipe 和 12 容器语义未修改。
- `make dev-content`：尚无资源测量证据，不实现；先使用完整 `make dev`。

## 当前门禁与待办

- migration focused tests：PASS；
- sibling 与 fresh 路径一次性 PostgreSQL replay：PASS；
- `make check-fast`：PASS（1172 passed / 26 个既有条件 skip；mypy 139 files）；
- `make check-pr`：PASS（1543 passed / 27 个既有条件 skip；UI 53、Web 106、隔离集成 14、Phase 5 migration/SQL 21）；
- 冻结候选、唯一一次 `make check-release`、同 SHA 远端 CI：待完成；
- 新正式备份及隔离恢复：待完成；
- 正式迁移、第一条资讯、八小时运行、重启恢复和最终唯一一次 `make check-live`：待完成。
