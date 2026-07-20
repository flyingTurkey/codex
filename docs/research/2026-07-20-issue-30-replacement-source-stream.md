# Issue #30 替代来源研究：《建筑科学与工程学报》+ 中国交建

- 替代票：GitHub Issue #39，父 Spec #1，supersedes #30
- 核验时间：2026-07-20（UTC 观察终点 `2026-07-20T03:52:15.6076920Z`）
- 目标：替换中国建筑科学研究院受法律与持续集合阻断的研究来源角色，不改变中国交建既有有界流，不增加运行授权。

## 第一性原理筛选标准

替代源必须同时满足：官方且身份唯一；直接覆盖房屋建筑、市政或其他十一类在域工程技术；存在 HTTPS、持续、可枚举的 list/detail 或等价 API；公网、重定向、robots、条款、版权和公开访问均可形成非 UNKNOWN 点时证据；研究结论不得冒充独立验证；raw-first 与公开投影版权边界可失败关闭。仅有首页、搜索结果、单篇材料或二手聚合不合格。

## 候选比较

| 候选 | 结论 | 主要证据或阻断 |
|---|---|---|
| 《建筑科学与工程学报》 | `BOUNDED + ADMISSION_READY` | 官方页明示教育部主管、长安大学主办、编辑部出版；同源当前刊期与文章列表 JSON 可持续枚举；HTTPS 可达；robots 404 只记“未发布”；版权限制由私有研究、题录/短摘/原链和禁再分发约束承接。 |
| 《土木工程学报》 | `BOUNDARY_DISCOVERY`，淘汰 | 官方旧卷目录可枚举，但浏览器报告 `NET::ERR_CERT_COMMON_NAME_INVALID`；未绕过证书错误。 |
| 《建筑材料学报》 | `BOUNDARY_DISCOVERY`，次选未采用 | HTTPS 当前期与详情稳定，但 robots、条款和版权未完成同门槛核验，且大量纯材料性质内容对工程对象直接相关率较低。 |
| 《建筑结构学报》 | `UNKNOWN`，淘汰 | 只确认中国建筑学会主办介绍，未核验到当前官方 HTTPS 持续 list/detail；第三方订阅站不得作为一手来源。 |
| 《建筑科学》 | `UNKNOWN`，淘汰 | 只确认主办身份，未核验到编辑部官方、当前且持续的 HTTPS list/detail；二手聚合与未完成身份核验的路径不采用。 |

## `RES-013`《建筑科学与工程学报》有界流

- canonical identity：`建筑科学与工程学报`；accountable publisher：编辑部（长安大学主办）。与 `RES-004` 中国公路学报、`RES-011` 中国土木工程学会不是同一机构。
- 官方阅读入口：`https://jace.chd.edu.cn/homeNav?lang=zh`，点时显示 2026 年第 43 卷第 3 期。
- 当前刊期 API：`GET https://jace.chd.edu.cn/rc-pub/front/front-period/getFirstTwoPeriods?publicationIndexId=1474`。
- 文章列表 API：`GET https://jace.chd.edu.cn/rc-pub/front/front-article/getArticlesByPeriodicalIdGroupByColumn/{period_id}?size=50&showCover=true`；`period_id` 只能来自前一响应，`size` 最大 50，禁止任意 query 扩张。
- 连接器：`JSON_CURRENT_ISSUE`；预期 MIME `application/json`；每日一次；每分钟最多一次；10 秒超时；最多 5 次、逐跳复核的同主机重定向。
- 点时网络：解析观察值 `28.0.0.136` 为 global 且非 private/loopback/link-local/metadata；该事实不替代 SourceAdmission 每次请求前的 DNS 与重定向复核。
- robots：`/robots.txt` 点时 404。只记录未发布，不推定许可。
- 条款/版权：官方投稿指南保留论文版权与编辑部权利，未获得全文或附件再分发许可。只允许未来 SourceAdmission 评估 Owner 私有非商业 raw-first；Reader 最多题录、accepted claims、必要短摘和原链；图片、附件、全文及公开再分发均禁止。
- 内容门禁：论文必须直接涉及十一类工程对象之一及规划、设计、施工、运营、养护、安全、监测或数字化研究事实；排除纯材料化学且无工程对象、期刊公告、征稿、会议和排行。
- ClaimBasis：只允许 `RESEARCH_CONCLUSION`。同行评审和期刊出版不等于平台 `INDEPENDENT_VERIFICATION`。

浏览器同源 fetch 已观察两个 JSON 端点为 200；本次没有同步固化官方原始响应字节，因此 `response_sha256` 诚实保存为 `null`，不使用 DOM、截图或自行重序列化 JSON 冒充 raw hash。

## `ENT-001` 中国交建复用边界

沿用 #30 已核验的 `https://www.ccccltd.cn/news/jcxw/jx/` 列表、分页及同目录详情边界，不重复建源或扩大到集团综合新闻。只接受在域工程对象与中标、开工、合龙、贯通、完工、验收、通车、投运等项目新事实；排除经营业绩、资本市场、党建、人事、招聘、会议和品牌宣传。项目节点为 `PROJECT_FIRST_PARTY_RECORD`，企业效果自述最多为 `MANUFACTURER_CLAIM`，均非独立验证。

## 研究结论与诚实边界

两流形成研究态 `BOUNDED + ADMISSION_READY`，足以完成 #39 的发现范围并替代 #30 的受阻席位。它们仍是 `CANDIDATE + disabled`，`desired_enabled=false`、`source_admission=null`、`actual_running=false`，不追加 `PAUSE`，不授予覆盖信用，不产生 Owner Gold、DeepSeek 成功、真实观察窗口或 GO。未来准入仍必须由服务端完整执行公网、重定向、robots、条款、版权、限速、预算、熔断、raw-first、PublicationService 与 R3/R4 门禁。
