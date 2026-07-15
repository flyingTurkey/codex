# Round 07 软件、物联网、低空和 AI 设备验收记录

- 日期：2026-07-15
- 用户场景：工程技术人员在既有 `/digital` 信息流统一检索四类技术产品，区分厂商声明与独立工程证据，查看型号版本、接口部署、应用案例及许可限制
- 固定来源：广联达软件产品、大疆行业低空设备
- 发布入口：唯一 `PublicationService`，publication gate `7.0.0`

## 范围、复用与不做项

本轮交付统一 `technology_product_profile` 及 vendor、product、model、version 实体，覆盖产品类型、型号、版本、能力、接口、部署方式、应用场景、工程案例、证据等级和许可状态。软件、物联网、低空、AI 设备作为统一模型的四个增量类型，不复制四套表、查询、卡片或详情。

实现继续复用 `AppShell`、`IntelligenceFeedPage`、`TimelineFeed`、`IntelligenceCard`、冻结的 `FeedPage`/`ItemSummary`、既有详情页、`item_relation` 和唯一 `PublicationService`。统一 `/api/v1/feed` 增加 `product_kind`、`evidence_level`、`deployment_mode` 及既有场景/成熟度筛选；统一 `/api/v1/items/{id}` 增量返回 `technology_product`；审核工作台增加型号/版本候选入口。

本轮不做价格采集、采购比选、设备远程接入和飞行审批。产品页固定显示“仅供技术调研，不构成采购建议”，不能自动产生“适用于四川路桥采购”结论；低空产品固定显示“产品发布不代表空域、适航、飞手和项目许可。”。

## 第一性原理与证据边界

1. 产品身份由厂商、产品、型号、版本四层构成。规范化只处理 Unicode、大小写和多余空白，不删除可区分型号的标点或数字；同名不同型号保持独立，新版本新增记录并以 `supersedes_version_id` 链接，绝不覆盖历史。
2. `PROMOTIONAL_CLAIM` 必须保留厂商归因且不能携带独立验证标记；`VERIFIED_CAPABILITY` 必须同时具备不同来源主体和 `INDEPENDENT_CONFIRMATION` 角色的证据。数据库约束、Pydantic 契约与 v7 发布门禁同时执行该分离。
3. 产品与数字化案例只通过具备证据、已人工审核并发布的 `APPLIED_IN` 关系展示；未发布或未审核案例不会进入普通产品详情。
4. 低空设备只有 `PRIMARY_OFFICIAL` 许可证据经接受后才能标记 `VERIFIED`；否则必须为 `UNKNOWN`。产品发布本身不代表空域、适航、飞手或项目许可。
5. 厂商图片不进入采集响应或对象存储，档案约束 `image_downloaded = false`，页面使用本地中性占位区。
6. ENT-007 广联达和 ENT-008 大疆行业应用早已由来源注册迁移建立，继续保持 `CANDIDATE/disabled`。固定响应、CSV 或客户端自报状态均不能形成生产 active，生产采集仍必须通过既有来源准入服务。

## 数据、迁移与回滚

Alembic `0008_technology_products` 新增：

- `technology_vendor`、`technology_product`、`technology_product_model`、`technology_product_version`：分层唯一身份、版本历史与后继关系；
- `technology_product_profile`：四类差异字段、证据等级、许可状态、成熟度、接口、部署方式和图片下载禁令；
- `technology_product_capability`：厂商声明/已验证能力、Claim、证据和独立证据；
- `technology_product_taxonomy`：工程专业、应用场景和技术标签；
- `product_normalization_candidate`：型号别名、版本后继和疑似重复候选及审核决定。

真实随机临时 PostgreSQL 已完成 `0007 → 0008 → 0007 → 0008`。存在四类产品事实时迁移拒绝破坏性降级；生产回滚策略为停止 Round07 写入、回退应用镜像并保留产品事实表。

隔离回放发现 ENT-007/008 已在 `0002_source_vault` 中存在，因此 `0008` 不重复插入，也不会在降级时删除既有来源。运行镜像的 `.dockerignore` 同步显式包含 v5/v6/v7 权威门禁资产，实际重建后 API、迁移和 Web 健康检查通过。

## API、审核、UI 与指标

四类产品通过同一 `/api/v1/feed` 和 `IntelligenceCard` 展示公共字段，并以同一 `TypeSummary` 判别联合提供差异字段：软件显示接口/部署，物联网显示连接方式/成熟度，低空显示平台/载荷/许可，AI 设备显示设备形态/AI 任务/生产验证。

同一详情页只增加统一产品分支，严格显示三个一级区域：

- 产品能力：中性灰“厂商声明”和独立证据“已验证能力”分列，每项可打开证据；
- 工程证据：证据等级、接口、部署方式、场景、版本历史和已审核 `APPLIED_IN` 案例；
- 许可与限制：许可状态、限制、非采购提示和低空固定合规提示。

审核工作台的 reviewer 可对 `MODEL_ALIAS`、`VERSION_SUCCESSOR`、`POSSIBLE_DUPLICATE` 选择合并别名、链接新版本或保持独立，必须填写理由；API 仅接受 reviewer，决定经唯一 `PublicationService` 锁定候选、写入版本关系并追加审计。`/metrics` 增加按类型/证据等级/许可状态的产品量、两类能力量和待归一候选量。

## 固定样本与安全

`apps/api/tests/fixtures/round07/` 保存两个最小 JSON 固定响应及 SHA-256 清单：广联达软件样本和大疆低空设备样本。两者均 `publishable: false`、`image_downloaded: false` 且不含图片 URL；固定适配器完全离线，真实适配器在来源非服务端有效 active 或未注入共享安全 HTTP 客户端时默认拒绝。

所有查询使用参数化 SQL，外部输入有受控枚举/长度校验；R3/R4 投影和来源准入仍由服务端处理。v7 发布上下文由仓储现查身份候选、能力分组、独立证据、采购禁语、图片状态和许可证据，不信任客户端、模型或固定样本自报结果。

## 验收结果

最终门禁结果（2026-07-15）：

- `make product-test`：24 passed；随机临时 PostgreSQL 完成 `0007 → 0008 → 0007 → 0008`。
- `make quality-gate`：通过；Python 364 passed / 7 skipped，UI 53 passed，Web 55 passed，契约 47 passed；Ruff、mypy strict、ESLint、TypeScript strict、可复现契约生成、pip-audit、pnpm high-level audit与 Trivy HIGH/CRITICAL 均通过（pnpm 仅报告 1 个 low）。
- `make fixture-replay`：125 passed，覆盖两类固定产品来源、能力证据边界和 v7 门禁。
- `make web-e2e`：38 passed；四类 Tab、共享低空产品卡片与筛选通过。
- `make web-a11y`：10 passed；产品详情 axe 扫描无违规。
- `git diff --check`：最终交付前通过。

## 下一轮起点

下一轮可从 Alembic `0008_technology_products`、publication gate `7.0.0`、统一产品判别联合、归一候选和既有 `/digital` Tab 继续增量扩展。生产来源仍默认禁用，不能把固定样本、厂商声明或产品发布转换为采购、许可、远程接入或飞行审批结论。
