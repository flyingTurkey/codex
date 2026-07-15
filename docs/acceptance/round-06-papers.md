# Round 06 期刊论文验收记录

- 日期：2026-07-15
- 用户场景：工程技术人员在既有 `/digital` 信息流检索论文题录，识别开放边界、研究成熟度与更正/撤稿状态，复制引用并跳转合法原文入口
- 自动化主切片：OpenAlex API
- 补充来源：Crossref DOI/更新关系；中国公路学报经批准 RSS 或固定目录样本
- 发布入口：唯一 `PublicationService`，publication gate `6.0.0`

## 范围、复用与不做项

本轮交付 `paper_profile` 全题录、DOI 优先去重、无 DOI 候选去重、OpenAlex 游标分页、Crossref 更新关系候选、论文分类、工程专业、技术标签、研究成熟度、列表/筛选/详情/相似论文、合法原文入口、题录导出和引用复制。访问级别由服务端决定为仅题录、可展示摘要或开放全文入口；前端以明确文字分区显示元数据、摘要与全文权限。

实现继续复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、`FeedPage`、`ItemSummary`、既有详情页和唯一 `PublicationService`。`PaperTypeSummary`/`PaperDetail` 只是冻结契约的增量分支，没有新增论文专用信息流、平行查询服务、第二套卡片或绕过发布门禁的后台写入。

本轮不做付费数据库抓取、引文网络可视化和自动学术评价；不把研究结论表述为工程生产应用，也不依据论文自动形成采购、施工或安全决策。知网和万方只允许授权 API 或人工题录录入，禁止绕过登录、验证码、Cookie、IP 限制和付费墙。

## 第一性原理与版权边界

1. DOI 是跨来源最稳定的论文身份，入库前去掉 URL/`doi:` 前缀并小写规范化；同一规范 DOI 只能形成一个 `paper_profile`，每个来源仍保留独立 `paper_source_record`、原始文档版本和内容哈希。
2. 无 DOI 时，规范题名、首位作者和年份只生成重复候选，不能静默合并；候选需人工审核后才形成正式关系。
3. `METADATA_ONLY` 永不投影摘要或全文地址；摘要仅在许可明确时保存和展示；开放全文也只保存许可明确的外部入口，本轮不下载论文全文、不写对象存储。
4. B1 正式期刊可支持“论文报告了什么”，不能单独证明工程落地、法规效力、事故原因或责任；卡片和详情固定显示“研究结果不代表已完成工程生产应用”。
5. `RETRACTS`、`CORRECTS`、`SUPERSEDES` 先进入关系候选，由唯一 `PublicationService` 审核落库；撤稿或更正状态在卡片和详情显著显示。
6. `source_registry.csv` 中 OpenAlex、Crossref、中国公路学报继续保持 `CANDIDATE/disabled`。固定样本、CSV 或客户端自报状态不能启用生产采集，必须通过既有来源准入服务。

## 连接器、固定响应与访问控制

OpenAlex 连接器使用 API key、可配置学术联系标识、`cursor=*` 起始游标、每页 100 条和 `next_cursor` 续传；只请求允许域名和必要字段。共享 HTTP 客户端提供明确超时、每分钟速率、有限指数退避、429/5xx `Retry-After`、条件请求、响应大小上限、重定向逐跳 SSRF 校验与熔断。Crossref 只按规范 DOI 查询并解析 `update-to`/撤稿/更正关系候选。

`apps/api/tests/fixtures/round06/` 保存脱敏、最小化且 SHA-256 锁定的 OpenAlex 两页响应、Crossref 更新关系和中国公路学报目录样本。固定响应不含摘要正文或论文全文；契约测试覆盖分页游标、Accept/User-Agent、DOI 规范化、同 DOI 双来源归一、关系映射和未授权字段不进入解析结果。

R3/R4 与未发布内容继续由服务端 ACL 投影。迁移仅给运行角色论文来源记录和候选表的必要写权限，正式 `item_relation` 只有发布角色可写。引用接口只读取已发布题录，支持 RIS、BibTeX 和 GB/T 7714；文件名和响应头由服务端生成。

## 数据、API 与 UI

Alembic `0007_papers` 新增论文档案、作者、机构、作者归属、来源记录、分类、重复候选、关系候选和正式关系表，并将 `JOURNAL_PAPER` 加入既有内容类型约束。规范 DOI 使用部分唯一索引；访问级别约束阻止仅题录记录携带摘要/全文地址。空库支持实验室降级，存在论文事实时迁移主动拒绝破坏性降级；生产回滚策略是停止 Round06 写入、回退应用镜像并保留事实表。

既有 `GET /api/v1/feed` 增加 `paper_type`、`technology_tag`、`access_level` 和 `year` 筛选；既有 `GET /api/v1/items/{id}` 增量返回论文详情与最多 5 篇 ACL 可见相似论文；`GET /api/v1/items/{id}/citation` 提供三种题录格式。相似论文只显示工程专业/技术标签等匹配理由，不生成学术评分。

`/digital` 增加“数字化案例/期刊论文”Tab。共享卡片显示期刊、年份、DOI、开放状态、成熟度和撤稿/更正提示；同一详情页显示完整题录、研究解读、权限边界、引用复制/导出、原文入口与相似论文。页面不展示模糊可信度，也不产生自动学术评价。

## 验收结果

最终门禁结果（2026-07-15）：

- `make paper-test`：23 passed；真实随机临时 PostgreSQL 完成 `0006 → 0007 → 0006 → 0007`。
- `make quality-gate`：通过；Python 337 passed / 7 skipped，UI 53 passed，Web 51 passed，契约 44 passed；Ruff、mypy strict、ESLint、TypeScript strict、可复现契约生成、pip-audit、pnpm high-level audit 与 Trivy HIGH/CRITICAL 均通过。
- `make fixture-replay`：110 passed，覆盖 OpenAlex/Crossref 固定响应、同 DOI 双来源归一、版权访问策略与历史轮次回放。
- `make web-e2e`：37 passed，论文卡已加入既有 Feed 全量回归。
- `make web-a11y`：9 passed，论文详情 axe 扫描无违规。
- `git diff --check`：最终交付前通过。

## 下一轮起点

下一轮可直接从 Alembic `0007_papers`、publication gate `6.0.0`、统一 `TypeSummary`/`ItemDetail` 分支、来源记录/候选关系表和既有 `/digital` Tab 模式增量扩展。生产来源仍为默认禁用，下一轮不得把固定样本或环境变量视为准入审批；新增内容类型仍必须复用唯一查询/发布服务和共享 Feed 组件。
