# Handoff：土木工程情报 v2 共同理解与 to-spec 输入

日期：2026-07-19
状态：`to-spec=READY`
运行状态：`ENGINEERING_CLOSEOUT=NO_GO`、`PRODUCTION_CLOSEOUT=NO_GO`

## 1. 结论

产品目标、领域边界、证据规则、AI 降级、阅读投影、来源扩充和测试边界已经形成共同理解，没有仍需 Owner 决策的产品问题，可以进入 `to-spec`。

`to-spec=READY` 只表示规格输入完整。工程与生产 closeout 的 `NO_GO` 是当前真实运行证据结论，继续阻止生产切换、来源启用和 GO 声明，但不阻止编写下一轮 Spec。

本轮只合并和校正共同理解，没有修改业务代码、启用来源、运行采集、复活 v1 内容或执行投影切换。

## 2. 权威顺序

发生冲突时按以下顺序解释：

1. Owner 已确认的产品决定、根 [AGENTS.md](../AGENTS.md)、[CONTEXT-MAP.md](../CONTEXT-MAP.md) 及四个 bounded context；
2. `packages/contracts`、v2 API、PublicationService 和正式 Nuxt 页面所表达的当前实现事实；
3. ADR 中难以逆转且有真实取舍的决定；
4. 验收记录、诊断 handoff、来源研究和 prototype 结果，它们分别说明运行证据、候选研究或设计探索，不得反向改写产品领域。

来源研究中的六类工程对象是 dated `SourceCoverageMatrix`，不是 `EngineeringObject` 全集；prototype 选择 B 是正式重建输入，不代表 B 已经进入生产页面；campaign 的 20 个机构是验收与战略组合，不是已准入的 SourceStream。

## 3. 冻结的产品与领域模型

### 3.1 产品形态

- 单一 Owner 使用的个人土木工程行业情报平台，不新增企业模式或多用户远程认证。
- 首要目标是高相关度、有证据、可阅读；先提高分类精度，再扩充来源，不以采集数量作为成功替代指标。
- 三种内容复用同一 Feed、Card、Event 详情契约和 Nuxt 组件体系。

### 3.2 三个正交分类轴

`EngineeringObject` 固定为十一类：

- `HIGHWAY`：公路；
- `RAILWAY`：铁路；
- `BRIDGE`：桥梁；
- `TUNNEL`：隧道；
- `BUILDING`：房屋建筑；
- `MINING`：矿山工程；
- `MUNICIPAL`：市政工程；
- `WATER_CONSERVANCY`：水利工程；
- `PORT_WATERWAY`：港口与航道工程；
- `AIRPORT`：机场工程；
- `ENERGY`：能源工程。

`SpecialtyFacet` 首期只有 `TUNNEL_GAS_MONITORING`，必须与公路或铁路隧道组合；矿井瓦斯归入 `MINING`，不能补交通隧道瓦斯监测覆盖。

`EquipmentDomain` 首期只有 `CONSTRUCTION_MACHINERY`；设备必须直接用于上述工程对象的规划、设计、施工、运营、养护、安全、监测或数字化活动。制造企业 ERP、生产线改造或泛工业互联网不会仅因厂商生产工程机械而进入该域。

`DirectRelevance` 必须同时满足：正文以在域工程对象或施工装备为中心，并包含影响其工程生命周期活动的实质性新事实。来源栏目、机构权威性或关键词命中不能单独决定相关性。

### 3.3 类型与热点

每个 Event 只有一个 `PrimaryType`：

- `DIGITAL_TRANSFORMATION`；
- `SAFETY_INTELLIGENCE`；
- `INDUSTRY_UPDATE`。

交叉属性只作标签。`INDUSTRY_UPDATE` 是中心新事实既不以数字化转型为主、也不以安全情报为主的直接相关工程行业更新，不包含泛政策、泛经济、消费、旅游、健康、金融行情或泛 AI 新闻。

热点不是第四种类型，而是服务端保存规则版本的永久派生授予：七天内至少两个去转载后的独立合格来源，或单一权威一手来源内部得分至少 70。普通阅读面只显示触发路径、独立来源数和理由，不显示总分。

### 3.4 内容形态与分类失败

- 数字化允许项目案例、研究、概念和产品，不新增成熟度枚举或 `DEPLOYED+` 阅读门禁。
- “已部署”“产生成效”“已独立验证”只能由 accepted claims、证据和 `ClaimBasis` 表达。
- 分类失败、低置信、主类并列或受限风险进入非公开 `QualificationReviewCase`；分类通过前不得创建普通阅读面可见 Event。
- 模型可以提出候选，不得写风险等级、复核结论、发布状态或热点授予。

## 4. 冻结的内容处理与证据链

权威顺序为：

`RawResponse → MIME 解析 → DirectRelevance 门禁 → candidate facts → AcceptedClaims → SourceExcerpt → AISummary → PublicationService → Reader Projection`

- 原始响应及内容哈希先保存；HTML、PDF、RSS 和附件按真实 MIME 解析，失败不破坏原始证据。
- `materialize_local()` 之类的采集物化只能形成候选，不能预建主类型、Event 或个人 Feed 投影。
- `AcceptedClaim` 必须绑定同一来源版本中的证据定位，并保留双向引用；未接受、已失效或无证据的候选不能进入用户可见字段。
- `SourceExcerpt` 是支持 active AcceptedClaims 的一段连续原文，最多 500 个中文字符，只允许最小必要上下文。规范术语固定为“原文摘录”，不再使用含混的“原文简述”。
- `AISummary` 是 300–500 个中文字符的解释性内容，组织为“发生了什么／工程影响与意义／限制与待跟踪”；事实段逐段引用 AcceptedClaims，判断必须单独标识。AI 输出不是证据。
- 原文变更、撤回或更正后，相关 claims 和摘要必须失效或进入复核；旧版本不得静默回填。
- 法规效力、事故原因、责任、处罚和最终整改结论是 `AuthorityReservedClaim`，只能由有权机关原文形成 accepted claim。
- 初报、续报和最终调查通过后续关系连接，不能简单去重；厂商声明、研究结论、项目第一方记录、独立验证和权威认定使用明确 `ClaimBasis`，不能互换。

## 5. AI 运行与用户降级

“已配置”和“可用”是两个独立事实：

- 已配置表示当前 provider/model/secret 等配置存在；
- 可用要求 60 秒内 worker 心跳、实际 provider/config 匹配、密钥/预算/队列正常，并在要求窗口内存在一次真实、Schema 合法的批准模型调用；
- `RuntimeAuthorization` 必须在消费模型结果前由服务端按当前来源、文档、安全、执行域和预算重新核验；撤权后不能读取、修复或发布既有模型输出；
- mock 只用于协议等价 CI，非测试环境不得把 mock、probe 或网络可达性计为 `RealSchemaSuccess`。

单条摘要状态固定为：

`NOT_GENERATED / PROCESSING / TEMPORARILY_UNAVAILABLE / SCHEMA_REJECTED / INSUFFICIENT_EVIDENCE / SUCCEEDED / STALE`

AI 未调用、调用失败、Schema 失败或证据不足都不得隐藏已经通过证据门禁的内容。页面继续展示原文摘录与来源，并显示对应的确定性状态说明；恢复后通过 durable handoff 自动补偿。事实复核与 AI 解读复核独立记录。

已验证的 0036 事实：历史伪 `WAITING_AI` 从 10 条归零；pipeline/outbox 终态可原子收口；授权撤销时 fail closed；runtime probe 的时间参数与模型映射已修复。当前仍为 `configured=true`、`available=false`，因为没有 `ADMIT + RUNNING` 来源、CLEAN 当前 TRIAL/PRODUCTION 文档或真实 Schema 成功；七条缺失可信 provider usage 的历史 `RESERVED` 预算不得补造 Token 或费用。

## 6. 冻结的普通阅读投影

### 6.1 接口边界

土木工程情报读取使用：

- `/api/v2/feed`、`/api/v2/search`、`/api/v2/hotspots`；
- `/api/v2/events/{event_id}`；
- `/api/v2/events/{event_id}/appendix`；
- `/api/v2/media/{media_id}/preview|download`；
- `/api/v2/review/cases...`。

saved/daily、引用、版本/diff、关系纠正、来源管理和 AI 设置等未改造能力继续使用 v1。

### 6.2 投影边界

- `FULL`：标题、主类型/facets、来源及官方性、两个时间、原文摘录、AI 总结及状态、ClaimBasis、热点理由、原文链接、许可媒体和附件，以及必要的更正提醒。
- `R3_METADATA`：标题、主类型、官方来源、两个时间、原文链接和待审核状态；正文、claims、证据、媒体与 AI 内容不投影。
- `R4`、分类未决和 claim 门禁失败：普通接口返回 404；Owner 隔离面只返回安全元数据与隔离原因。
- “官方一手来源”和“已人工复核”必须独立展示；不能合并为“官方已核验”。
- 服务端完成 R3/R4 ACL，前端不能先接收完整内容再隐藏。

### 6.3 Owner Reader 决定

Owner 已选择 B：宽屏为“正文主栏 + 受约束的 sticky 上下文侧栏”，窄屏恢复单列语义顺序。标题与更正提醒在首屏；正文主栏按“原文摘录 → AI 总结 → 图片 → 附件及原文动作”；诊断、证据、关系、更正历史和 Owner 纠正位于底部且默认折叠。

此决定是正式 Nuxt 重建输入。当前 `apps/web/app/pages/events/[id].vue` 仍是单列第一版，不能把 prototype fixture、组件或截图提升为生产依赖。

## 7. 来源扩充的共同理解

- 来源按机构计数，栏目或有界集合路径是 SourceStream；Source 与 SourceStream 不得混称。
- 36 条研究记录只是来源/入口/样本候选。`SourceResearchDisposition = ADMISSION_READY | BOUNDARY_DISCOVERY | MANUAL_SHADOW` 只路由后续研究，不授予采集或运行权限。
- 本轮来源报告只对公路、铁路、桥梁、隧道、房屋建筑、矿山及两个跨切面形成 `SourceCoverageMatrix`。其余五类没有本轮覆盖信用，但仍在产品范围内。
- 0037 campaign 的 20 个机构是工程验收和战略组合；当前 20/20 均为 `PAUSE`、样本为零且 `hard_negative_evaluated=false`，不能视为 20 条已准入流。
- 来源仍按 `10 → 20 → 30–50` 分批，每次启用两个；每波至少 72 小时并满足样本量，首批整体观察 14 天。20 源未达标前不扩到 30–50。
- 每个目标路径启用前重新核验公网安全、robots、条款、版权、重定向、限速、预算和熔断；任何未知或硬门禁失败都保持停用。
- 单源验收目标：抓取至少 98%，解析及证据定位至少 95%，元数据至少 98%，有效相关产出至少 50%，重复率不高于 30%，锁定负例零泄漏。硬门禁失败立即暂停；软指标连续两个 14 天窗口失败则退役。

## 8. 质量、测试和验收边界

- 版本化 gold corpus 为 360 例：180 正例、90 边界例、90 负例；三个主类型各至少 60 个正例，并覆盖十一类工程对象和两个跨切面。
- 候选分类 precision 与 recall 都至少 90%；最终 Feed 人工抽检 200 条且 precision 至少 98%；中医药、泛健康、旅游消费、金融行情和泛 AI 等锁定负例零泄漏。
- 四个最高层级 seam：纯领域规则与 claim 约束；v2 契约/ACL/空投影/只读归档；真实 PostgreSQL、Redis、对象存储下从 HTML/PDF/RSS 到 PublicationService 的 durable 集成与完整 AI 失败矩阵；Nuxt E2E 覆盖阅读、搜索位置、投影、媒体与折叠附录。
- `ENGINEERING_CLOSEOUT` 与 `PRODUCTION_CLOSEOUT` 的双 profile 语义由 ADR-0003 固定；campaign 命令、采样 cutoff、故障注入编排和当前证据属于可逆实现与运行记录。

## 9. 当前实现事实与下一份 Spec 必须收口的差距

| 范围 | 已验证事实 | Spec 必须处理 |
|---|---|---|
| v2 基线 | 三主类型、十一对象/facets、FULL/R3、v2 API、空投影、复核命令、热点和媒体契约已存在 | 保持严格联合和服务端 ACL，不另建第二套内容体系 |
| SpecialtyFacet 不变量 | `TUNNEL_GAS_MONITORING` 枚举已存在 | 当前分类 Schema、Pydantic 输出和 FULL facets 只限制枚举/长度，未强制同时包含 `TUNNEL` 与 `HIGHWAY|RAILWAY`；Spec 应让分类输出、Owner facet 修正和 PublicationService 共用同一领域不变量及回归测试 |
| DeepSeek | 0036 已闭合伪等待与撤权断链，runtime probe 健康 | 在合法来源与文档前置成立后取得真实 Schema 成功，并覆盖七状态和补偿 UX；不得重做 0036 |
| 工程 campaign | 0037、双 profile 和只读证据链已存在；当前真实结论为 NO_GO | 新活动必须诚实补足观察窗口、真实成功、Feed、locked-negative 与补偿证据；旧活动缺口不能改写 |
| 来源 | 36 条研究候选和三种 disposition 已形成 | 逐路径执行 SourceAdmission；不要把研究清单或 20 源 campaign 当作启用清单 |
| Reader | B 方案已由 Owner 确认 | 正式 Nuxt 页仍需按 B 重建；明确桌面/移动顺序、动作去重、附录状态和可访问性 |
| FULL 契约 | 已有 facets、source official、SourceExcerpt、AISummary、ClaimBasis、hotspot、媒体/附件 | 增加普通阅读面的人工复核状态；为 AI 总结建立逐段 claim 引用结构，并把当前 `body` 最少 30 字收紧为已确认的 300–500 字规则 |
| 正式页面 | 已能读取 FULL/R3 并延迟加载 appendix | 仍未展示 facets、ClaimBasis、热点理由/来源数、官方与人工复核双状态、判断标识；R3 未显示 official source |
| ReaderAppendix | v2 当前有 claims、evidence、automatic results、已审核 relationships 和字符串 corrections；v1 保留自动关系读取/纠正 | Spec 必须明确组合保留的 v1 能力或扩展 v2 appendix，并补足结构化更正历史及 Event→ReviewCase 只读上下文，不能假设现契约已经具备 |
| 旧来源枚举 | `SourceIndustry` 尚缺 `MINING`，旧 `DiscoveryTopic` 只覆盖七类 | 作为迁移/兼容 seam 进入 Spec，不能据此缩窄十一类 v2 产品模型 |

## 10. 本轮明确不做

不增加额外工程领域、独立法规/工法/招标库、内部数据、第二模型、模型微调、通用聊天/RAG、多用户远程认证、旧角色清理、付费墙采集、全文再分发、数字成熟度、可见热点总分、React 或第二组件库；不在本轮执行生产迁移、启用来源、修复真实运行 NO_GO 或把 prototype 提升为生产代码。

## 11. to-spec 输出要求

下一步可以直接进入 `to-spec`，无需继续产品访谈。Spec 应至少产出：

1. 统一 Event FULL/R3 契约增量与兼容策略，包括普通阅读人工复核状态和逐段 claim 引用；
2. B 方案正式 Nuxt 信息架构、响应式顺序、状态文案、媒体/附件与 appendix 交互；
3. 领域与来源旧枚举迁移 seam；
4. API/PublicationService/AI 补偿/Reader 的验收矩阵及分阶段纵向切片；
5. 明确区分“规格完成”“工程 GO”“生产 GO”的验收口径。

如实现中发现事实性矛盾，应回到对应 Context 或契约核验；只有出现新的、会改变产品行为的真实取舍才重新询问 Owner。

## 12. 必读输入

- [Intelligence Qualification Context](contexts/intelligence-qualification/CONTEXT.md)
- [Acquisition Context](contexts/acquisition/CONTEXT.md)
- [Evidence & AI Context](contexts/evidence-ai/CONTEXT.md)
- [Publication & Reader Projection Context](contexts/publication-reader/CONTEXT.md)
- [ADR-0002](adr/0002-api-v2-empty-projection-cutover.md)
- [ADR-0003](adr/0003-intelligence-v2-closeout-profiles.md)
- [v2 验收记录](acceptance/phase-2/intelligence-quality-reader-v2.md)
- [DeepSeek 诊断 handoff](srbg-deepseek-no-results-return-handoff-2026-07-19.md)
- [工程 closeout handoff](srbg-intelligence-v2-engineering-closeout-handoff-2026-07-19.md)
- [权威来源扩充研究](research/2026-07-19-civil-engineering-authoritative-source-expansion.md)
- [Owner Reader to-spec handoff](srbg-intelligence-v2-owner-reader-to-spec-handoff-2026-07-19.md)
