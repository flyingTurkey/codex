# 土木工程情报 v2 工程基线收口验收

日期：2026-07-20
分支：`codex/round-10-feed-search-daily`
父规格：GitHub Issue #1（保持开放）
结论：工程基线可提交；本记录不是来源准入、真实运行或任何 GO 证据。

## 1. 收口边界

本轮只收口工作区中已经完成的纵向切片、研究票及父规格前置工程基线，不实现新功能，不启动 #14、#34、#35、#36，不访问真实 AI，不执行公网采集，也不改变任何来源的意图或实际运行状态。

所有 SourceStream 研究清单继续保持 `desired_enabled=false`、`source_admission=null`、`actual_running=false`；研究态 `ADMISSION_READY` 只表示可以进入后续独立准入票，不构成 SourceAdmission、覆盖信用、PAUSE 或运行授权。

## 2. 文件级归属映射

| Issues | 已完成能力 | 主要文件范围与验收记录 |
| --- | --- | --- |
| #2 | T01 领域分类、结构化语料与资格评估 | `intelligence_v2/qualification.py`、`structural_corpus.py`、资格 Schema/脚本/测试；`t01-intelligence-qualification.md` |
| #3 | T02 Owner Gold pilot 与既有校准基线 | `0038_owner_gold_calibration.py`、`gold_calibration.py`、校准 Schema/脚本/测试；`t02-owner-gold-calibration.md`。仓库只含 Schema、fixture 和聚合结论，不含 Owner 私有标注或 reviewed artifact |
| #4 | 首页搜索与既有 Owner 阅读入口 | `GlobalSearch.vue`、首页/搜索页、v2 API/契约及 E2E；`issue-4-home-search.md`。Issue 已关闭，本轮只做基线复验 |
| #5 | T04 证据优先内容候选准备 | `0039_t04_content_candidates.py`、`content_candidate_*`、候选契约/测试；`t04-evidence-content-preparation.md` |
| #6 | T05 `PublicationService` 统一发布门禁和 Reader 投影 | `0040_t05_reader_projection.py`、publication/v2 service、契约、迁移与集成测试；`t05-reader-publication-projection.md` |
| #7 | T06 AI 七态与证据约束投影 | `0041_t06_ai_runtime_projection.py`、`ai_runtime.py`、`t06_content_summary.py`、Worker/API/UI 测试；`t06-deepseek-runtime-projection.md`。仅 mock/失败关闭证据，不含真实 DeepSeek 成功 |
| #8 | T07 受控 SourceStream shadow/raw-first 边界 | `0042_t07_controlled_stream.py`、`controlled_stream.py`、`controlled_shadow.py` 及测试；`t07-controlled-source-shadow.md`。未授予准入且未运行来源 |
| #9 | T08 搜索、Feed 与证据卡 | v2 search/feed service、契约、卡片/页面与测试；`t08-evidence-search-feed-card.md` |
| #10 | T09 服务端派生热点 | `0043_t09_hotspot_awards.py`、热点契约/测试；`t09-permanent-hotspot-awards.md` |
| #11 | T10 Owner Reader B | `events/[id].vue`、`ReaderActions.vue`、受约束原型与 E2E；`t10-owner-reader-b.md`。原型不是生产依赖 |
| #12 | T11 ReaderAppendix | `0044_t11_reader_appendix.py`、appendix service/contract/component/测试；`t11-reader-appendix.md` |
| #13 | T12 许可媒体安全交付 | `0045_t12_media_delivery.py`、media repository/service/契约/测试；`t12-licensed-media-delivery.md` |
| #15/#17/#19/#24/#26/#28 | T14/T16/T18/T23/T25/T27 已关闭 SourceStream discovery | `source_stream_discovery*`、对应 validation 清单/Schema、`docs/research/`、基础设施测试和同名验收记录 |
| #21/#30/#32 | T20/T29/T31 已关闭且被替代的研究证据 | 原研究清单、报告、测试和验收记录原样保留为 `SUPERSEDED`/阻断证据，不伪装为准入通过 |
| #37/#38/#39 | T20R/T31R/T29R 已关闭替代研究 | 替代 validation 清单/Schema、报告、测试及验收记录；仍为 disabled 研究输入 |
| Spec #1 前置基线 | 0037 campaign、总体 closeout 与三份 handoff | `0037_engineering_closeout_campaign.py`、campaign 领域/脚本/测试、`intelligence-quality-reader-v2.md`、三份 `docs/srbg-intelligence-v2-*-handoff-2026-07-19.md`。这些材料不关闭父规格，也不构成 ENGINEERING/PRODUCTION GO |

共享改动如 `AGENTS.md`、Context、ADR、README、contracts 生成器、observability、环境示例、`Makefile` 和 `CHANGELOG.md` 均服务于上述已完成切片的共同约束、契约或门禁，不包含 #14/#36 新实现。

## 3. 安全与隐私复核

- 对全部 tracked 修改与 untracked 候选执行凭据、私钥、Token、Cookie、密码赋值和大文件扫描；未发现可提交凭据或私钥，测试中的本地占位密码不具备外部权限。
- `HUMAN_OWNER` 只出现在版本化 Schema、测试 fixture、程序枚举和聚合验收结论中；没有 Owner 私有正文、逐条标注、reviewed artifact 或真实个人信息进入仓库。
- `GO` 命中均为 `NO_GO`、失败关闭断言或文档边界；未产生 Owner Gold 生产校准、真实 DeepSeek Schema 成功、SourceAdmission、真实采集窗口、ENGINEERING GO 或 PRODUCTION GO。
- 来源运行字段的唯一正向用例是测试 fixture；所有研究清单继续显式 disabled，未启动 scheduler、source worker、source-discovery 或真实来源。
- Trivy 以 HIGH/CRITICAL 阈值扫描仓库快照通过；对象存储、R3/R4、PublicationService、robots、版权与公网地址安全边界均未降低。

## 4. 门禁结果

- `make quality-gate`：通过；Python `1346 passed, 27 skipped`（既有受控 skips），UI `53 passed`，Web unit `101 passed`，contracts `109 passed`；Ruff、mypy strict、TypeScript strict、契约再生成、pip/pnpm audit 与 Trivy 均通过。
- `make fixture-replay`：通过，`357 passed`；round09 使用 `provider=mock`、`cost_microusd=0`，证据/Schema 覆盖 100%，unsupported expansion 0。
- T05/T06/T07/T08/T09/T11/T12 定向纵向目标：全部通过；迁移均完成升级、回滚、再升级回放。T05 为 18 passed，T06 为 33 passed + Web 101，T07 为 39 passed，T08 为 17 passed + Web 101，T09 为 20 passed，T11 为 10 passed + ReaderAppendix 3，T12 为 36 passed。
- discovery 定向测试：T14/T16/T18/T20/T20R/T23/T25/T27/T29/T29R/T31/T31R 全部通过；没有公网访问或来源运行。
- 全新隔离正式栈：只启动 PostgreSQL、Redis、MinIO、隔离锚存储、ClamAV、迁移/角色初始化、API 与 Web；显式禁用 source discovery、Baidu/semantic 外部搜索和真实 AI。Playwright E2E `74 passed`，a11y `21 passed`。
- Nuxt-only 本地试跑的 9 个 SSR 失败由缺少回环 API/Owner 身份导致，不作为权威门禁；隔离正式栈已全部通过。

门禁回放发现并修复三项已授权切片内回归：T05/T09 迁移验证器在完成各自往返断言后将累计集成场景数据库升级到 head；`.dockerignore` 放行 T06 运行时必需的 `summarize-v2-output.schema.json`。未删除断言、降低阈值、新增 skip 或吞异常。

## 5. Issue #4

Issue #4 已于 2026-07-20 关闭，已有实现、验收记录及 `74 E2E / 21 a11y` 评论，本轮不 reopen、不重复关闭。基线提交后只追加一次 follow-up 评论，引用本记录、最新门禁结果和提交哈希。

## 6. 明确保留的未闭环事项

- Spec #1 继续开放；#14、#34、#35、#36 等后续票未启动。
- ADR-0003 仍保留早期生产阈值，而 Spec #1 已采用 40 条、90 分钟、2 小时、50 条的新门槛；本轮不以基线修复名义启动 #36，留待独立文档闭环。
- 未产生 Owner Gold 生产校准、真实 DeepSeek 成功、真实准入/采集、覆盖信用或任何 GO。
- 所有研究态来源继续 disabled、`desired_enabled=false`、无 SourceAdmission、无实际运行。
