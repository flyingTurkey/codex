# Round 03 PDF、OCR 与版本变化验收记录

- 日期：2026-07-14
- 范围：已准入安全规定来源的 PDF、公开附件、OCR、页码证据和版本生命周期
- 固定演示：测试专用 v1、仅元数据/重复页眉变化 v2、实质修订 v3、明确撤回证据
- 发布入口：唯一 `PublicationService`，publication gate `3.0.0`

## 用户场景、复用与边界

已准入来源发布 PDF 或附件后，平台先将原始字节写入私有对象存储，再执行 MIME、ClamAV、PDF 结构、主动内容和附件预算检查。安全文档进入原生文本提取或 OCR，形成稳定的页码、文本块、表格单元格、旋转归一坐标和置信度证据。审核员在既有详情与审核工作台查看页面高亮、版本时间线及词级差异，并人工确认 `AMENDS`、`SUPERSEDES`、法规状态和撤回证据；普通用户只看到与当前投影相符的“已更新 / 待复核 / 已撤回 / 原文失效”。

本轮复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`EvidenceDrawer`、`FeedPage`、`ItemSummary` 和唯一 `PublicationService`。没有创建 PDF 专属法规卡、平行详情页或第二条发布链路。

本轮不做事故生命周期、语义去重、真实 LLM、全文表格编辑器、浏览器加载原始 PDF、PDF 内嵌附件解析或普通用户原文件下载。原文失效仅表示连续访问失败，不自动推断撤回或废止。

## 数据、状态与迁移

Alembic `0004_pdf_ocr_versioning` 在既有不可变事实上增量增加：

- `raw_object_security_fact`：追加式 `CLEAN / QUARANTINED / REJECTED` 扫描事实、检测 MIME、规则版本和原因。
- `document_version_state_event`：`RECEIVED → SECURITY_PASSED → PARSING → [OCR_PENDING → OCR_COMPLETE] → READY`，异常终态为 `QUARANTINED / FAILED`；只有完整持久化成功的 `READY` 才提升为当前版本。
- `document_page`、`document_text_block`、`document_table_cell`：页码从 1 开始，坐标为旋转归一后的整数千分之一 point，保存阅读顺序、原生/OCR 来源、置信度基点、文本哈希和表格跨格。
- `document_attachment` 增量树字段：根附件与一层 ZIP 子项通过 `parent_attachment_id` 关联，保存规范化路径、深度、声明/检测 MIME、大小和安全状态。
- `version_change` 与追加式状态事件：自动检测仅形成 `INITIAL / METADATA_ONLY / CONTENT_UPDATE`；`CORRECTION / AMENDMENT / REPLACEMENT / WITHDRAWAL` 由审核决定形成。
- 关系候选、正式关系与法规状态决定分离：正式文档关系只允许 `AMENDS / SUPERSEDES`；`REPEALED` 只属于法规状态，必须有一手官方证据和有权审核决定。
- Claim、证据、摘要和发布修订通过 `content_lifecycle_event` 表达 `ACTIVE → UPDATE_DETECTED → RE_REVIEW_PENDING → SUPERSEDED / WITHDRAWN`，历史对象不被改写。
- parser 写处理事实与 Outbox，publisher 以发布专用数据库角色消费 Outbox；解析角色没有发布修订或生命周期写权限。

已在独立临时 PostgreSQL 数据库实际执行：

```text
空库 → 0003_safety_publication
0003_safety_publication → 0004_pdf_ocr_versioning
0004_pdf_ocr_versioning → 0003_safety_publication
0003_safety_publication → 0004_pdf_ocr_versioning
最终 alembic_version = 0004_pdf_ocr_versioning
Round03 关键表抽查 = 4/4
```

生产回滚默认回退应用镜像并停用相关连接器/任务队列，保留 `0004` 的向前兼容表、原始对象、证据和追加式历史；不得在生产执行会删除 Round03 表的实验室降级命令。降级/再升级仅用于空的临时验收数据库。

## 安全、解析与变化规则

固定默认预算为：单文件 50 MiB、PDF 1000 页、最多 OCR 200 页、ZIP 100 项、总解压 200 MiB、压缩比 100:1、单页渲染 4000 万像素。ZIP 只展开一层，只接受白名单 HTML/PDF；任一子项不安全会隔离整个归档，不部分接收。

PDF 检查拒绝加密、JavaScript、OpenAction、Additional Actions、Launch/自动外链、内嵌文件、错误 MIME 和超预算页面。扫描页通过本地 Tesseract `chi_sim+eng`，词级结果保留框与置信度；关键字段 OCR 置信度低于 `0.95` 时 publication gate 拒绝发布。OCR 可用页定义为至少 10 个非空白字符且词置信度中位数不低于 `0.80`。

归一化使用 Unicode NFC、空白/换行归一、零宽字符移除、软连字符及断行连词合并和稳定阅读顺序。原始字节、归一化全文、语义正文和元数据分别保存 SHA-256。顶/底 10% 中至少跨 3 页且覆盖 60% 页面的重复行保留为证据块，但不进入语义正文哈希。

仅页眉/页脚或 PDF 元数据变化为 `METADATA_ONLY`。普通正文词变化达到 `0.5%` 或累计 10 词为实质变化；文号、发布日期、实施日期、数字/日期、法规效力词和否定词变化无条件实质触发。审核员只能把非实质变化升级为实质变化，不能降低硬规则命中。

## API 与投影契约

保持 `/api/v1` 和内容 Schema `1.0.0`。`ItemSummary` 只新增可选 `document_states` 和版本历史提示；`EvidenceView.locator` 使用 `HTML_PARAGRAPH | PDF_TEXT | PDF_OCR | PDF_TABLE_CELL` 判别并兼容旧 HTML 字段。

主要端点：

```http
GET /api/v1/items/{item_id}/versions
GET /api/v1/items/{item_id}/diff?from={version_id}&to={version_id}
GET /api/v1/document-versions/{version_id}/pages/{page_number}
GET /api/v1/document-versions/{version_id}/pages/{page_number}/preview
POST /api/v1/admin/review-candidates/{RELATION|REGULATION_STATUS}/{candidate_id}/decisions
POST /api/v1/admin/version-changes/{version_change_id}/escalations
```

页面预览返回服务端生成的私有 PNG、SHA-256 ETag 和短缓存头；服务端按角色与 R3/R4 策略决定是否返回页面、Claim、证据和预览。普通 R3 响应不包含受限结论。撤回后的普通当前详情只保留标题、来源、时间和撤回原因/时间；历史修订需显式进入并显示“已失效、不可作为当前依据”。

## 固定样本与生命周期验收

`apps/api/tests/fixtures/round03/round03-golden-manifest.json` 将所有样本标记为“TEST ONLY - none of these artifacts is a real regulation”，并锁定解码后 SHA-256、字节数、声明 MIME 和预期结果。固定文件覆盖：

- v1 `READY_INITIAL`、v2 `METADATA_ONLY`、v3 `CONTENT_UPDATE` 和官方撤回证据；
- 普通文本 PDF、扫描 PDF、原生表格、错误 MIME、主动动作和超像素页；
- 正常一层 ZIP 与压缩炸弹；路径穿越、符号链接、加密项、规范化重名、嵌套 ZIP、未知 MIME、内嵌文件等由确定性单元样本覆盖。

实际纵向集成验证：

1. v1 经扫描、原生解析与证据持久化成为当前 `READY`；同版本重放不产生重复页面、块或证据，页码、坐标和文本哈希稳定。
2. v2 仅改变元数据/重复页眉，生成 `METADATA_ONLY → NO_REVIEW_REQUIRED`；只有证据文本唯一重锚且页码/坐标稳定才自动形成派生 Claim/Evidence。
3. v3 改变正文、文号和实施日期，生成 `CONTENT_UPDATE → RE_REVIEW_PENDING`，同一业务事件写审核任务和 Outbox；旧 Claim、摘要和发布修订失效，普通投影立即降级。
4. 明确一手官方撤回证据经 reviewer 决定后由 `PublicationService` 撤回；当前投影最小化，历史修订仍保留。
5. 安全 ZIP 持久化根/子附件树；压缩炸弹形成隔离版本，既有 `READY` 当前版本不被替换。
6. `AMENDS / SUPERSEDES` 只先形成候选；未解析目标不得生成正式关系或支撑法规状态/摘要。`REPEALED` 和撤回均不能由解析器、客户端或模型直接生效。

## UI、键盘与截图

`IntelligenceCard` 在既有卡片上增量显示“已更新 / 待复核 / 已撤回 / 原文失效”，状态使用图标、文字和语义色，不依赖颜色传意。`EvidenceDrawer` 继续复用 `ResponsiveDrawer` 与 `FocusTrap`，内部组合：

- `PdfEvidenceViewer`：144 DPI 有界 PNG、页码选择、上一页/下一页、缩放和坐标高亮；浏览器不加载原始 PDF。
- `VersionTimeline`：v1、v2、v3、撤回/失效和审核状态。
- `DiffView`：按页/文本块组织词级增删，并区分页眉、元数据、关键字段和正文。

已验证 Tab 焦点陷阱、Esc 关闭并归还触发点、页码跳转和差异跳转；axe 对主页、移动抽屉、安全规定证据抽屉和来源管理页均返回空违规数组。

验收截图：

- [PDF 页码高亮](assets/round-03-pdf-highlight-1920x1080.png)
- [v2/v3 差异审核](assets/round-03-version-diff-1440x900.png)
- [撤回当前投影](assets/round-03-withdrawn-1024x768.png)
- [移动端证据抽屉](assets/round-03-mobile-drawer-768x1024.png)

对应 Playwright 视觉基线位于 `apps/web/tests/e2e/visual-baselines/round03-*.png`，覆盖 1920×1080、1440×900、1024×768 和 768×1024。

## 指标与运行

`GET /metrics` 从持久化处理事实输出：

- `srbg_pdf_parse_success_ratio`、`srbg_pdf_parse_total`、`srbg_pdf_parse_success_total`；
- `srbg_ocr_usable_ratio`、`srbg_ocr_pages_total`、`srbg_ocr_usable_pages_total`；
- `srbg_ocr_low_confidence_critical_fields`；
- `srbg_version_changes_total{change_type,material}`；
- `srbg_publisher_outbox_depth`、`srbg_publisher_outbox_oldest_seconds`、`srbg_publisher_outbox_retries_total`。

parser 和 publisher 使用独立 Celery 队列；Python 运行镜像固定 Tesseract、`chi_sim` 和 Noto CJK 字体，parser 以低并发、只读根文件系统、临时目录、硬超时和任务子进程回收运行。Outbox 消费幂等，失败退避重试并在达到上限后进入死信状态。

## 基线复验修复（2026-07-14）

开始 Round04 前实际重跑 Round03 关键门禁，`make safety-regulation-test` 在保留既有共享测试数据时失败：初次采集错误地把 2016 年的原文发布时间写入 `activity_at`，目标内容因此落出“最近 20 条”Feed。继续按 RED → GREEN 收紧后还发现：仅元数据版本错误推进活动时间，以及游标解码把时间和 UUID 转回字符串，真实 asyncpg keyset 查询拒绝绑定。

最小修复保持三类时间事实分离：

- 初次采集精确保留固定样本原文时间 `2016-06-03 10:28 UTC`，并令 `activity_at = first_discovered_at`；
- `METADATA_ONLY` 只推进 `updated_at`，不改变 `activity_at`；
- 实质更新使用同一个服务端 `now` 推进 `activity_at` 与 `updated_at`；
- Feed 游标保持外部 base64 契约，内部解码为原生 `datetime/UUID`，真实数据库按 `(activity_at DESC, UUIDv7 DESC)` 分页；同一活动时间的三条记录逐页无重复，夹具在 `finally` 中删除并恢复原记录时间。

两个真实集成门禁现在都通过 `scripts/run_isolated_integration.py` 创建随机命名的临时数据库、私有桶和临时 LOGIN 角色。Alembic 只迁移临时数据库，测试角色只继承既有 `srbg_api_role` / `srbg_publication_writer` 组角色；Make 目标不再运行共享 `migrate`、`role-init` 或 `minio-init`。runner 在数据库、桶或角色创建成功后才确认本轮所有权，并在测试失败、进程异常、`KeyboardInterrupt` 和清理异常路径执行清理；资源名称碰撞时不会删除非本轮资源。测试子进程会剔除共享/bootstrap 数据库与云凭据，配置对象的秘密字段不进入 `repr`。PostgreSQL 与 S3 端点默认必须为回环地址，非本机环境只有显式设置 `SRBG_ALLOW_REMOTE_INTEGRATION=1` 才允许运行。

定向与重复实测结果：

| 验证 | 结果 |
|---|---|
| runner 防破坏/防泄密单测 | 16/16 通过，相关 Ruff 通过 |
| Feed cursor 单测 | 5/5 通过，解码值为原生 `datetime/UUID` |
| `make pdf-ocr-test` | 真实 OCR 3/3 页可用；23 通过、1 跳过 |
| `make safety-regulation-test`（连续两次） | 每次 3/3 通过 |
| 共享状态前后对照 | `document=1524`、`intelligence_item=46`、`srbg-raw objects=1751`，均未变化 |
| 清理审计 | `srbg_it_*` 数据库 0、临时 LOGIN 角色 0、`srbg-it-*` 桶 0 |
| Playwright 并发回归 | 4 workers 稳定复现 28/29；固定 2 workers 后两轮均 29/29 |

隔离边界：本机 MinIO 测试仍使用 root 凭据访问随机私有桶，因此是名称与生命周期隔离，不是 IAM 权限隔离；默认回环限制用于阻止该凭据误指向远端。临时空库首次迁移可能在本机 PostgreSQL 集群创建迁移定义的共享 `NOLOGIN` 组角色，这些组角色不是测试登录凭据，不由 runner 删除，避免破坏同集群已有数据库的授权关系。

## 最终门禁

按指定顺序执行：

```text
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make pdf-ocr-test
make safety-regulation-test
make quality-gate
make web-e2e
make web-a11y
```

真实结果：

| 门禁 | 结果 |
|---|---|
| `make lint` | Ruff、设计 Token 一致性、UI/Web ESLint 全部退出 0 |
| `make typecheck` | mypy strict 50 个源码文件通过；UI/Web `vue-tsc` 与生成 TypeScript 契约通过 |
| `make test` | Python 170 通过、5 个显式集成开关跳过；UI 53 通过；Web 32 通过 |
| `make contract-test` | 22 通过；Python/JSON Schema/TypeScript 生成可重复 |
| `make security-check` | pip-audit 无已知漏洞；pnpm 只有 1 个 low；Trivy HIGH/CRITICAL 秘密与配置问题为 0 |
| `make fixture-replay` | 35 通过 |
| `make pdf-ocr-test` | 容器内真实 Tesseract OCR 3/3 页可用；PDF/OCR/安全/版本/集成 23 通过、1 跳过 |
| `make safety-regulation-test` | 真实 PostgreSQL/MinIO 生命周期与数据库 RBAC 3 通过 |
| `make quality-gate` | lint、typecheck、test、contract-test、security-check 全部退出 0 |
| `make web-e2e` | Chromium 29/29 通过，含 Round03 四断点视觉回归、页码跳转、高亮、差异、审核与焦点归还 |
| `make web-a11y` | axe 4/4 通过，所有 `violations=[]` |

Web 复验再次在本地 4 workers 下复现 1280px 用例的 `page.goto('/')` 超时。Playwright trace 显示根文档请求 30 秒内始终没有响应头或子资源，`ERR_ABORTED / frame detached` 是超时后关闭 context 的次生错误；Web/API 容器同期无重启或 OOM，API 请求持续成功。单项 1 worker 为 625ms，全量 2 workers 为 29/29；因此将本地与 CI 统一固定为 2 workers。修复后 `make web-e2e` 29/29、`make web-a11y` 4/4，通过过程中未增加 retry、未放宽超时或断言、未删除测试。

## Git 工作树

实施开始时确认的 Round02 基线为 37 个已修改项和 52 个未跟踪项。Round03 初次验收结束时 `git status --porcelain` 为 45 个已跟踪变更、94 个未跟踪入口，共 139 项；其中包含保留的 Round02 基线和本轮新增实现、契约、黄金样本、截图及验收记录。本次基线复验保留这 139 项为受保护基线，结束时为 45 个已跟踪变更、96 个未跟踪入口，共 141 项；新增入口仅为隔离 runner 及其基础设施测试。任务未清理、覆盖、暂存或提交用户工作树变更，最终 `git diff --check` 退出 0。

## 已知限制

- 生产来源连接器仍保持服务端准入与启用控制；四阶段演示使用确定性测试适配器，不代表实时官方站点可用性。
- OCR 和扫描表格只生成可审核候选，不提供全文表格编辑或自动接受关键事实。
- 浏览器只显示服务端 PNG 预览，不渲染、执行或向普通用户下载原始 PDF。
- 仅支持一层白名单 ZIP；PDF 内嵌附件直接隔离而不解析。
- 本轮没有事故生命周期、语义去重或真实 LLM；一句话摘要由固定模板 `safety-regulation-summary-1.0.0` 基于已接受 Claim 生成。
