# 第 13 轮验收：内部发布投影、Event 身份与权限隔离

## 验收结论

本轮建立了可由真实低权限 PostgreSQL 登录验证的 Event-keyed 内部发布影子投影。现有 Feed、搜索、日报、收藏、专题和详情消费者尚未切换，仍使用既有 Item-keyed 路径；第 14 轮只能进行一次性消费者切换，不能并行形成第二套用户可见身份。

本地固定验收数据连续两代回填均得到 32 个稳定 Event，其中 23 条 `FULL`、9 条 R3 `METADATA_ONLY`、0 条 R4 投影，对账差异为 0。生产就绪状态不因本轮改变。

## 开始前基线与执行推导

### 用户场景

企业内部 viewer 在 OIDC/SSO 登录后，最终应只从稳定 Event 身份的发布投影读取 Feed、Event、搜索、日报、收藏和详情。本轮先生成不可见于现有消费者的安全影子数据，并用真正受限的数据库身份证明读取边界，为下一轮原子切换提供输入。

### 信任边界

- PostgreSQL 业务表、原始对象、accepted claims、审核记录和风险判断属于写侧权威区。
- 唯一 `PublicationService` 及受控 publisher writer 可以生成或失效投影；客户端、普通 reader、模型和后台按钮不能直写发布状态或投影。
- `published_v1` 是读侧发布区；`srbg_projection_reader` 只读版本化视图，不依赖业务表 `WHERE` 过滤实现隔离。
- 企业 OIDC/JWKS 是 staging/preproduction/production 身份边界；本地身份头只在 development/demo/test 生效。
- 审计日志是 append-only/tamper-evident 边界，链根写入独立对象存储；不宣称能抵抗拥有完整数据库管理权限的管理员。

### 复用对象

- 复用现有 `event`/`event_item` 的已确认映射；没有映射时建立正式一对一 Event 绑定，不创建 `PROVISIONAL_EVENT`。
- 复用 `PublicationService`、`publication_revision`、accepted claims、证据定位和既有撤回/纠正状态。
- 保留 `publication_projection_state` 作为 SEARCH/CACHE/DAILY_DIGEST 的失效状态，不把它冒充内容投影。
- 复用既有 OIDC、角色、职责分离和 `audit_log` hash 链，并收紧其数据库授权。

### 数据迁移与回滚

- `0013_internal_projection` 新增 `published_v1`、稳定 Event 绑定、对账、审计锚点和三条独立枚举轴。
- 旧 `risk_level` 不删除；迁移使用 `risk_level -> publication_risk_tier` 同值映射和数据库约束保持历史语义，兼容触发器处理旧写入。回滚先移除新投影对象与新轴，不改写旧字段。
- 影子回填持有事务级 advisory lock，按 generation 整体生成；失败整事务回滚，可幂等重跑。只有完整 generation 成功后才成为影子 current，不触发消费者切换。

### 失败降级

- 无稳定、可验证来源的数据不进入投影；R4 和其他不合格记录为 `NONE`。
- 官方 R3 待审核只降级为白名单题录，并明确 `MACHINE_DISCOVERED`/`PENDING_HUMAN_REVIEW`。
- 撤回、纠正、`LEGAL_TAKEDOWN` 或来源 revision 变化会失效旧投影；旧 generation 不再可达。
- OIDC/JWKS、step-up、角色、reader 数据库连接或对账失败均默认拒绝，不回退到业务超管连接。

### 明确不做

- 不开放匿名公网，不实现多租户或浏览历史。
- 不实现完整 Item→Event 迁移、事件合并拆分、来源 V2、AI 观察、邮件或企业微信。
- 不切换或分批切换 Feed、搜索、日报、收藏、专题和详情，不创建第二套可见 Feed/Card。
- 不复制原始全文，不给普通 reader 旧业务表兼容权限。
- 页面与组件没有改动；仅收紧 Nuxt 服务端代理的身份头处理，并运行完整 Web 回归。

### 测试顺序

1. 先写契约、投影策略、认证/RBAC、reader SQL 边界、迁移和真实低权限登录的失败测试。
2. 实现最小契约、迁移、回填、reader、OIDC step-up、审计函数和独立锚定。
3. 回放 `0012 -> 0013 -> 0012 -> 0013`，再进行两代影子回填和差异对账。
4. 使用临时真实 reader 登录执行权限对抗测试，审计所有发布路径。
5. 依次运行 lint、typecheck、全量测试、契约、安全、fixture、quality、Round 13 专项和 Web 回归。

## 发布契约

权威枚举同时存在于 Python/Pydantic、JSON Schema、生成 TypeScript 和 PostgreSQL `CHECK` 约束中：

- `publication_risk_tier`: `R1 | R2 | R3 | R4`
- `content_severity`: `UNASSESSED | LOW | MODERATE | HIGH | CRITICAL`
- `projection_level`: `NONE | METADATA_ONLY | FULL`

三个字段只能各自表达发布风险、内容严重性和可见投影等级；severity 不能授权，risk 不能伪装审核结果，projection 不能改变 risk。

R3 题录样例（关键事实必须不存在或为 `null`）：

```json
{
  "id": "019b0000-0000-7000-8000-000000000301",
  "publication_revision_id": null,
  "projection_version": "1.0.0",
  "generation": 2,
  "domain": "SAFETY",
  "content_type": "SAFETY_REGULATION",
  "title": "官方题录标题",
  "source_name": "官方来源",
  "source_published_at": "2026-07-01T00:00:00Z",
  "first_discovered_at": "2026-07-02T00:00:00Z",
  "original_url": "https://example.gov.cn/document/301",
  "review_status": "PENDING",
  "discovery_status": "MACHINE_DISCOVERED",
  "fact_review_status": "PENDING_HUMAN_REVIEW",
  "publication_risk_tier": "R3",
  "content_severity": "UNASSESSED",
  "projection_level": "METADATA_ONLY",
  "one_sentence_fact": null,
  "type_summary": null
}
```

`FULL` 详情以同一 summary 为头，仅增加 accepted claims 和证据引用：

```json
{
  "summary": {
    "id": "019b0000-0000-7000-8000-000000000302",
    "projection_version": "1.0.0",
    "generation": 2,
    "publication_risk_tier": "R2",
    "content_severity": "LOW",
    "projection_level": "FULL",
    "discovery_status": "HUMAN_CURATED",
    "fact_review_status": "HUMAN_REVIEWED"
  },
  "claims": [{"claim_id": "019b0000-0000-7000-8000-000000000401", "field_name": "one_sentence_fact", "value": "已接受且可回溯的事实"}],
  "evidence": [{"evidence_id": "019b0000-0000-7000-8000-000000000501", "locator": "paragraph:019b0000-0000-7000-8000-000000000601", "content_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]
}
```

样例为字段边界说明；完整必填字段由生成的 JSON Schema 定义。

## 真实数据库授权证据

测试通过隔离环境创建的真实 `srbg_projection_reader_login` 登录执行 SQL，不使用 owner、API 超管或 publisher 连接。

| 验证项 | 结果 |
| --- | --- |
| `published_v1` schema `USAGE` | 允许 |
| current summary/detail、title search、distribution/export 版本化视图 `SELECT` | 按视图允许 |
| `public` 业务 schema `USAGE` | 拒绝 |
| 原始对象、业务表、accepted claims、审核备注、`audit_log` | 无 `USAGE/SELECT` |
| `published_v1` 投影基表 | 无直接 `SELECT` |
| R4 数据 | 视图中为 0，数据库约束拒绝生成 |
| publisher/runtime 直接 `audit_log INSERT` | 拒绝 |
| 受控审计函数 | 允许并由数据库计算前链、hash 和时间 |
| 独立 audit chain anchor | 1 个；对象存储 endpoint 与原始对象存储不同 |

查询参数、伪造游标、旧 generation、标题搜索、distribution candidates 和 export 都只能到达 `published_v1` 当前有效视图，不能把 reader 引回业务表。

## R3/R4 与一致失效负向验证

- R3 待审核只允许标题、类型、官方来源、原文发布时间、首次发现时间、原文链接和待审核状态；contract validator 拒绝其中的事实摘要、类型事实、claims 或 evidence。
- R3 的 allowed surfaces 仅为 `FEED/EVENT/TITLE_SEARCH`；`SELECTED/DAILY/RECOMMENDATION/NOTIFICATION/FULLTEXT_EXPORT` 全部排除。
- R4 policy 始终返回 `NONE`，数据库禁止 R4 projection revision；本地数据集没有 R4 行，测试用构造样本验证零投影而非仅依赖空数据。
- 撤回、纠正、`LEGAL_TAKEDOWN` 和 publication revision 变化触发失效；Feed/Event/search/daily/download/cache 使用同一 active generation 语义，旧 generation 不可恢复可见性。
- `include_draft` 不存在于影子 reader 接口；治理后台参数不能传入普通 viewer 通道。

## 身份、角色与浏览器边界

- staging/preproduction/production 只接受 OIDC，校验 issuer、audience、RS256 algorithm、kid、exp、nbf、iat、角色和 JWKS；失败默认 401/403。
- 非开发环境忽略 `X-SRBG-*` 本地身份头。viewer、editor、reviewer、source_admin、platform_admin 在服务端映射；source_admin 不能发布，reviewer 不能启停来源，提交人与 R3 reviewer 必须分离。
- 高权限发布/审核/来源写操作要求 allowlisted `acr`、MFA `amr` 和 15 分钟内 `auth_time`；development/demo/test 有显式标记的本地等价 step-up。
- CORS 只接受精确 allowlist，拒绝 `*`。Nuxt 服务端代理剥离客户端身份头，只在 development/demo/test 注入短时本地身份；浏览器代码不保存长期 token 到 localStorage 或日志。
- 当前没有新增 Cookie/BFF 会话；若后续引入，必须使用 `Secure`、`HttpOnly`、`SameSite` 并为状态变更实现 CSRF 防护。

## 影子回填与对账证据

| generation | source | projected | FULL | METADATA_ONLY | R4 | differences | 状态 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 32 | 32 | 23 | 9 | 0 | 0 | SUCCEEDED |
| 2 | 32 | 32 | 23 | 9 | 0 | 0 | SUCCEEDED |
| 3 | 32 | 32 | 23 | 9 | 0 | 0 | SUCCEEDED（独立复验） |

两代回填后 `event_identity_binding=32` 且稳定 Event 数仍为 32，证明幂等重跑未建立第二套身份。每条 FULL 投影都指向有效 publication revision，只读取 accepted claims/evidence；每条 metadata-only 投影都满足官方 R3 待审核白名单。

## 迁移、审计与可观测性

- 隔离 PostgreSQL 完成 `0012 -> 0013 -> 0012 -> 0013`；最终 head 为 `0013_internal_projection`。
- 发布、撤回、来源启停、权限和 Prompt 变更保持审计；运行角色的无意义 UPDATE/DELETE 和直接 INSERT 均被撤销。
- 结构化日志只记录 generation、event ID、策略原因、差异类型和结果，不记录正文、token、Cookie 或个人信息。
- 低基数指标：`srbg_internal_projection_runs_total{outcome}`、`srbg_internal_projection_records_total{level}`、`srbg_authorization_denials_total{reason}`、`srbg_internal_projection_reconciliation_differences`、`srbg_internal_projection_last_success_timestamp_seconds`、`srbg_audit_chain_anchor_last_success_timestamp_seconds`。
- publisher 每日执行 `srbg.audit.anchor`；Prometheus 对投影差异、投影陈旧和审计锚定陈旧提供 fail-closed 告警，处置步骤记录在 `docs/operations/runbooks.md`。

## 2026-07-15 独立复验与修复

复验基于分支 `codex/round-10-feed-search-daily`、基线提交 `fa8972f80b6388ae9275ed3ef3367a0de50e06de` 和开始时 clean 工作树执行。环境为 Windows/PowerShell、Docker Compose 5.3.0、Docker Server 29.6.1、uv 0.11.28、pnpm 11.12.0、GNU Make 4.4.1；核心代码修复差异快照 Git blob hash 为 `69ab2cda3855b704b658fa006a5658f4ca9d823d`（最终提交 hash 在提交完成后由验收交付记录给出）。

先写失败测试并真实得到红灯：

| 命令 | 失败证据 |
| --- | --- |
| `pytest apps/api/tests/test_round13_projection_policy.py tests/infrastructure/test_round13_observability.py -q` | exit 1；5 failed/3 passed，暴露 PublicationService 回填边界、CLI 旁路和指标/告警/Runbook 缺口 |
| `make phase2-round13-test` | exit 1；3 failed/23 passed，额外复现 accepted claim 字符串被二次 JSON 编码 |
| 授权拒绝结构化日志定向测试 | exit 1；缺少 `authorization_denied` 事件 |

最小修复后，影子回填 CLI 只调用 `PublicationService.build_internal_projection`；字符串 claim 保留原值，非字符串才 JSON 序列化；运行时从 PostgreSQL 提供对账/最近成功/锚定时刻指标；补齐投影失效、权限拒绝和锚定结构化日志、每日锚定任务、三条告警及 fail-closed Runbook。没有修改页面、Feed/Card 或切换任何用户消费者。

真实运行证据：publisher 容器回填返回 generation 3、source/projected 32/32、FULL 23、METADATA_ONLY 9、R4 0、difference 0；独立锚定返回既有有效 anchor。`srbg_projection_reader_login` 登录读取两个 current 视图成功，`public.intelligence_item` 查询以 `permission denied for schema public` 失败；32 条 title 的首字符为双引号的计数为 0。受保护 `/metrics` 返回对账差异 0 和两个成功时刻指标；`promtool check rules` 返回 8 rules、SUCCESS。

## 最终门禁

最终工作树（包括运行时 demo 身份边界修复）完成以下门禁，不以早期局部通过替代：

下表命令均为本次复验实际执行且最终退出码为 0；失败测试的非零退出结果单独保留在上节。

| 门禁 | 最终结果 |
| --- | --- |
| `make lint` | PASS |
| `make typecheck` | PASS；mypy 95 source files，无问题，Vue/Nuxt/生成 TS strict 通过 |
| `make test` | PASS；Python 502 passed/24 skipped，UI 53 passed，Web unit 69 passed |
| `make contract-test` | PASS；生成可复现，58 passed |
| `make security-check` | PASS；无 HIGH/CRITICAL，pnpm 仅 1 个已知 low |
| `make fixture-replay` | PASS；164 passed，Round 09 对抗评估通过 |
| `make quality-gate` | PASS；在最后代码变更后再次全量通过 |
| `make phase2-round13-test` | PASS；真实临时 reader/runtime/publisher 登录，32 passed |
| `make web-e2e` | PASS；42 passed |
| `make web-a11y` | PASS；13 passed，axe 违规为 0 |
| Alembic 正向/回滚/再正向 | PASS；`0012 -> 0013 -> 0012 -> 0013` |
| 发布路径审计 | PASS；应用写入均经 `PublicationService` |
| 数据库权限对抗 | PASS；reader/runtime/publisher 负向授权断言通过 |

## 已知限制

- 影子 reader 尚未接入用户 API；普通用户仍由旧消费者读取，不能把本轮描述为已切换或生产上线。
- 本地 32 条记录是固定/集成验收数据，不是获准真实来源的生产运行证据。
- 没有实现 Event 合并拆分和完整 Item 迁移；一条已有 Event 可聚合多个来源 Item，没有已确认映射时只建立正式绑定。
- 审计锚定提高事后发现篡改的能力，但不提供对数据库管理员的绝对不可篡改保证。
- 第 11 轮真实金标、连续运行、PITR 和真实告警路由阻断项仍然存在。

当前轮验收通过，可以进入下一轮。尚未启动第14轮，也尚未切换任何用户消费者。
