# v2 T12 许可媒体与附件安全交付验收记录

- Issue：`flyingTurkey/codex#13`
- Parent Spec：`flyingTurkey/codex#1`
- 日期：2026-07-20
- 状态：PASS（本票工程、迁移、安全与浏览器门禁通过；不代表外部来源、DeepSeek 或 closeout GO）

## 前置与范围

GitHub 原生 `blockedBy` 已回读：本票唯一原生 blocker #11（T10 Owner Reader B）已于 2026-07-20 关闭。父 Spec #1、本 Issue、`CONTEXT-MAP.md`、acquisition、intelligence-qualification、evidence-ai、publication-reader contexts，以及 ADR-0001/0002/0003 均已完整读取。

本轮只实现许可媒体登记、安全派生、FULL 投影、同源预览与短期签名下载这一条纵向行为。没有新增来源、采集运行授权、发布旁路或前端隐藏式 ACL；发布仍只能由 `PublicationService` 基于 PostgreSQL 权威上下文执行。

## TDD 证据

RED 阶段先加入媒体登记、读取服务、对象存储错误映射、迁移和正式浏览器断言，依次观察到缺失媒体领域类型、未实现不可用错误、对象存储错误未归一、隔离运行器未准入 T12 verifier，以及真实签名 URL 格式差异导致的失败。

GREEN 阶段用最小实现闭合上述行为；没有删除断言、降低阈值、增加 skip 或吞掉异常。`make t12-media-delivery-test` 最终为 36 passed，并在一次性 PostgreSQL 中通过 `0044 → 0045 → 0044 → 0045` 往返。正式 Chromium 定向用例同时覆盖 1280px 与 320px，确认媒体请求失败时证据正文和原文动作仍可用、无远程图片回退，axe serious/critical 为零。

## 验收映射

- 许可依据只接受 `PUBLIC_DOMAIN`（公共领域）、`EXPLICIT_LICENSE`（明确许可）、`SOURCE_AUTHORIZED`（来源授权）或 `OWNER_OWNED`（Owner 自有素材）；服务端保存许可证据引用，客户端哈希和自报扫描状态不具权威性。
- 登记必须关联当前 `CLEAN` 的附件、raw 对象及 URL 哈希一致的成功采集尝试；数据库 `SECURITY DEFINER` 函数和触发器共同失败关闭。
- JPEG、PNG、WebP 先按实际字节解码并在大小/像素边界内重新编码为内容寻址 PNG。无法生成安全派生物时投影 `null`，前端不生成 `<img>`；预览端点只读派生对象，不读取原始对象。
- R3 契约没有媒体字段；R4 和其他不可见内容的普通读取保持 404。FULL 媒体和附件只能经 `PublicationService` 投影。
- 无再分发许可时只返回材料名称、来源原站链接；满足再分发许可且当前三重扫描状态均为 `CLEAN` 时，下载端点才可 302 到私有对象签名 URL，TTL 被服务端限制为不超过 300 秒。
- 对象缺失统一为 404；对象存储暂时失败统一为不泄漏桶名、对象键或供应商细节的 503。任何当前扫描状态改变都会即时撤销预览和下载，不依赖旧投影中的历史许可判断。
- URL 只接受无凭据、无片段、标准 443 端口的 HTTPS 公网主机；IP literal、控制字符和异常端口失败关闭。既有 acquisition/document-vault 回归继续覆盖重定向逐跳公网复核、实际 MIME、文件大小、PDF/压缩炸弹和流式字节边界，本票未另建绕行入口。
- 对象存储桶保持私有；页面只消费同源 `/api/v2/media/{id}/preview`，媒体失败不会遮蔽标题、`SourceExcerpt`、AI 状态或原文动作。桌面、移动端和 axe 定向验收均已覆盖。

## 数据与安全边界

迁移 `0045_t12_media_delivery` 增加权威附件关联、许可证据、安全预览元数据、受限读取函数、写入触发器与 security-barrier 视图；回滚删除这些增量对象并已实际验证可再次升级。私有对象下载仍使用现有对象存储签名机制，外部 I/O 有明确边界；日志和 Problem Details 不记录正文、对象键、令牌或 Cookie。

测试中的许可、扫描与附件记录均为一次性协议事实，不是 Owner Gold、真实来源准入、真实采集窗口、DeepSeek `RealSchemaSuccess` 或任何 ENGINEERING/PRODUCTION GO 证据。本票未启用来源、未联网调用 DeepSeek、未写入虚假审核或安全事实，也未改变 robots、版权、公网地址与重定向安全门槛。

## 门禁结果

仓库内置 GNU Make 路径为 `.tools/make/tools/install/bin/make.exe`。本票定向门禁：

- `make t12-media-delivery-test`：PASS（36 passed；迁移往返通过）；
- T12 正式 Chromium/axe 定向行为：PASS（1 passed，覆盖桌面与移动视口）。

完整仓库门禁最终实跑结果：

- `make lint`：PASS（Ruff、tokens、UI/Web ESLint）；
- `make typecheck`：PASS（mypy 148 source files、UI vue-tsc、Nuxt strict typecheck、生成契约 tsc）；
- `make test`：PASS（Python 1264 passed / 27 个仓库既有条件性 skipped，本票未新增；UI 53 passed；Web 101 passed）；
- `make contract-test`：PASS（生成可重复；109 passed）；
- `make security-check`：PASS（pip-audit、pnpm audit、Trivy HIGH/CRITICAL）；
- `make fixture-replay`：PASS（357 passed；mock 评估通过，不构成真实外部证据）；
- `make quality-gate`：PASS；
- `make web-e2e`：PASS（74 passed）；
- `make web-a11y`：PASS（21 passed，包含 T12 桌面/移动媒体失败用例）。

门禁兼容清理仅包含 import/换行等机械格式、静态检查的固定表名说明，以及把两个旧调用方 E2E 从早期“零计数”原型文案对齐到 #12 当前公开空态“附录当前没有治理记录。”；仍断言附录已展开、已加载和键盘可操作。没有改变 #12 的组件行为、契约、数据库投影语义、状态机、文案、验收记录或 Issue 状态，未删除断言、增加 skip 或降低门槛。
