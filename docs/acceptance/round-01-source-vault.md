# Round 01 来源注册与原始文档库验收记录

- 日期：2026-07-14
- 分支：`codex/round-01-source-vault`
- 提交：见交付回执（本文件随该提交交付）

## 用户场景与边界

来源管理员登记候选来源，在管理端补齐准入策略、11 项准入证据和 30 个不同内容样本；服务端重算证据并执行 `CANDIDATE → COMPLIANCE_REVIEW → FIXTURE_TEST → APPROVED → ACTIVE` 状态机。管理员可人工上传 HTML/PDF 固定样本，系统先校验与杀毒，再按 SHA-256 私有保存不可变原始对象、建立文档版本，并只预览安全元数据。

本轮不包含定时抓取、OCR、AI、发布和搜索。正式前端继续复用第 00A 轮 `AppShell`、`PageHeader`、`StatusBadge`、`ResponsiveDrawer`；既有资讯路由继续复用 `IntelligenceFeedPage`。本轮不创建 `FeedPage`、`ItemSummary`、`IntelligenceCard` 或 `PublicationService` 的提前/平行实现。

## 交付范围

- Alembic `0002_source_vault` 创建 `source`、`source_policy`、`source_connector`、`raw_object`、`document`、`document_version`、`document_attachment`、`audit_log`，以及保存准入事实所需的 `source_onboarding_record`。
- 42 个 `source_registry.csv` 来源由迁移确定性导入，全部初始为 `CANDIDATE` 且 `enabled=false`。
- 策略与准入记录分别按 `source-policy.schema.json`、`source-onboarding-record.schema.json` 的封闭字段形状构造；检查代码严格取自 `source_onboarding_checklist.json`。证据摘要由服务端计算。
- 启用时重新读取策略、准入记录、策略版本、有效期、检查项和 30 个不同样本摘要；缺失、过期、不通过或只改数据库状态/请求字段时均保持 `effective_active=false`。
- 原始对象使用 `sha256/{前两位}/{完整摘要}` 内容寻址和 `If-None-Match: *` 创建；数据库唯一约束和不可变触发器共同禁止覆盖。
- 上传只接受 HTML/PDF，并校验文件名、扩展名、声明与嗅探 MIME、50 MiB 上限、PDF 页数/加密/脚本/嵌入对象，以及有超时且失败关闭的 ClamAV `INSTREAM` 结果。
- Compose 使用官方 `clamav/clamav:1.5.2-debian13-slim@sha256:14e2e080…e20674`，复用镜像内置健康检查和持久签名库；3310 只在 Compose 私网暴露，API 必须等待 ClamAV 健康后启动。
- `/admin/sources` 提供来源列表、真实空态、候选来源表单；详情页提供准入门禁、策略、准入记录、状态推进和样本上传；文档页仅展示元数据，不渲染不可信 HTML/PDF。
- 指标 `/metrics` 暴露上传、拒绝、去重和对象存储错误计数；来源状态、启停、策略与上传写入哈希链审计日志。

## 迁移与回滚

正向迁移：

```powershell
$env:SRBG_DATABASE_URL='postgresql+asyncpg://srbg:srbg_local_only@127.0.0.1:15432/srbg'
.\.tools\uv\uv.exe run alembic -c apps/api/alembic.ini upgrade head
```

仅回滚本轮并重新验证：

```powershell
.\.tools\uv\uv.exe run alembic -c apps/api/alembic.ini downgrade 0001_foundation
.\.tools\uv\uv.exe run alembic -c apps/api/alembic.ini upgrade head
```

已实际执行上述降级/升级；回滚会删除本轮来源和文档库表，生产执行前必须先完成数据库与私有对象存储备份。对象是不可变证据，数据库回滚不会自动删除对象存储内容。

## API 示例

登记来源（客户端不能提交 `state` 或 `enabled`）：

```http
POST /api/v1/admin/sources
Content-Type: application/json

{
  "name": "四川省交通运输厅示例",
  "base_url": "https://jtt.sc.gov.cn/",
  "channel": "BOTH",
  "source_type": "government",
  "authority_level": "A1",
  "priority": "P1",
  "collection_method": "manual_fixture",
  "poll_interval_minutes": 1440,
  "owner": "source_ops"
}
```

上传固定 HTML 样本：

```http
POST /api/v1/admin/sources/{source_id}/fixture
Content-Type: text/html
X-Filename: round01-sample.html
X-Document-URL: https://jtt.sc.gov.cn/example/document

<!doctype html>...
```

读取文档安全元数据：

```http
GET /api/v1/admin/documents/{document_id}
```

响应包含 `current_version.version_number`、服务端 `content_hash`、`raw_object.sha256`、嗅探 MIME、字节数和扫描状态，不返回原始正文或对象存储密钥。

## 截图证据

### 来源列表与默认拒绝状态

![来源列表](assets/round-01-sources-1440x900.png)

### 来源详情与准入门禁

![来源详情](assets/round-01-source-detail-1440x900.png)

### 不可变文档元数据预览

![文档元数据预览](assets/round-01-document-preview-1440x900.png)

三张截图均由仓库 Playwright 1.61.1 / Chromium 在 1440×900、浅色模式、reduced-motion 下从本地 Nuxt/API 实际页面生成，并已逐张目视检查。

## 测试场景

- 同一字节上传两次只有一个 `raw_object`，第二次不新建版本；同 URL 内容变化建立 `document_version` 2。
- PostgreSQL 直接更新 `raw_object` 被不可变触发器拒绝。
- 29 个样本、重复摘要、缺项、过期或版本不匹配的证据不能激活来源。
- 直接篡改 `source.state='ACTIVE'`、`enabled=true` 后，服务端投影仍为 `effective_active=false`。
- viewer 不能登记、上传、变更策略、推进或启停来源。
- 路径文件名、伪装扩展名、MIME 不符、超大文件、主动内容 PDF、恶意扫描结果与扫描器不可用均被拒绝。
- 真实 Compose ClamAV 已验证干净 INSTREAM 返回 OK；包含 EICAR 的合法 PDF 外壳经运行中 API 上传返回 Problem Details 422，`fixture_count` 保持 0，未写入原始对象。
- 管理页来源登记、准入抽屉、样本抽屉和 axe 无障碍场景由 Playwright 覆盖。

## 最终门禁

当前本地验收结果：

| 门禁 | 结果 |
|---|---|
| `make lint` | 通过；Ruff、Token、UI/Web ESLint 均退出 0 |
| `make typecheck` | 通过；mypy strict 检查 24 个源文件，UI/Web/生成契约 TypeScript 均退出 0 |
| `make test` | Python 68 通过、1 个专用集成场景跳过；UI 52 通过；Web 27 通过 |
| `make contract-test` | 11 通过；生成契约无二次漂移 |
| `make fixture-replay` | 8 通过 |
| `make source-fixture-test` | 真实 PostgreSQL/MinIO 纵向测试 1 通过 |
| `make web-e2e` | Chromium 21 通过，含四个视觉基线和来源准入流程 |
| `make web-a11y` | axe 3 通过，`violations=[]` |
| `make security-check` | 通过；pip-audit 无已知漏洞，pnpm 仅 1 个 low，Trivy HIGH/CRITICAL 为 0 |
| `make quality-gate` | 通过；lint、typecheck、test、contract-test、security-check 全部退出 0 |

最终验收已实际执行：

```text
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make quality-gate
make web-e2e
make web-a11y
make source-fixture-test
```

## 联网核验与生产杀毒联调

按用户要求，联网前先通过 `web-access` skill。为避免接触日常 Chrome 和 Google 登录态，使用全新临时用户目录、禁用同步的 Headless Chrome，并仅监听随机本机 CDP 端口；代理确认只存在一个隔离空白标签页。

- [ClamAV 官方 Docker 文档](https://docs.clamav.net/manual/Installing/Docker.html)确认官方仓库、3310 端口、标签语义及镜像健康检查；
- [Docker Hub 官方标签 API](https://hub.docker.com/v2/repositories/clamav/clamav/tags/1.5.2-debian13-slim)确认 `1.5.2-debian13-slim` 多架构索引摘要为 `sha256:14e2e0805c6a5ff6728ea591c05565e0f0954d93e8701919012c3a8c44e20674`；
- 镜像拉取后再次由本地 Docker inspect 核对 RepoDigest 和 `clamdcheck.sh` 健康检查，容器实际进入 `healthy`；API 干净样本和 EICAR PDF 生产链路联调均完成。
