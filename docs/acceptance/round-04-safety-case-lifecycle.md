# Round 04 安全案例生命周期验收记录

- 日期：2026-07-14
- 场景：同一安全事故从初报、续报、正式调查、处罚/追责到整改评估的事件化展示与审计
- 固定案例：梅大高速茶阳路段“5·1”塌方灾害公开官方材料离线副本
- 发布入口：唯一 `PublicationService`，publication gate `4.0.0`

## 用户场景、范围与复用

安全人员在同一个 `/safety` 信息流切换“规定 / 案例”，能够识别尚在调查的事故，进入事件详情查看初报、续报、正式调查、追责和整改时间线；已由有权审核人接受且证据充分的事实进入“已确认事实”，数字冲突、证据不足和未审核字段进入“待核实”。审核员在既有审核工作台处理事件关联候选、逐字段事实和关键字段冲突，所有决定均留下追加式审计记录。

本轮复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`、`ItemSummary`、事实/证据组件和唯一 `PublicationService`。`SafetyCaseTypeSummary` 仅扩展冻结契约；事件详情复用既有 BFF、鉴权和证据投影，没有建立第二套案例信息流、卡片、ORM 边界或发布服务。

本轮不做媒体线索自动发布、事故等级模型推断、复杂 AI 摘要、自由生成的现场操作指令或第05轮功能。相似场景和防范措施只显示受控标签；任何带操作步骤的候选都会被 publication gate 拒绝。

## 第一性原理约束

实现以以下不可再分事实作为默认拒绝边界：

1. 一次事故是事件，初报、续报、调查、处罚和整改是独立材料；材料相似不等于重复，不能被精确或近似去重删除。
2. 公开事实必须能回到当前材料、文档版本和稳定定位；模型、客户端字段或无定位自由文本都不是证据。
3. 伤亡和损失只接受 A0/A1 官方一手材料并逐字段人工审核；原因与责任还必须来自正式调查或处罚阶段。
4. 没有正式依据时原因/责任为 `null`；正式证据已经审核且明确没有对应认定时才可为 `[]`，两者不可混用。
5. 一旦同字段出现未解决冲突，普通投影必须隐藏具体值；旧值只能留在受控审计中，不能继续伪装为当前事实。
6. 生成候选不是确认关系；事件成员、事件关系、冲突取值和发布均必须由不同权限主体作出终态决定，提交人不能审批自己的案例。

## 数据迁移、数据库边界与回滚

Alembic `0005_safety_case_lifecycle` 新增 12 张事实与决定表：

- `safety_case_profile`：事故类型、工程类型、事发时间、地区、项目、主体、伤亡、损失、调查状态和阶段投影；
- `event`、`event_item_candidate`、`event_item_decision`、`event_item`：事件、五维候选、人工决定和正式成员；
- `event_relation_candidate`、`event_relation_decision`、`event_relation`：后续、调查、处罚、整改、更正等关系候选与正式关系；
- `claim_field_decision`：受保护事实的逐字段接受/拒绝及证据依据；
- `claim_conflict`、`claim_conflict_decision`：关键字段冲突和 `KEEP_CURRENT / ACCEPT_CANDIDATE` 终态决定；
- `safety_case_audit_event`：更正、撤回、关系和冲突决定的追加式哈希链审计。

数据库触发器强制证据来源、事件成员资格、职责分离、决定不可变和公开投影降级；运行时角色只能读取去标识的安全视图，发布写入仍由专用角色和唯一服务完成。R4 或未发布材料不能通过事件聚合泄漏标题、身份、状态、关系、Claim ID 或证据定位。

真实隔离 PostgreSQL 回放结果：

```text
0004_pdf_ocr_versioning → 0005_safety_case_lifecycle
0005_safety_case_lifecycle → 0004_pdf_ocr_versioning
0004_pdf_ocr_versioning → 0005_safety_case_lifecycle
最终 alembic_version = 0005_safety_case_lifecycle
Round04 关键表、视图、触发器和权限抽查通过
```

降级/再升级只在随机命名的空临时数据库执行。生产回滚采用回退应用镜像、停止 Round04 写入并保留事实/审计表的策略；不得用实验室降级删除生产历史。

## 事件关联与冲突规则

事件关联候选由服务端按日期、地区、项目、主体和事故类型五个独立维度计算，保存每维结果、总分与规则版本。达到阈值只写 `PENDING_REVIEW` 候选；低于阈值不落库，任何路径都不能由候选直接生成 `event_item`。首个材料可以进入空的临时事件，已有未决定提案不能被后续材料当作已确认成员参与自匹配。

同一事故各阶段均保留独立 `intelligence_item` 与内容哈希。人工确认后建立：

```text
初报 → FOLLOW_UP → 续报
事件 → INVESTIGATES → 正式调查
事件 → PENALIZES → 追责/处罚
事件 → RECTIFIES → 整改评估
较早事实 → CORRECTS → 后续正式事实
```

伤亡数字发生冲突时立即创建人工队列并隐藏普通投影。固定演示先处理 `24 → 48` 为 `KEEP_CURRENT`，验证落选候选不会进入发布门禁或后续冲突基线；再处理正式调查的 `52` 为 `ACCEPT_CANDIDATE`，验证当前事实更新为正式结论且历史材料仍可审计。撤回材料不再参与事件头部事实聚合，后续有效材料能够替代较早事实而不改写历史。

## 证据与发布门禁

受保护字段的 Claim 必须同时绑定来源、原始 URL、采集记录、文档版本、正文哈希和 HTML 段落或 PDF 页/文本块定位。`official_direct_causes` 与 `responsible_entities` 仅接受 A0/A1 的 `FINAL_INVESTIGATION` 或 `ENFORCEMENT` 正式证据；媒体推测、初报和续报即使有文字也不能写入这些字段。

`PublicationService` 在提交时重新读取数据库权威上下文，逐项验证：

- 材料已由人工确认属于事件，来源有效且不是 R4 隔离内容；
- 事故类型、工程类型、时间、地区、项目和主体等元数据均来自本材料已接受 Claim；
- 伤亡、损失、原因和责任具有本字段终态审核、合格来源等级与稳定定位；
- 不存在未解决关键字段冲突、失效/撤回证据或落选 Claim；
- 提交人与审核人分离，R3 精选有明确审核者与发布审计；
- 受控标签来自词表，不含自由生成的现场操作指令。

门禁任一事实缺失即拒绝，并按原因输出结构化日志和 `srbg_publication_gate_denials_total{reason}`，客户端不能用完整发布对象或自报状态绕过。

## API、契约与 UI 纵向切片

保留 `/api/v1/feed`、`/api/v1/items/{item_id}` 和既有 `FeedPage`/`ItemSummary`，增量提供：

```http
GET  /api/v1/events/{event_id}
POST /api/v1/admin/events/{event_id}/candidate-items/{item_id}
GET  /api/v1/admin/claim-conflicts
POST /api/v1/admin/review-candidates/EVENT_LINK/{candidate_id}/decisions
POST /api/v1/admin/review-candidates/EVENT_RELATION/{candidate_id}/decisions
POST /api/v1/admin/review-candidates/CLAIM/{candidate_id}/decisions
POST /api/v1/admin/claim-conflicts/{conflict_id}/decisions
```

同一 `/safety` 页面增加“规定 / 案例”筛选和 SafetyCase 类型汇总；`IntelligenceCard` 以文字、图标和语义色显示“调查中 / 正式调查 / 整改 / 有冲突”，不依赖颜色传意。`/events/{id}` 组合 `EventTimeline`、已确认事实、待核实事实、受控标签和已审核关系；审核页组合 `ClaimConflictPanel`，只向 reviewer 显示完成决定所需的候选、证据和审计信息。

普通用户看不到冲突候选值、落选 Claim、审核人标识或受限证据定位。浏览器响应已经由服务端白名单投影裁剪，不是收到完整对象后再用 CSS 隐藏。

## 固定官方样本 E2E

`apps/api/tests/fixtures/round04/round04-official-manifest.json` 将 6 份公开官方响应锁定为不可变离线测试材料，逐项保存来源 URL、来源代码、权威等级、MIME、字节数和 SHA-256；测试从不联网刷新：

| 阶段 | 固定材料 | 预期事实 |
|---|---|---|
| 初报 | 大埔县政府 HTML | 20 辆车、54 人、24 人死亡、30 人受伤 |
| 续报 | 大埔县政府新闻发布会 HTML | 23 辆车、48 人死亡、3 人待 DNA 确认、30 人受伤 |
| 正式调查 | 广东省应急管理厅落地页和 31 页 PDF | 52 人死亡、30 人受伤、正式原因依据 |
| 追责 | 广东省纪委监委 HTML | 4 个责任单位、32 名公职人员被问责 |
| 整改 | 广东省应急管理厅 HTML | 整改评估完成，但仍有未完成问题 |

真实纵向集成完成：原始材料校验与持久化、独立阶段材料、五维候选、人工成员确认、逐字段审核、冲突决定、正式关系、唯一服务发布、普通 Feed/详情/事件投影、撤回与更正审计。所有 R3 精选均有不同于提交人的审核人；同一事故各阶段没有被精确或近似去重删除。

## 指标、运行与冷启动

`/metrics` 只允许 `PLATFORM_ADMIN` 或 `AUDITOR` 读取，匿名 `/healthz` 与 `/readyz` 保持可用。Round04 输出待审核事件候选、待审核关键 Claim、按阶段/调查状态统计的案例量、按字段统计的待处理冲突，以及既有发布拒绝原因指标。

Web 镜像采用两阶段构建：构建阶段执行 Nuxt build，运行阶段只复制 `.output` 并以 Nitro production server 启动。这样首次访问审核动态路由不再等待 Vite 冷转换；无全局预热、无重试、无放宽超时。无缓存重建并强制重建容器后，第一轮 `make web-e2e` 即通过。

## 最终门禁

本轮最终顺序覆盖 `make fixture-replay`、真实 OCR/PDF 门禁、Round02 安全规定集成、Round04 安全案例集成、完整质量门禁、浏览器主路径和 axe：

| 门禁 | 结果 |
|---|---|
| `make fixture-replay` | 75/75 通过 |
| `make pdf-ocr-test` | 真实 OCR 3/3 页可用；23 通过、1 跳过 |
| `make safety-regulation-test` | 真实 PostgreSQL/MinIO 生命周期与 RBAC 3/3 通过 |
| `make safety-case-test` | 官方五阶段纵向切片 5/5 通过；实际执行 `0004 → 0005 → 0004 → 0005` |
| `make quality-gate` | Ruff、设计令牌、ESLint、mypy strict 56 个源码文件、Vue/TS 契约全部通过；Python 288 通过/7 跳过，UI 53/53，Web 单测 44/44，契约 38/38；pip-audit 无外部已知漏洞，pnpm 仅 1 个 low，Trivy HIGH/CRITICAL 为 0 |
| `make web-e2e` | Chromium 33/33 通过，含规定/案例筛选、事件时间线、调查中、已确认/待核实、冲突决定、关系和普通投影隔离 |
| `make web-a11y` | axe 7/7 通过，所有 `violations=[]` |
| `git diff --check` | 退出 0 |

硬性测试结论：同事故不同阶段全部保留；媒体推测不能进入 `official_direct_causes`；无正式调查依据时责任为 `null`；伤亡冲突进入人工队列；未结案显著显示“调查中”；提交人不能审批自己的安全案例。

## 已知限制

- 固定样本的正式调查材料才包含精确事发时间，因此演示数据中的部分早期候选日期维度为 0；Asia/Shanghai 日期边界和日期命中由独立单元测试覆盖，平台没有为提高分值补造时间。
- 固定样本同时保存行政区划代码 `441422` 和官方文本中的“广东省”，粒度不同但不互相推断；更细层级标准化留给后续数据治理。
- 数据库已强制版本、来源、正文哈希和定位证据一致；`claim_evidence.original_url` 尚未通过数据库触发器与文档 URL 做逐字绑定，服务门禁仍会校验该来源上下文。
- reviewer 的事件关系契约仍包含审核者 UUID 供受控审计，普通页面 DOM 不显示；后续可进一步拆分最小化审计 DTO。
- Round04 页面沿用共享 AppShell/EvidenceDrawer 的键盘焦点测试，本轮新增页面由 axe 与主路径行为测试覆盖，尚未增加独立的冲突面板焦点归还专项用例。
