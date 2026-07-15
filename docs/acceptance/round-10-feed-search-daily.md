# Round 10 信息流、搜索、专题与日报验收记录

- 日期：2026-07-15
- 用户场景：内部用户从精选或全部动态进入数字化/安全频道，搜索“隧道+监测预警+四川”或精确文号，打开事实与证据、收藏到私有专题并阅读当天已审核日报；reviewer 从固定快照生成草稿并经唯一发布服务发布
- 发布与日报入口：唯一 `PublicationService`
- 搜索原则：精确编号优先；trigram、中文全文和可配置语义召回只作后续增强

## 范围、复用与不做项

本轮完善既有 Feed、详情、事件和热点，新增搜索、日报、收藏、自定义专题、指纹与 Markdown 导出，统一交付 Cursor、ETag、组合筛选、ACL、快照与降级状态。列表没有新增 `/items` 或 `/events` 平行接口。

前端继续复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、冻结的 `FeedPage`/`ItemSummary`、既有详情、`FactList`、`EvidenceDrawer`、来源冲突和版本组件；搜索、收藏只把 `search_context`、保存动作和 Cursor 追加能力增量接入共享卡片与信息流。后端继续复用唯一 `PublicationService` 与既有 publication revision/projection，不存在第二套发布或详情实现。

本轮不做公网开放、复杂个性化推荐、企业微信推送、开放 API 密钥体系或 Codex Skill。站内关注是 P1，本轮未开启；可选语义召回默认关闭，未配置提供方或超时时明确降级为关键词结果。

## API、分页、缓存与 ACL

- 保留并完善 `GET /api/v1/feed?mode=selected|all`、`GET /api/v1/items/{id}`、`GET /api/v1/events/{id}`、`GET /api/v1/hot-topics`、`GET /api/v1/version`。
- 新增 `GET /api/v1/search`、`GET|POST|DELETE /api/v1/saved-items`、`GET|POST|PATCH /api/v1/collections`、`GET /api/v1/daily`、`GET /api/v1/reports/{id}`、reviewer 专用日报草稿/发布接口、`GET /api/v1/export/markdown` 和 `GET /api/v1/fingerprint`。
- Feed、搜索和收藏使用 HMAC 签名 Cursor；Cursor 绑定规范化查询、组合筛选和 ACL scope，修改条件或用户后拒绝复用。生产环境拒绝默认值或不足 32 字节的签名密钥。
- 稳定只读投影返回 ETag，`If-None-Match` 命中时返回 304；ETag 排除每次请求变化的 `generated_at`，仍包含实际资源和筛选结果。
- 收藏和专题只属于当前用户，读取收藏时重新执行当前 ACL。写入使用 `Idempotency-Key`，专题更新使用 `If-Match`；未授权用户访问 reviewer 日报接口返回 403。R3 只返回最小白名单，R4 不返回浏览器。

## 搜索与数据库

Alembic `0011_feed_search_daily` 创建 `search_projection`、`search_identifier`、日报/快照、收藏/专题和幂等记录，启用 `pg_trgm` 与 `vector` 扩展并建立 GIN/HNSW 索引。PostgreSQL 镜像固定为 17.10，并从固定 pgvector 0.8.2 多阶段复制扩展，最终以非 root `postgres` 用户运行。

编号、文号、标准号和 DOI 先规范化再精确匹配；精确结果排序最高。标题、实体和标签使用 pg_trgm，正文使用确定性中文 bigram `tsvector`；可选语义 provider 只追加低优先级候选，超时或不可用时返回 `SEMANTIC_SEARCH_DEGRADED` 通知，不覆盖精确编号命中。

搜索响应的 `search_context` 标明命中类型、字段、编号和语义状态。用户可从共享 `IntelligenceCard` 打开既有详情/证据抽屉，事实仍只来自当前 accepted claims，来源冲突、版本变化、撤回和原文失效继续走既有状态契约。

## 日报、导出与投影一致性

日报草稿在生成时锁定 publication revision、标题、摘要、原文链接、位置和 snapshot time；发布需要 reviewer 权限，并调用唯一 `PublicationService` 完成审核和发布。历史日报不因后续修订被静默改写；若当前内容已撤回，读侧显示“已撤回”文字并隐藏旧摘要，同时标记需要重新生成。

发布、修订和撤回继续在同一治理链路推进 SEARCH、CACHE、DAILY_DIGEST generation/visible 状态；Worker 只有在失效副作用成功后才确认投影事件。Markdown 导出只输出允许投影的题录、短摘要和原文链接；以 `= + - @` 等危险字符开头的单元内容增加前导单引号，防止后续粘贴或转换为 CSV/表格时执行公式。

## UI、响应式与降级状态

首页没有大幅 Hero，首屏依次提供今日重点、数据更新时间/内容指纹、异常通知和全局搜索。`/`、`/selected`、`/all`、`/digital`、`/safety` 继续共享唯一信息流；新增 `/search`、`/daily`、`/saved`，搜索和收藏通过共享 `load-more` 契约追加下一 Cursor 页。

视觉回归覆盖 1920×1080、1440×900、1024×768 和 768×1024；另验证 720px 等效 200% 阅读视口。Loading、空态、来源延迟、原文失效、撤回和无 AI 状态均有文字，不只依赖颜色；forced-colors、键盘焦点、移动抽屉和 768 搜索/日报 axe 扫描通过。

## 迁移、性能与最终门禁

随机隔离 PostgreSQL 已完成 `0010 → 0011 → 0010 → 0011`，并验证 pg_trgm/vector、索引、约束和角色权限。生产回滚策略为先停止 publisher/worker，回退应用镜像；存在日报、收藏、专题或搜索投影数据时不执行破坏性降级，保留权威业务事实。

最终门禁结果（2026-07-15）：

- `make round10-test`：26 passed；迁移正向/回滚/再正向、搜索/游标/ACL/ETag、日报/收藏/专题、唯一发布服务与投影 Worker 通过。
- `make round10-eval`：部署服务 40 次搜索，P95 31.05 ms，门槛 800 ms；条件请求 304；语义增强非必需且默认关闭。
- `make quality-gate`：通过；Python 443 passed / 8 skipped，UI 53 passed，Web 65 passed，契约 56 passed；Ruff、mypy strict、ESLint、TypeScript strict、设计令牌、可复现契约、pip-audit、pnpm high-level audit 和 Trivy HIGH/CRITICAL 全部通过。pnpm 仅报告 1 个 low。
- `make fixture-replay`：164 passed；Round09 对抗回放仍为 Schema/证据支持 100%、无证据扩写 0%、6/6 恶意样本拒绝。
- `make web-e2e`：41 passed；精确文号搜索→证据→收藏→当天日报路径、频道、视觉和既有页面回归通过。
- `make web-a11y`：12 passed；包括 768 搜索/日报在内的关键路径 axe 扫描无违规。
- `git diff --check`：最终交付前通过。
