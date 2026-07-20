# T20R 中国建筑与徐工集团替代 SourceStream 验收

## 范围和替代决定

本记录对应 GitHub Issue #37，父 Spec #1。Owner 决定不再把中国中铁与三一集团作为首批 W5 目标：原 Issue #21 不伪装成验收通过，而以 `SUPERSEDED` 关闭。替代组合复用 `ENT-002` 中国建筑，并为此前未注册的徐工集团分配唯一候选代码 `ENT-010`；没有复用 `ENT-003` 或 `ENT-009`。

研究只形成 `SourceResearchDisposition` 输入。两流均保持 `CANDIDATE`、`desired_enabled=false`、`source_admission=null`、`actual_running=false`、不追加 `PAUSE`、不授予覆盖信用。完整一手来源记录见 [替代来源研究](../../research/2026-07-20-issue-21-alternative-source-streams.md)。

## 有界流

### `ENT-002` 中国建筑

- 集合：`https://www.cscec.com/xwzx_new/zqydt_new/`
- 分页：`/xwzx_new/zqydt_new/index_{positive_integer}.html`
- 详情：`/xwzx_new/zqydt_new/YYYYMM/{numeric_id}.html`
- 连接器：`HTML_LIST_DETAIL`；仅 `text/html`；1440 分钟；1 request/minute；10 秒超时；最多 5 次同主机重定向。
- 核验：`2026-07-20T03:18:08Z`；集合与详情 HTTPS 200、零重定向；公网 CDN 地址 `138.113.89.175`、`115.127.225.136`。
- robots：点时返回 404，记录为“未发布”而不是永久许可；SourceAdmission 必须重查。
- 内容：要求在域工程对象与工程生命周期事实同时出现，排除党建、人事、资本市场、奖项、纯商业运营、品牌和制造基地。
- ClaimBasis：仅 `PROJECT_FIRST_PARTY_RECORD`，不得冒充独立验证。

### `ENT-010` 徐工集团

- shell：`https://www.xcmg.com/case/case.htm`
- 列表：`POST https://www.xcmg.com/ext/ajax_case.jsp`，固定表单 `flag=case`、`ids=1,1,`、`channelId=22571`。
- 详情：`/case/case-detail-{numeric_id}.htm`；核验列表约 300 个有界详情链接。
- 连接器：`HTML_SHELL_POST_LIST_DETAIL`；仅 `text/html`；1440 分钟；1 request/minute；10 秒超时；最多 5 次同主机重定向。
- 核验：`2026-07-20T03:13:15Z`；shell、POST 列表与详情 HTTPS 200、零重定向；公网地址 `115.120.56.205`。
- robots：`User-agent: *` 下空 `Disallow`，未禁止 `/case/` 或 `/ext/ajax_case.jsp`。
- 条款：允许为传达或查看信息作电子复制，但禁止镜像、修改后再发布和商业利用。
- 内容：要求施工机械直接用于在域工程生命周期，排除 ERP、生产线、制造工厂、泛制造数字化、纯交付、发运、销售和品牌奖项。
- ClaimBasis：仅 `MANUFACTURER_CLAIM`，不得提升为独立验证或权威认定。

两流都只允许 Owner 私有研究所需 raw HTML、题录、必要短摘和原链；禁止图片、视频、附件、全文与公开再分发。实际运行前仍须由 SourceAdmission 重新核验公网、重定向、robots、条款、版权、限速、预算和运行门禁。

## TDD

RED：新增基础设施行为测试后，因版本化 Schema、清单、`ENT-010` 注册候选和首批映射均不存在而出现 5 个预期失败。

GREEN：新增版本化 Schema/清单、唯一注册候选以及首批 rollout/campaign 替代映射后，`make t20r-source-discovery-test` 的 5 项测试通过，覆盖精确集合、POST 表单、ClaimBasis、无运行权限、无附件/公开再分发、未知合规事实失败关闭和原两源不再占用首批名额。

## 诚实边界

本票没有产生 SourceAdmission、Owner GO、真实运行、观察窗口、覆盖信用、Owner Gold 或 DeepSeek 成功；没有绕过 WAF、robots、条款、版权、公网安全、raw-first、PublicationService 或 R3/R4。中国铁建的 WAF/人机识别和大疆禁止自动访问的条款均未绕过。

## Issue 收口

- #37：两条替代流满足本票研究态 `BOUNDED + ADMISSION_READY` 条件，以 `COMPLETED` 关闭。
- #21：以 `NOT_PLANNED / SUPERSEDED` 关闭，明确不表示中国中铁许可 blocker 已解除或原两流验收通过。
- #22：标题、正文和原生依赖已改为中国建筑 + 徐工集团，并由 #37 替换 #21；#20 仍是其另一原生 blocker。
- 父 Spec #1 与本地首批 rollout/campaign 均保持十个机构，并同步替代后的机构名称。

## 门禁结果

- `make t20r-source-discovery-test`：5 passed。
- `make quality-gate`：通过；Ruff、Nuxt/UI lint、mypy strict、Nuxt/UI/契约 typecheck、全量测试、契约可复现、依赖审计和 Trivy 均通过。
- 全量测试：Python 1331 passed、27 skipped（仓库既有条件型跳过）；UI 53 passed；Web 101 passed；契约 109 passed。
- `make fixture-replay`：357 passed；离线 mock 质量评估通过，不构成真实 DeepSeek 成功。
- 本票不涉及正式前端行为变更，`make web-e2e` 与 `make web-a11y` 不适用。
