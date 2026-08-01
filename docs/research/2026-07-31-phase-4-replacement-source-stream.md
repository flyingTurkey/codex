# 第四阶段替代 SourceStream 点时研究

- 核验日期：2026-07-31（Asia/Shanghai）
- 目的：替换第四阶段持续返回 HTTP 521 的中国交建流，只选择一个可完成低风险 `INDUSTRY_UPDATE` 真实闭环的既有候选。
- 边界：本记录不运行模型、不写数据库、不授予 SourceAdmission，也不改变 `desired_enabled` 或正式发布门禁。所有运行前门禁仍须在隔离环境重新核验。

## 先排除 `VERIFIED_RESTRICTED`

ADR-0005 和 Acquisition Context 的当前规则是：robots、条款或版权的显式 `RESTRICTED`、`BLOCKED`、`DENIED`、`DISALLOWED` 或 `FORBIDDEN` 结果必须 `PAUSE`。`apps/api/src/srbg_api/source_registry/v2_rollout.py::review_gate_result` 也把 `RESTRICTED` 映射为 `False`。因此不能把“单 Owner 私有 raw + 题录/短摘/原链”当作权限缩减手段，将既有 `VERIFIED_RESTRICTED` 事实自行改写成 `ADMIT`。

这直接排除四川省交通运输厅建设动态和中国建筑企业动态：二者即使当前 HTTPS 可达，既有机器研究中的版权结果仍是 `VERIFIED_RESTRICTED`。如果权利状态没有新的权威证据改变，SourceAdmission 必须失败关闭。

## 唯一推荐

推荐复用 `ENT-009` 三一集团的既有 SourceStream：

- SourceStream key：`sany-construction-cases`
- Source 注册代码：`ENT-009`
- 仓库种子 Source UUID：`019b0000-0000-7000-8000-000000000039`
- SourceStream UUID：仓库没有既存 UUID；不得把 Source UUID 当成 SourceStream UUID，隔离验收环境应新建并在运行前固定其 UUID。
- 机构：三一集团有限公司（施工机械制造商第一方官网）
- 精确列表 URL：`https://www.sanygroup.com/case/`
- 连接器：`HTML_LIST_DETAIL`
- 预期 MIME：`text/html`
- 既有研究处置：`BOUNDED`、`ADMISSION_READY`
- 既有研究证据：[`t20_crec_sany_source_stream_discovery.json`](../codex-kit/assets/validation/t20_crec_sany_source_stream_discovery.json) 和 [`T20 中国中铁与三一集团 SourceStream 发现验收`](../acceptance/phase-2/t20-crec-sany-source-stream-discovery.md)

T20 验收记录后来因当时 Owner 为对应 rollout 票选择中国建筑/徐工而标记 `SUPERSEDED`；这不改写其中三一流的点时证据或 `ADMISSION_READY` 研究结论，但也不自动恢复运行授权。本阶段只有在当前 Owner 明确选择该唯一替代流后，才能由 SourceAdmission 重新裁决。

### 允许 URL 范围

本轮收紧到比既有研究更小的范围：仅允许主机 `www.sanygroup.com`，且只允许：

- 列表根页：`^/case/$`
- 详情：`^/case/[0-9]+\.html$`

本轮不访问筛选分页、搜索、产品页、图片、CDN、视频、附件或其他栏目。每次重定向都必须重新执行公网地址和路径校验；登录、验证码、WAF 挑战或其他访问限制一旦出现即停止，不得绕过。

当前生产解析器只支持简单 `tag`、`.class`、`tag.class` 或 `#id`，因此可直接执行的声明式配置为：

- `item_selector`: `div.case-list`
- `link_selector`: `a`
- `title_selector`: `h3`
- `published_selector`: 不配置。列表条目没有可见发布时间字段，Nuxt 列表状态中的 `time` 也是空值；不得从图片 URL 推断日期。

`div.case-list` 是有界列表容器；其内部第一个 `a`/`h3` 恰好是当前第一条记录。2026-07-31 已用仓库生产 `ListDetailConnector` 对真实列表验证：只发现一条，URL 为 `https://www.sanygroup.com/case/16504.html`、标题为“STC800C5-8就位 | 助力深大城际机场坪山段白坭坑站工程”、`published_at=None`。这与本阶段只取一篇的上限一致，且不会误扫导航链接。

详情页的完整 CSS 位置为 `.innerWrap .left .detail i.i-time + span`，可见值是 `2026.07.27`。同一详情内嵌 Nuxt 状态还给出 `common_createtime="2026-07-27T08:10:12.000+0000"`；日期权威值应在详情抓取后解析并与可见字段交叉核验。当前通用列表解析器不支持该后代/相邻选择器，不能把它误填为 list `published_selector`。

### 当前可达性

2026-07-31 使用固定研究 User-Agent 点时复核得到：

| 资源 | 结果 |
| --- | --- |
| [施工案例列表](https://www.sanygroup.com/case/) | HTTPS 200，`text/html`，零重定向；公开列表持续给出同主机数字详情 |
| [深大城际白坭坑站工程案例](https://www.sanygroup.com/case/16504.html) | HTTPS 200，`text/html; charset=utf-8`，零重定向；页面/CMS 时间为 `2026-07-27T08:10:12.000Z` |
| [robots.txt](https://www.sanygroup.com/robots.txt) | HTTPS 200，`text/plain`，零重定向 |
| [法律声明](https://www.sanygroup.com/law/) | HTTPS 200，`text/html; charset=utf-8`，零重定向 |

列表、详情、robots 和法律声明可在公开 HTTPS 会话中读取，无需登录、验证码或付费。运行时仍须由 SourceAdmission 重新执行独立 DoH、公网地址、TLS、robots、条款、版权、限速、预算和熔断检查；本次点时复核不能替代该裁决。

### robots、条款与版权边界

- robots：官方 [`robots.txt`](https://www.sanygroup.com/robots.txt) 当前为 200。通配组只禁止 `/case/null?imageMogr2/` 等异常资源路径，未禁止 `/case/` 或 `/case/{numeric_id}.html`。本轮明确不访问被禁止路径。
- 条款：官方[《法律声明》](https://www.sanygroup.com/law/)明确允许个人非商业使用。第四阶段是单 Owner、隔离、非商业研究，不需要绕过访问控制。
- 版权：法律声明同时禁止修改、公开展示、公布或分发。运行边界因此固定为 Owner 私有 raw 和事实核验；Reader 只投影题录、accepted claims、必要短摘和原文链接。禁止图片、附件、视频、全文和修改后内容的再分发。
- 当前 SourceAdmission 语义：既有机器记录将 robots、terms 和 copyright evidence 均记为 `VERIFIED`，而非 `RESTRICTED` 或 `BLOCKED`。在个人非商业、私有 raw、无公开全文再分发的精确用途下，它可以进入 scoped SourceAdmission 复核；如果运行时证据不再支持这一精确用途，必须 `PAUSE`。
- ClaimBasis：所有施工、能力、效率和效果描述只能是 `MANUFACTURER_CLAIM`，不得冒充独立验证。

### 为什么适合低风险 INDUSTRY_UPDATE

研究样本是[“STC800C5-8 就位｜助力深大城际机场坪山段白坭坑站工程”](https://www.sanygroup.com/case/16504.html)：

- 工程类型是铁路/隧道建设，设备是直接用于站点工程吊装的起重机，处于产品既定工程对象和 `CONSTRUCTION_MACHINERY` 范围；
- 中心新事实是施工机械在具体在建工程节点中的应用，不涉及事故原因、责任、法规效力、伤亡或处罚；
- 页面给出稳定原文 URL、CMS 时间、工程对象、设备型号和施工场景，适合形成 evidence locator；
- 安全、性能、效率、难度和效果描述均保留为制造商陈述，只有证据完整且核验通过的最小事实才可成为 accepted claim；否则保持未接受。

目标文档必须由有界列表运行自行发现。上述详情 URL 只是研究样本和类型适配证据，不能由人工写入 publication，也不能绕过列表发现、raw-first、qualification、AI EXTRACT/VERIFY 或 PublicationService。

## 已知风险与停止条件

- 单页 HTML 约 347 KB，含大量导航、产品和营销数据。发送模型前必须只抽取文章主栏并遵守最小文本原则，正文不得写入日志。
- 三一是设备制造商；标题、性能、效率和施工效果具有商业宣传属性，必须固定 `MANUFACTURER_CLAIM`，不得授予 `INDEPENDENT_VERIFICATION`。
- 不抓取页面图片/CDN 资源。发布时间使用页面/CMS 字段，不从图片路径或 URL 猜测。
- 若列表/详情在隔离运行网络出现 401、403、429、5xx、WAF challenge、验证码、跨主机重定向或非 HTML 响应，立即停止，不尝试绕过。
- robots 或法律声明变更、证据无法取得、SourceAdmission 不能对精确用途形成非受限裁决，立即 `NO_GO`。

## 明确不采用的候选

| 候选 | 本阶段处置 | 原因 |
| --- | --- | --- |
| 中国交建 `cccc-project-briefs` | 不合格 | 已在第四阶段多次返回 HTTP 521；继续重试不增加验收价值。 |
| 四川省交通运输厅建设动态 | 不合格 | 既有机器证据把版权结论记为 `VERIFIED_RESTRICTED`；ADR-0005 要求 `PAUSE`。 |
| 中国建筑企业动态 | 不合格 | 虽适合工程节点且当前可达，但既有条款和版权均是 `VERIFIED_RESTRICTED`；ADR-0005 不允许 scoped override。 |
| 中国中铁生产经营 | 不合格 | robots 虽允许，但版权声明明确禁止未经书面许可复制、传播、镜像或存入信息检索系统，与 raw-first 冲突。 |
| 中国煤炭科工 | 不合格 | 既有研究确认法律声明要求复制前取得书面许可，不能推定私有 raw 授权。 |
| 广联达案例 | 不合格 | robots 未发布且用户协议限制爬虫；不得绕过或推定允许。 |
| CAAC 机场司公开 | 不选作本轮唯一候选 | 当前可达且 robots 允许，但没有独立自动访问条款，版权页脚不足以在本轮“来源授权状态不可不明”约束下优于三一。 |
| 《中国公路学报》 | 不选作本轮唯一候选 | 论文版权和研究结论边界更复杂，且中心事实通常是研究发布，不如施工机械工程应用适配低风险行业更新。 |

## 结论

切换来源可以避免继续消耗在中国交建 521 上。第四阶段应只切换到 `sany-construction-cases`，重新冻结 SourceStream UUID、代码 SHA、模型/Prompt/Schema、预算和截止时间后，从列表开始执行一次完整隔离闭环。该推荐是“可进入运行前 SourceAdmission 复核”，不是预先宣告 PASS；只有同一文档完成全链路、Reader 可打开、重放零重复且队列排空，第四阶段才可 PASS。

## 2026-08-01 Owner 授权的同流文档重定向（追加）

原固定文档 `/case/16504.html` 已在不可变真实验收记录中得到
`AUTO_FILTERED`，没有 accepted claims。Owner 随后明确授权降低诊断和代码量，
在不改变生产资格规则的前提下，继续使用同一个
`sany-construction-cases` SourceStream，重新固定一篇中心工程事实更明确的文档。
该授权不改写原 NO_GO，也不授权第二来源、Prompt/Schema/模型变更、人工发布或
第五阶段。

新的精确列表 URL 是
`https://www.sanygroup.com/case/dlid-7/gongclx-/year-/`。它是原 `/case/`
公开列表内的“桩工机械”筛选路径，仍位于既有 `/case/` 授权前缀内。2026-08-01
通过平台独立 DoH、公共地址校验、TLS 和进程级 SOCKS 只读复核，并使用仓库生产
`ListDetailConnector` 与原声明式选择器验证：该列表 HTTPS 200，恰好发现一条
`https://www.sanygroup.com/case/16434.html`，标题为“旋挖施工案例 |
广州市增城区新塘站综合交通枢纽一体化工程”。

详情页同样 HTTPS 200、`text/html; charset=utf-8`，无登录、验证码或跨主机
重定向；页面可见日期为 `2026.06.30`。不记录正文的结构信号检查确认页面包含
旋挖钻机、综合交通枢纽、新塘站、施工、建设和铁路语义。中心事实因此比原
“就位/助力”标题更明确地表达施工机械直接参与在建工程，但所有施工、能力和
效果描述仍只能作为 `MANUFACTURER_CLAIM`，是否形成 accepted claims 继续由
冻结的生产 qualification、EXTRACT/VERIFY 和 PublicationService 决定。

这次只读选文没有模型调用、数据库写入或发布。运行前仍必须固定新代码 SHA、
同一 SourceStream ID、该精确列表和详情 URL、既有 provider/model/Prompt/Schema、
预算、截止和最大重试，并重新执行 SourceAdmission。只有完整 live、Feed/Reader、
重放零重复和排空全部通过，第四阶段才可 PASS。
