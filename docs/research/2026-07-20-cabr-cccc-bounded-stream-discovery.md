# 中国建筑科学研究院与中国交建 SourceStream 发现（Issue #30）

> **SUPERSEDED：** 该组合已由 Issue #39 的《建筑科学与工程学报》+ 中国交建替代。下文继续作为中国建研院 `NO_CONTINUOUS_COLLECTION` 与 `TERMS_PROHIBIT_COPYING` 的原始证据，不得把 #30 的关闭解释为 blocker 已解除。

- GitHub Issue：[#30](https://github.com/flyingTurkey/codex/issues/30)（v2 T29）
- 父 Spec：#1
- 最终点时观察：`2026-07-20T03:14:18.0272444Z`
- 范围：只研究 `RES-003` 中国建筑科学研究院和 `ENT-001` 中国交建；不执行 SourceAdmission、采集、样本评估或运行波次。

## 结论

Issue #30 **不能按关闭条件关闭**。中国交建“简讯”可以形成精确的 `BOUNDED + ADMISSION_READY` 工程项目流；中国建筑科学研究院当前官网只有陈旧的静态成果汇总，没有可重复分页/详情边界或持续更新信号，而且法律声明明示未经书面许可不得复制、传递网站文字等内容，与平台 raw-first 私有保存直接冲突。因此中国建研院应保持 `CANDIDATE + MANUAL_SHADOW`，不能为了关闭工单强行提升为 `BOUNDED + ADMISSION_READY`。

`ADMISSION_READY` 只表示有界集合可提交后续 SourceAdmission Probe，不表示 robots、条款、版权、频率、预算或运行门禁已经通过。两个 Source 都必须保持 `desired_enabled=false`、`source_admission=null`、`actual_running=false`，不得追加 `PAUSE`、运行窗口、覆盖信用或 GO 证据。

| Source | 研究结论 | 精确入口 | ClaimBasis |
| --- | --- | --- | --- |
| `RES-003` 中国建筑科学研究院 | `CANDIDATE + MANUAL_SHADOW` | 静态候选：[科研成果—获奖情况](https://www.cabr.cn/zgjyy/kjbzx/kycg/hjkq/A019003003002Gone1.html)；参考：[科研项目](https://www.cabr.cn/zgjyy/kjbzx/kycg/kjxm/A019003003001Gone1.html) | 研究标题/结论只可标 `RESEARCH_CONCLUSION`；研究院对应用效果、产品或装备能力的描述标 `MANUFACTURER_CLAIM`；奖项列表本身是机构自报，未回到授奖机关前不得标 `INDEPENDENT_VERIFICATION` |
| `ENT-001` 中国交建（alias：中国交通建设集团） | `BOUNDED + ADMISSION_READY` | [新闻中心—子公司报道—简讯](https://www.ccccltd.cn/news/jcxw/jx/) | 工程节点事实标 `PROJECT_FIRST_PARTY_RECORD`；规模领先、效果、效益、首创等企业表述标 `MANUFACTURER_CLAIM`；均不得冒充 `INDEPENDENT_VERIFICATION` |

## `RES-003` 中国建筑科学研究院

### 入口、边界和状态建议

仓库旧 origin `https://www.cabr.com.cn/` 在本次浏览器观察中以 `ERR_CONNECTION_CLOSED` 失败；当前公开官网及页脚主体均为中国建筑科学研究院有限公司，建议 canonical origin 更新为 `https://www.cabr.cn/`，但不得因此新建第二个 Source。

- 静态候选入口：`https://www.cabr.cn/zgjyy/kjbzx/kycg/hjkq/A019003003002Gone1.html`
- 参考静态页：`https://www.cabr.cn/zgjyy/kjbzx/kycg/kjxm/A019003003001Gone1.html`
- 允许主机候选：仅 `www.cabr.cn`
- 候选路径：`^/zgjyy/kjbzx/kycg/(?:hjkq/A019003003002Gone1|kjxm/A019003003001Gone1)\.html$`
- 连接器：当前只能是 `STATIC_HTML_MANUAL`，不能写成 `HTML_LIST_DETAIL`
- 预期 MIME：`text/html`
- 自动频率：`unavailable`；`MANUAL_SHADOW` 下不得安排自动轮询。若取得书面许可并找到持续集合，后续研究可从 1440 分钟候选值重新评估，不能把该建议写成授权。
- 策略版本建议：`t29-cabr-research-results-boundary-v1`
- `readiness=CANDIDATE`
- `disposition=MANUAL_SHADOW`
- `blocker_codes=["NO_CONTINUOUS_COLLECTION", "TERMS_PROHIBIT_COPYING"]`
- `content_relevance=FILTERED`
- `claim_basis_policy=RESEARCH_CONCLUSION`
- `permitted_claim_bases=[RESEARCH_CONCLUSION, MANUFACTURER_CLAIM]`
- `public_redistribution=false`

### 为什么不是持续 SourceStream

[科研项目](https://www.cabr.cn/zgjyy/kjbzx/kycg/kjxm/A019003003001Gone1.html)是一个单页表格，只列“十二五”国家科技支撑计划和“十三五”国家重点研发计划承担项目；没有分页、条目详情链接、逐条发布日期或当前计划期更新信号。[获奖情况](https://www.cabr.cn/zgjyy/kjbzx/kycg/hjkq/A019003003002Gone1.html)虽有可重复的年度/奖励类别/项目名称/等级行，但年度仅为 2005、2010—2021，条目没有详情链接，点时未见 2022 年以后的更新。二者可作为人工术语与历史基线，不能把静态汇总页冒充持续流。

若未来找到同机构官方、公开、持续更新的科研成果列表，内容仍须限定为房屋建筑、市政或其他十一类在域工程对象，排除泛机构动态、党建、人事、会议和仅有荣誉宣传而无工程技术新事实的内容。

### 公网、robots、条款和版权

- DNS 观察：`www.cabr.cn -> 28.0.0.83`；仓库旧主机 `www.cabr.com.cn -> 28.0.0.88`。Python `ipaddress` 对两个点时地址均判定 `is_global=true`、非 private/loopback/link-local。该环境可能使用合成 DNS，故这只是点时拒绝私网目标的证据，不是源站归属证明；后续每跳仍须重新解析和校验。
- HTTP：`http://www.cabr.cn/` 返回 `301` 到同主机 `https://www.cabr.cn/`；HTTPS 首页、科研项目和获奖情况分别返回 `200`，集合页为 `text/html; charset=utf-8`，没有跨主机重定向。
- [`robots.txt`](https://www.cabr.cn/robots.txt) 返回 `404 text/html`（点时响应体 388 字节）。浏览器会呈现站点首页样式的错误页，不能据此把 404 误记为 200；404 绝不推定允许自动访问。
- [法律声明](https://www.cabr.cn/zgjyy/flsm/A019009Gone1.html)说明网站信息只供参考、不得用于商业用途；知识产权条款进一步规定，未经公司事先书面明确允许，网站文字、视像、声音、图形和图像不得以任何形式或方式复制或传递，且未经书面允许不得设置超链接。raw-first 保存完整 HTML 本身涉及复制，默认原文链接流程还触及其超链接条款，因此在取得书面许可前必须失败关闭为人工影子。
- 公开页面无需登录、验证码或付费墙；本次没有使用站内搜索、未公开接口、登录服务或内部图书馆地址。

## `ENT-001` 中国交建

### 可直接写入 manifest 的流字段建议

- `registry_code=ENT-001`
- `institution=中国交建`
- `official_origin=https://www.ccccltd.cn/`
- `aliases=["中国交通建设集团", "中国交通建设集团有限公司", "中国交通建设股份有限公司"]`；简称与全称映射到同一个 Source，不能重复建源。
- `stream_key=cccc-project-briefs`
- `collection_url=https://www.ccccltd.cn/news/jcxw/jx/`
- `collection_path_pattern=^/news/jcxw/jx/$`
- `allowed_hosts=["www.ccccltd.cn"]`
- `allowed_path_patterns=["^/news/jcxw/jx/(?:index(?:_[1-9][0-9]*)?\\.html)?$", "^/news/jcxw/jx/[0-9]{6}/t[0-9]{8}_[0-9]+\\.html$"]`
- `connector_type=HTML_LIST_DETAIL`
- `expected_mime_types=["text/html"]`
- `poll_interval_minutes=1440`（保守候选值，不是运行授权）
- `request_timeout_seconds=10`
- `max_redirects=5`
- `rate_limit_requests_per_minute=1`
- `user_agent=SRBG-SourceResearch/1.0 (+personal noncommercial research)`
- `policy_version=t29-cccc-project-first-party-v1`
- `readiness=BOUNDED`
- `disposition=ADMISSION_READY`
- `blocker_codes=[]`
- `source_admission=null`
- `actual_running=false`
- `content_relevance=FILTERED`
- `claim_basis_policy=PROJECT_FIRST_PARTY_RECORD`
- `permitted_claim_bases=[PROJECT_FIRST_PARTY_RECORD, MANUFACTURER_CLAIM]`
- `public_redistribution=false`

### 集合与内容边界

[“简讯”集合](https://www.ccccltd.cn/news/jcxw/jx/)由官网导航“新闻中心 → 子公司报道 → 简讯”自然到达。它每页 10 条，分页为 `index.html`、`index_1.html`……，点时尾页为 `index_299.html`；详情稳定采用 `/news/jcxw/jx/YYYYMM/tYYYYMMDD_ID.html`。列表和详情都有发布日期，且连续提供中标、开工、合龙、贯通、完工、交工/竣工验收、通车/投运等工程项目新事实，满足有界列表—详情流要求。

正向过滤要求同时命中在域对象和工程生命周期事实。在域对象包括公路、铁路、桥梁、隧道、房屋建筑、矿山、市政、水利、港航、机场、能源工程；生命周期信号包括规划、设计、施工、开工、中标、贯通、合龙、封顶、完工、验收、通车、投运、运营、养护、安全、监测、数字化、智能建造和直接用于工程的装备。

明确排除经营业绩、合同金额本身、资本市场、股价/公告、党建、人事、招聘、会议会见、品牌宣传以及无工程新事实的企业新闻。详情页的“来源”通常是中交所属单位，因此工程节点只能视为项目第一方记录；“世界最大”“全球首创”、预期社会经济效益、技术/产品效果等仍是企业声明，除非另有独立一手证据，不得升级为独立验证。

### 公网、HTTP、robots、条款和版权

- DNS 观察：`www.ccccltd.cn -> 28.0.0.79`；Python `ipaddress` 点时判定为 global、非 private/loopback/link-local。与 CABR 相同，这可能是研究环境的合成解析，后续 Admission/运行必须逐跳重新解析。
- 浏览器导航证据：集合 URL 的 Navigation Timing 为 `responseStatus=200`、`redirectCount=0`、最终 URL 不变；样本详情 [浙江甬江特大桥合龙](https://www.ccccltd.cn/news/jcxw/jx/202607/t20260717_227766.html)同样为 `200`、零重定向，页面 meta 指定 `text/html; charset=utf-8`，公开显示标题、发布日期、正文和来源“中交路建 振华重工”。无需登录、验证码或付费墙。
- HTTP 根站在浏览器中最终升级到同主机 HTTPS；CDP 未保留该次升级的精确 30x 状态，因此只记录“最终 HTTPS”，不伪造状态码。非浏览器 `curl` 在同一时段对 CCCC 页面返回边缘层 `521`，而浏览器正常 200；这说明后续 Admission 必须用获准客户端重新 Probe，不得把浏览器可达外推为任意连接器可达。
- [`robots.txt`](https://www.ccccltd.cn/robots.txt)在浏览器中显示 `404 Not Found`；404 不表示允许，SourceAdmission 必须重新核验并失败关闭未知状态。
- [版权声明](https://www.ccccltd.cn/dbnr/dbnr_bqsm/)保留网站资料、信息、版式、程序等所有权和著作权，并声明使用网站即同意条款；它没有像 CABR 那样明示禁止个人非商业复制/传递，但也没有授予自动保存或公开再分发许可。因此 `ADMISSION_READY` 仅表示可以进入下一步合规 Probe，不能视为版权许可。后续策略必须只公开题录、accepted claims、必要短摘和原链，原始响应保持私有，且 `public_redistribution=false`。

## 原始哈希与证据限制

本研究 Markdown **没有保存可声明为官方 raw response 的 SHA-256**，字段应明确为 `unavailable`，不能用页面文本、截图或浏览器 DOM 的哈希冒充原始响应哈希。原因如下：

- CABR 的状态、MIME 和重定向可由直接响应可靠观察，但本研究会话未在取证时同步固化原始字节；事后重取可能遇到页面更新，不能倒填成先前观察的 hash。
- CCCC 的浏览器导航返回 200，而无凭据 `fetch`/`curl` 返回边缘层 521；对 521 错误体计算的 hash 不是集合原文 hash，故不保存。

若后续机器 manifest 的 Schema 强制 `response_sha256`，必须在新的、受控且可复核的 Probe 中把实际 200 响应原始字节与响应元数据同时固化后再写入；不得填占位值或错误页 hash。本票研究结论不因此变成准入或运行证据。

## 关闭与后续门禁

中国交建已满足研究态 `BOUNDED + ADMISSION_READY`，但中国建研院同时存在 `NO_CONTINUOUS_COLLECTION` 和 `TERMS_PROHIBIT_COPYING`。依 Issue #30 的“两个精确 SourceStream 都达到 `BOUNDED + ADMISSION_READY` 才能关闭”条件，本票必须保持打开，且不能解除 Issue #31 对中国建研院席位的准入波次阻断。

可解除 CABR 阻断的外部事实至少包括：同一官方机构提供公开、持续更新且有可重复条目边界的科研成果集合，以及对单一 Owner 非商业研究平台自动访问、raw-first 私有保存和必要原链使用的明确书面许可。即使未来满足，也仍须独立通过公网安全、逐跳重定向、robots、版权、限速、预算、熔断和 SourceAdmission 门禁。
