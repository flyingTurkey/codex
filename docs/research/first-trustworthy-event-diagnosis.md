# 第一条可信 Event：历史能力审计与阻断诊断

> 调查日期：2026-07-29（Asia/Shanghai）
> 调查分支：`codex/phase-2-first-event-diagnosis`
> 调查边界：只读 Git、源码、迁移、测试、正式 PostgreSQL 和本地只读 API
> 数据边界：未调用公网、模型或任务队列；未修改来源、AI 配置、发布状态或数据库；
> 未输出正文、Secret、Cookie、URL 全文或完整模型响应

## 1. 结论

本轮选择了真实、已保存、来源边界明确且中心事实可归为低风险
`INDUSTRY_UPDATE` 的 DocumentVersion：
`019f75b5-b28b-7c28-bdbc-aee6eef0910e`，题名为
“山东青岛胶州湾第二海底隧道主线盾构掘进收官”。

它已经具备 production scheduled fetch、raw-first、CLEAN raw、安全事实、
current/READY DocumentVersion，以及 3 条 accepted claims 和 3 条有锚点 evidence。
它没有形成 Event、SourceExcerpt、发布决定、v2 projection 或 Reader 输出。

**第一个确定阻断点是 SourceAdmission 不成立。**

- 该文档的历史 SHADOW pipeline 启动时，所属 source 没有任何
  `source_admission_assessment_v2`；
- 当前最新 SourceAdmission 为 `PAUSE`，不是生产资格所要求的 `ADMIT`；
- 当前正式库也没有 active qualification policy bundle；
- 因此当前权威代码会在任何真实模型调用前失败关闭，不能合法把旧 SHADOW 结果或现有
  claims 继续推向 publication。

这是“来源意图/采集运行”和“内容生产权威”分离后的正确失败关闭。`source.desired_enabled`
为真、SourceStream 为 `READY`、采集 runtime 为 `RUNNING`，均不能替代
SourceAdmission，也不能授予发布权。

完整闭环需要代码和新迁移，但**修复首个 SourceAdmission 事实本身不需要改表**。
首先需要在现有 Schema 中用当前、可审计的一手证据形成新的 `ADMIT` assessment，并在
另行授权下激活精确的生产 qualification bundle。此后仍需选择性重实现 VERIFY 原子
完成、自动发布 authority/revision、projection revision guard、invalidation/epoch/veto
和最小 ACL；不得移植 transfer 或 849 的整提交和旧迁移。

## 2. Git 与数据库基线

### 2.1 第一阶段

- `PHASE_1_SHA`：
  `66d4e7cf0d0ac25cc14c18eff365697b080c1eda`
- 第一阶段文档权威提交：
  `f44ad7864b674f836880bbebda9cbd7d8ccdf6ab`
- 第一阶段风险分层提交：
  `66d4e7cf0d0ac25cc14c18eff365697b080c1eda`
- `a83dda41fd00175a93a864901a898d411bf53b83` 是
  `PHASE_1_SHA` 的祖先。
- 调查开始前工作树干净。

### 2.2 正式数据库

正式 PostgreSQL 通过回环地址访问。查询使用受限 API 身份或本地数据库身份，并在
`transaction(readonly=True)` 中确认 `transaction_read_only=on` 后只执行 `SELECT`。
未回显 DSN 或凭据。

- 正式数据库 revision：`0054_policy_optimization`
- 源码 Alembic 单一 head：`0054_policy_optimization`
- `qualification_policy_bundle_v2`：0
- `qualification_policy_activation_v2`：0
- `active_qualification_policy_v2`：0
- `source_stream_admission_decision_v2`：0
- `automated_qualification_decision_v2`：0
- `source_excerpt_version_v2`：0
- `qualification_acceptance_v2`：0
- `content_preparation_candidate_v2`：0
- `ai_summary_state_event_v2`：0
- `publication_decision_v2`：0
- `intelligence_projection_v2`：0
- `visible_intelligence_projection_v2`：0

本地只读调用 `GET /api/v2/feed?limit=100` 返回 HTTP 200、`items=0`。该结果证明正式
v2 Feed 为空，不证明旧 `publication` 表没有历史数据；正式库仍有 37 条旧
`publication` 和 81 条旧 `publication_revision`，它们不是当前 v2 闭环证据。

## 3. 选定 DocumentVersion

| 字段 | 只读事实 |
|---|---|
| DocumentVersion | `019f75b5-b28b-7c28-bdbc-aee6eef0910e` |
| Document | `019f75b5-b28b-778a-a922-dfb27d22db2f` |
| Raw object | `019f75b5-b283-72c5-bf73-96cb6d9f672b` |
| Source | `019b0000-0000-7000-8000-000000000003`（交通运输部） |
| SourceStream | `be4a170d-b36d-7fb5-8579-6009dc36ff86` |
| Fetch run | `019f75b2-3e31-7c71-978e-4279102a9671` |
| 采集时间 | `2026-07-18T14:51:09.765454Z` |
| execution domain | `PRODUCTION` |
| current version | 是 |
| raw/security | `CLEAN`；1 条 CLEAN security fact |
| lifecycle | `RECEIVED → SECURITY_PASSED → READY` |
| 文档类型 | HTML |

选择理由：

1. 来源是明确的官方交通运输来源，SourceStream 具有固定 HTTPS host 边界；
2. fetch、raw capture、DocumentVersion 和安全事实的 production lineage 完整；
3. 题名直接描述隧道工程施工进展，中心新事实优先归为低风险
   `INDUSTRY_UPDATE`；
4. 不以事故原因、责任、处罚或法规效力为中心，避免用高风险内容作为第一条闭环；
5. 它已走到 accepted claims/evidence，但尚未 Event 化，便于区分权威阻断与后续实现
   缺口。

本轮没有读取或输出正文。上述分类只基于公开题名、来源类型和现有低敏感状态，最终
`PrimaryType` 仍必须由当前 qualification 合同产生。

## 4. 第一个确定阻断点

### 4.1 SourceStream 已存在，但不等于 SourceAdmission

选定 SourceStream 当前为 `READY`，API runtime projection 为 `SCHEDULED/HEALTHY`，
source 为 `desired_enabled=true`、`runtime_state=RUNNING`。历史 fetch run 的 transport、
discovery、parse、quality 和总状态均为 `SUCCEEDED`。

这些事实只证明采集边界和运行状态，不授予内容生产资格。

### 4.2 SourceAdmission 历史缺失、当前为 PAUSE

历史 SHADOW pipeline
`019f75c0-b611-77c5-8aee-b4b68ddf4ace` 于
`2026-07-18T15:03:11.652021Z` 启动。当时该 source 的 admission assessment 数量为
0。

当前最新 assessment：

| 字段 | 事实 |
|---|---|
| assessment | `019f7a19-4f9a-7c8a-9cc3-fbe841df6fea` |
| assessed_at | `2026-07-19T11:18:26.874469Z` |
| rule | `civil-source-rollout-v2-engineering-1.0.0` |
| sample size | 0 |
| verdict | `PAUSE` |
| public network safe | false |
| robots allowed | false |
| terms allowed | false |
| copyright reviewed | false |
| hard-negative evaluated | false |

当前 `authorize_model_call`、approved-content success 和 production handoff 均要求最新
`source_admission_assessment_v2.verdict='ADMIT'`。因此该文档在进入当前
autonomous qualification 之前就确定失败关闭。

`source_stream_admission_decision_v2` 在正式库全局也是 0。该表属于受控
SourceStream runtime 决策线；当前 production model gate 实际读取的是 source-level
assessment。两者不能混为一个状态，也都不能由 Owner 意图或旧 SHADOW 事实替代。

### 4.3 缺少 active qualification policy 是第二个独立阻断

即使 SourceAdmission 变为 `ADMIT`，正式库仍没有任何 bundle、activation 或 derived
active policy。迁移 `0054` 只提供 append-only activation ledger、派生 view 和受控
命令，不会凭迁移 revision 自动授予一个策略生产权威。

因此不能把“数据库已到 0054”解释为“AI qualification 已授权”。

## 5. 已到达节点和后续阻断

| 节点 | 选定文档事实 | 结论 |
|---|---|---|
| SourceStream | `READY`；历史 fetch `SUCCEEDED` | 已到达 |
| SourceAdmission | pipeline 启动时不存在；当前 `PAUSE` | **首个确定阻断** |
| active policy | 0 | 已证实的第二阻断 |
| raw object | CLEAN，1 条 CLEAN security fact | 已到达 |
| DocumentVersion | current、`READY`、`PRODUCTION` | 已到达 |
| content outbox | `DEAD_LETTER`，attempt 5，`RUNTIMEERROR` | 历史后续失败 |
| pipeline | `SHADOW/FAILED/RUNTIMEERROR` | 非生产权威，不能发布 |
| AI step | 0 | 没有可复用的 CLASSIFY/EXTRACT/VERIFY 成功事实 |
| qualification decision | 0 | 未到达 |
| claim/evidence | 3/3；均 accepted 且有 typed/anchored locator | 旧 evidence gate 事实，缺少当前 qualification |
| technical exception | 该 DocumentVersion 为 0 | legacy SHADOW dead letter 未进入当前 governed recovery |
| Event membership | 0 | 未到达 |
| SourceExcerpt | 0 | 未到达 |
| summary state/outbox | 0/0 | 未到达 |
| publication decision | 0 | 未到达 |
| publication/revision | 0/0（针对该 DocumentVersion） | 未到达 |
| v2 projection | 全局 0 | 未到达 |
| v2 feed | HTTP 200，0 items | 空 |
| v2 event detail | 没有 event id | 无合法 `{id}` 可查询 |

`source_content_outbox` 的 `RUNTIMEERROR` 是一个已证实的历史后续失败，但错误码过于宽泛，
且 run 是 `SHADOW`、无 AI step、无 current policy binding。SourceAdmission 修复后，
不能据此断言新的 LIVE run 会在同一点失败，也不能直接重放该旧 run。

现有 technical-exception reconciliation 处理 current automated decisions、compensation
和受治理 fetch failure；该旧 SHADOW run 没有 qualification decision，因此没有为选定
DocumentVersion 形成 exception。后续要么增加受治理的历史 current-version
requalification seam，要么等待一个在合法 ADMIT + active policy 下产生的新
DocumentVersion；不得直接把 outbox 改回待处理。

## 6. 当前真实链路

```text
Owner desired_enabled
        │
        ├──不能授予权威────────────────────────────────────────────┐
        ▼                                                         │
SourceStream controller ── raw-first fetch ── raw/capture ── DocumentVersion READY
        │                                                         │
        └── 独立 SourceAdmission latest verdict == ADMIT ◄─────────┘
                                      │
                                      ▼
                         active qualification policy bundle
                                      │
                                      ▼
                       source_content_outbox → LIVE pipeline
                                      │
                                      ▼
                      CLASSIFY → autonomous decision
                          │              │
               AUTO_FILTERED        AUTO_ACCEPTED
                          │              │
                       terminal          ▼
                            EXTRACT → server evidence gate
                                      │
                                      ▼
                         accepted claims ↔ evidence
                                      │
                                      ▼
                                  VERIFY
                                      │
                                      ▼
                        SourceExcerpt + summary state
                                      │
                                      ▼
                      projection refresh outbox
                                      │
                                      ▼
                  PublicationService + automatic authority
                                      │
                                      ▼
                   publication/revision + guarded projection
                                      │
                                      ▼
                    /api/v2/feed + /api/v2/events/{id}
```

选定文档的历史路径在 SourceAdmission 之前由旧 SHADOW seam 分叉，最终落在
`SHADOW/FAILED/RUNTIMEERROR`。它不是当前权威链的完成证据。

### 6.1 当前源码的两个结构性缺口

1. Worker 当前成功路径实际是
   `CLASSIFY → EXTRACT → SUMMARIZE → SUCCEEDED`；虽然 contracts 和旧 orchestration
   仍有 `VERIFY`，production success branch 没有调度独立 VERIFY。
2. 当前 v2 `PublicationService` 会写 `publication_decision_v2` 和
   `intelligence_projection_v2`，但没有为自动 R1 成功创建并绑定传统
   `publication/publication_revision`；Reader projection 也没有 revision guard。

因此“AutomaticEvidenceGate 已经等价替代 VERIFY”和
“projection generation 已经等价替代 publication revision”都尚未被唯一合同证明。

## 7. transfer 六项能力矩阵

| 提交 | 能力 | 当前权威线 | 阶段分类 | 结论 |
|---|---|---|---|---|
| `dd5923a` | deterministic stop/drain | 只有基础 STOPPING；无完整 drain/recovery | 一天运行 | 延期，从当前 head 重实现 |
| `fb86580` | governed failure replay | current technical exception/recovery 已覆盖核心语义 | 已有/删除旧面 | 不移植旧 generic replay |
| `9d7a24c` | SourceStream→Feed 纵向测试 | 当前 `t41` 已有更强隔离 PostgreSQL seam | 已有测试意图 | 只作验收合同参考 |
| `d1d9f25` | pipeline operations status | 当前无 11 阶段 owner dashboard | 一天运行 | 延期，按当前表重做 |
| `8c690ae` | offline acceptance regression | 空过滤 Feed、v2 proxy、clean DB role bootstrap 等已独立修复 | 已有/删除旧补丁 | 只保留回归意图 |
| `8d4d1e0` | 旧 Docker lite | `c0de217 + 42dc786 + a83dda4` 更完整 | 已被取代 | 全部不移植 |

六个 transfer 提交中，没有一个是第一条可信 Event 必须先搬运的代码：

- `fb86580` 的 current-gate recheck、幂等、append-only audit 和 PublicationService
  边界已由 0051 technical exception recovery 覆盖核心场景；
- `9d7a24c` 只证明 fixture/mock 的确定性 seam，不能证明正式来源、正式 AI 或真实发布；
- stop/drain 和 operations dashboard 是一天运行能力，不是用一篇已保存文档完成第一条
  Event 的直接前置；
- 旧 migration/API/UI/Compose 均与当前权威线冲突或已被取代。

## 8. 849 行为规格矩阵

| 行为规格 | 当前状态 | 分类 | 第一条 Event 的要求 |
|---|---|---|---|
| raw-first + canonical SourceAdapter/parser | 核心已有 | 已有 | 保留；按选定 stream 最小补 path/MIME 测试 |
| projection revision guard + invalidation | 只有旧 evidence invalidation；FULL 无 revision guard | 重实现 | 必须 |
| authority epoch + Owner veto | 无 epoch/CAS/veto rebuild 状态 | 重实现 | 必须 |
| automatic publication authority | 无自动 R1 authority/revision 创建 | 重实现 | 必须 |
| VERIFY 原子完成 | enum/旧代码存在，production 未调度 | 重实现 | 必须 |
| EXTRACT issued anchors + 稳定失败码 | 基础 anchor 校验有，closed prompt/稳定码不足 | 重实现 | 必须 |
| 失败 Token/费用结算 | 部分成功后撤权可结算；本地校验失败仍可能 UNKNOWN | 重实现 | 必须 |
| Publisher/Reader 最小 ACL | 部分 direct grants 缺失 | 最小重实现 | 按真实 SQL 依赖补齐 |
| 预算冲突 arbiter | named unique constraint 已满足 ON CONFLICT | 已有 | 不移植 0066/0074 |
| Worker handoff lock | 无窄 `FOR SHARE` current-handoff lock | 重实现 | 随 VERIFY 一起交付 |

### 8.1 应提取的行为，不应复制的实现

- FULL projection 必须绑定 current valid publication revision；revision 切换或文档失效后
  旧 FULL 在 Feed/search/hot/detail 中同时不可见。
- invalidation 必须在同一 event lock/transaction 中删除旧 FULL、使旧 claims/summary
  失效并投递 durable rebuild；旧 claim token 或 epoch 不能写回。
- Owner veto 与 stale context 是 retryable authority condition，不应写成 sticky
  automatic denial；解除 veto 后应只重启一次。
- 自动发布必须由 PublicationService 在数据库中重载当前 SourceAdmission、policy、
  qualification、claim hash、evidence、summary、epoch 和 Owner 决定后 CAS；客户端映射
  不能充当 authoritative context。
- VERIFY 成功必须原子完成 step、current claim provenance、SourceExcerpt、summary、
  approved success、projection outbox、pipeline 和 handoff；任一失败整体回滚。
- EXTRACT 只能引用 server-issued evidence id/block/locator，并返回稳定安全错误码。
- provider 已完成调用但本地 schema/evidence 校验失败时，应结算可验证 Token/费用，且
  不落 raw response 或明文 provider request id。
- Publisher/Reader 只取得完成目标查询所需的 SELECT/EXECUTE；不得扩大表写权限。

## 9. “已有／重实现／延期／删除”归类

### 已有

- 核心 raw-first 和 canonical SourceAdapter/parser；
- current DocumentVersion、安全事实和 accepted claim/evidence 基础模型；
- PublicationService 唯一发布边界；
- technical exception/recovery 的 current-run 核心；
- AI budget `(pipeline_run_id, step, attempt)` 唯一冲突约束；
- v2 Feed/detail 只读 visible projection 的接口骨架；
- a83 的 Docker dev-lite 与 clean-db role bootstrap。

### 重实现

- server-owned SourceAdmission assessment 的可运行入口，以及合法历史 current-version
  requalification/handoff；
- immutable EXTRACT/VERIFY prompt/schema、issued anchors、稳定失败码；
- VERIFY 原子完成和 current handoff lock；
- 失败调用的可验证 Token/费用结算；
- automatic publication authority 和 automatic/human revision XOR；
- projection revision binding、durable invalidation/rebuild、authority epoch 和 Owner
  veto；
- Publisher/Reader 的最小实际 ACL。

### 延期

- deterministic stop/drain、一天运行恢复；
- pipeline operations status/dashboard；
- 849 的 precise controlled-run acceptance、readiness、controlled accounting、
  acceptance campaign 与相关 UI；
- 与第一条 Event 无关的通用运维 replay 产品面。

### 删除或不保留

- transfer 的 0046/0047/0048 migrations；
- `8c690ae` 对旧 0016 migration 的编辑；
- `8d4d1e0` 的全部旧 Docker lite 实现；
- `9d7a24c` 的 caller-supplied authoritative context、内存 publication 和 fixture
  “真实闭环”表述；
- 849 的 0055—0075 migration 文件/编号；
- 0066 diagnostic canary 和仅为其修补的 0074；
- 旧 generic replay API/UI 和旧 operations views SQL。

## 10. 迁移冲突图

```text
transfer（从 8e5bb02 分叉）
  0046 stop/drain
    └─ 0047 governed replay
         └─ 0048 operations status

当前权威线
  0046 owner_gold_prediction_seal
    └─ 0047 owner_gold_override_go
         └─ 0048 autonomous_policy_foundation
              └─ 0049 autonomous_content_switch
                   └─ 0050 autonomous_handoff_state_order
                        └─ 0051 technical_exception_recovery
                             └─ 0052 feed_suppression_projection
                                  └─ 0053 safety_exception_lifecycle
                                       └─ 0054 policy_optimization

849 实验线（共同祖先 11971f6）
  0049* / 0052* / 0054*（revision id 相同、文件语义不同）
    └─ 0055 → ... → 0075
```

transfer 的 0046—0048 与当前同号 revision 是完全不同的业务语义。849 与当前的
0049、0052、0054 甚至具有相同 revision identity、不同 migration 内容：

- 849 的旧 0049 downgrade 错误合并了 INSERT revoke；
- 849 的旧 0052 downgrade 缺少 suppression INSERT revoke；
- 849 的旧 0054 downgrade 缺少当前 API/Worker publication/suppression read revoke。

这不是两个可由 Alembic merge revision 汇合的 heads。数据库可能已经 stamp 同一个
revision id，merge revision 无法检测或修复同名 migration 的语义差异。必须保持当前
0016、0046—0054 原样，从当前 `0054_policy_optimization` 之后创建全新、线性的选择性
迁移。

## 11. 第一条可信 Event 的唯一验收合同

只有同时满足以下条件，才能宣称第一条可信 Event 闭环：

1. 证据对象是真实、production、non-fixture、current DocumentVersion；SourceStream
   边界固定，raw/capture/hash/security lineage 完整且 CLEAN。
2. 模型调用前最新 SourceAdmission 为 `ADMIT`，source/runtime、预算、provider 和
   security gate 在每个 callback 重新验证；Owner intent 不替代任何 gate。
3. LIVE pipeline 在创建事务中绑定 current active immutable policy bundle；SHADOW、
   replay、fixture 和 Owner Gold 不授予生产权威。
4. CLASSIFY 形成唯一 current autonomous decision；只有 `AUTO_ACCEPTED` 可继续。
5. EXTRACT 只使用 server-issued anchors，形成 current accepted claims 与 evidence 的
   双向引用；每个用户可见事实都能回到 locator。
6. VERIFY 读取完全相同的 current accepted claim set 和 evidence provenance；通过后在
   一个事务内形成 SourceExcerpt、summary state、approved success、projection outbox，
   并完成 pipeline/handoff。失败或 superseded 不得留下半成品。
7. PublicationService 在 event lock 下从 PostgreSQL 重载全部权威事实并 CAS
   revision/epoch/hash；成功同事务写 automatic authority、publication revision、
   current revision 和 audit。普通 gate denial 不创建 revision。
8. FULL projection 显式绑定 current valid revision；invalidation、Owner veto 或 revision
   变化后，Feed/search/hot/detail 必须同时失败关闭。
9. `/api/v2/feed` 返回该 event id；`/api/v2/events/{id}` 返回同一 event、DocumentVersion、
   revision 和 accepted-claim fingerprint；页面显示 `human_reviewed=false` 和机器整理
   语义，不暗示人工或政府核验。
10. 验收证据同时包含正式数据库只读 lineage 和本地 API 只读结果；`9d7a24c`、
    `t41`、fixture、mock 或截图只能补充确定性测试，不能替代真实闭环。

## 12. 最小实现顺序

1. **先解除 authority 前置阻断**：不改来源状态；收集并核对当前 robots、terms、
   copyright 和 public-network 一手证据，通过现有 append-only Schema 形成新的
   SourceAdmission。只有证据确实允许时才可为 `ADMIT`。
2. **显式建立 policy authority**：以另行授权激活精确 baseline bundle；不能由 migration
   自动 bootstrap，也不能把 replay/shadow 结果当授权。
3. **先写 current-line characterization tests**：固定选定 DocumentVersion 的历史
   dead-letter 不可直接重放；为合法 current version 建受治理 requalification seam。
4. **实现 EXTRACT/VERIFY**：注册 immutable prompt/schema，补 issued anchors、稳定错误码、
   失败计费与 current-handoff lock；VERIFY 原子完成。
5. **实现自动发布 authority/revision**：PublicationService 重载数据库事实、event lock、
   epoch/hash CAS、automatic/human XOR 和 audit。
6. **实现 revision-guarded projection**：durable rebuild outbox、atomic invalidation、
   authority epoch、Owner veto 和 guarded reader view。
7. **补最小 ACL**：用真实 Publisher/Reader SQL 确定精确 SELECT/EXECUTE，再做对称
   upgrade/downgrade。
8. **最后做真实只读验收**：仅在前述实现和显式运行授权完成后，让一篇 R1
   `INDUSTRY_UPDATE` 通过唯一合同；不得用本轮旧 SHADOW 数据伪造成功。

## 13. 是否需要新迁移

| 范围 | 新迁移 |
|---|---|
| 本轮诊断 | 不需要 |
| 写入新的 SourceAdmission assessment | 现有表足够；不需要 |
| 激活现有、已注册的 policy bundle | 现有 ledger/command 足够；前提是 bundle 已合法注册 |
| 历史 current-version requalification | 优先用现有 outbox/exception Schema；若不扩大状态机可不迁移 |
| EXTRACT/VERIFY prompt/schema registry | 需要 |
| Worker current-handoff lock | 需要 |
| automatic authority + revision XOR | 需要 |
| projection revision FK/guard + rebuild/epoch/veto | 需要 |
| Publisher/Reader 最小 ACL | 需要 |

结论：**需要代码，也需要从当前 0054 之后开始的新迁移；但首个 SourceAdmission 阻断不是
Schema 缺失，不能用迁移伪造 `ADMIT`。**

## 14. 定向测试合同

| 改动 | 先写的失败测试 |
|---|---|
| SourceAdmission workflow | 缺失/PAUSE/显式 hard denial 均不能创建 LIVE run；只有 current ADMIT 可继续 |
| historical requalification | 旧 SHADOW dead-letter 不可直接 reopen；current version + current gates 才创建新 LIVE run，幂等 |
| EXTRACT anchors | 伪造 evidence id/block/locator/excerpt 或双向链接分别返回稳定 safe code |
| failed billing | schema/evidence rejection 结算 sanitized usage 一次；无可验证 billing 才 UNKNOWN；无 raw 泄漏 |
| VERIFY atomicity | 任一步失败整体回滚；post-commit retry 幂等；superseded callback 只结算不落内容 |
| handoff lock | worker 可 lock current `WAITING_AI`，不能 UPDATE；stale handoff 返回空；与 Owner regeneration 互斥 |
| automatic authority | gate denial 无 revision；success 原子写 authority/revision/audit；claim hash/epoch/source 变化导致 CAS 失败 |
| revision XOR | 每个 revision 恰好 human 或 automatic 一种 authority，不得同时或都没有 |
| invalidation/rebuild | revision/文档/claims 变化时 enqueue + delete FULL 原子；旧 token/epoch 不能回写 |
| Owner veto | inflight rebuild 与 veto 竞态失败关闭；解除 veto 后只恢复一次；不写 sticky denial |
| guarded Reader | Feed/search/hot/detail 都只读同一 guarded view，旧 revision 和 vetoed event 均不可见 |
| ACL | 每个实际 login 能完成目标查询；非目标读和全部非授权写失败；downgrade 只撤本迁移 grant |
| budget arbiter | 并发同 `(pipeline, step, attempt)` 只形成一个 reservation；保留可推断 named constraint |
| 真实验收 | 同一 event/revision/claim fingerprint 同时出现在正式 DB、Feed 和 detail；fixture 标记永不通过生产门禁 |

## 15. 明确不应移植

- 不 merge、rebase 或 cherry-pick transfer/849 实验线；
- 不回放 849 的 0055—0075，不覆盖当前 0016、0046—0054；
- 不创建 Alembic merge revision 掩盖同 revision、不同语义；
- 不复制 `8c690ae` 的旧 migration 修改；
- 不移植 `8d4d1e0`；a83 是 Docker 权威；
- 不移植 `9d7a24c` 的 caller-supplied authoritative context 或把 fixture/mock 当真实证据；
- 不移植 transfer generic replay API/UI、旧 operations views 或同号 migrations；
- 不复制 849 的无差别删除 legacy FULL、0066 canary、0074 canary 补丁、acceptance
  campaign/stop-drain/UI；
- 不直接改 `source_content_outbox`、`ai_pipeline_run`、publication status 或
  `alembic_version` 制造闭环；
- 不把当前 3 条旧 accepted claims/evidence 当作 current autonomous qualification 或
  publication authority。

## 16. 本轮验证

按纯文档/诊断风险执行：

- `git diff --check`：通过；
- 文档格式和链接检查：通过；
- 风险分类：`documentation`，`fail_closed=false`，无 unknown path；
- `make check-fast`：Windows PATH 没有 `make`，入口在执行 gate 前失败；
- 按 `check-fast` 计划直接执行同一组 gate：
  - `risk_matrix.py diff-check`：通过；
  - `check_docs.py`：通过；
  - risk-classifier/pytest-partitions 定向测试：`31 passed`。

明确未运行：`check-pr`、`check-release`、`check-live`、Docker、数据库迁移、
fixture replay、E2E/a11y、安全扫描、真实来源和真实模型。
