# 中国公路学会与《隧道建设（中英文）》SourceStream 点时研究

## 结论

本研究对应 GitHub Issue #28，只补齐既有来源研究尚未锁定的两个机构级 Source，不执行 SourceAdmission 或采集：

- `RES-001` 中国公路学会：形成一个 `BOUNDED + ADMISSION_READY` 的成果通知集合研究输入；
- `RES-005`《隧道建设（中英文）》：官方站 HTTP 集合保留为已被替代的阻断证据；持续更新流改用万方按 ISSN 2096-4498 组织的精确期刊专页与文章详情，形成 `BOUNDED + ADMISSION_READY`。

两者均保持 `desired_enabled=false`、`source_admission=null`、`actual_running=false`，不追加 `PAUSE`，不授予覆盖信用。`ADMISSION_READY` 只表示可提交后续 SourceAdmission Probe，不表示 robots、条款、版权、预算、质量或运行门禁已通过。

机器可读证据为 `docs/codex-kit/assets/validation/t27_chts_tunnel_construction_source_stream_discovery.json`，由 `t27_source_stream_discovery.schema.json` 和服务端 Pydantic 模型双重校验。

## 核验方法

学会核验点时为 `2026-07-20T03:05:10Z`，替代期刊流复核点时为 `2026-07-20T04:21:11Z`。公开页面访问使用 `SRBG-SourceResearch/1.0 (+personal noncommercial research)`、10 秒连接超时、30 秒总超时、最多 5 次重定向；没有登录、验证码、付费墙、WAF 或访问控制绕过。DNS 证据使用公开 DNS-over-HTTPS；动态页面只通过隔离后台浏览器标签确认公开渲染结果，未直接调用站内未公开 API。所有本轮创建的浏览器标签均在核验后关闭。

测试与门禁不依赖公网，固定消费版本化点时记录。

## `RES-001` 中国公路学会

### 精确集合与连接器

- 集合：`https://www.chts.cn/cgtg/CGTGTZ/index.html`
- 允许主机：`www.chts.cn`
- 列表：`/cgtg/CGTGTZ/index(?:_[1-9][0-9]*)?.html`
- 详情：`/cgtg/CGTGTZ/art/{year}/art_{32位十六进制}.html`
- 连接器：`DYNAMIC_HTML_LIST_DETAIL`
- MIME：`text/html`
- 候选频率：每日一次、每分钟最多一次

集合原始 HTML 通过同主机脚本加载公开列表；隔离浏览器观察到 26 条混合通知。它不是无需过滤的直接流：会议、论坛、培训、观摩、征集、会员、理事会、党建和综合新闻均排除；只有同时具有公路工程对象、工程生命周期和公布／公示／入库等结果语义的材料才进入逐文档 DirectRelevance。

学会名单只表达学会流程记录，流级 ClaimBasis 固定为 `PROJECT_FIRST_PARTY_RECORD`，不能提升为 `INDEPENDENT_VERIFICATION` 或 `AUTHORITY_FINDING`。

### 公网、robots、条款与版权

- DNS-over-HTTPS 返回公网地址 `115.127.225.16` 与 `115.127.228.36`；SourceAdmission 仍须逐跳重验。
- 集合和结果样本 HTTPS GET 均为 200、零重定向，SHA-256 分别为 `06d217c047556f60e9e005e449803b13ef70bacaa8f83ad0f8b751eed3d155ec` 与 `29061de08ca4fb88facd8965c7c033dbe1e78dd6b0a4aaf461a0d0a048773dbd`。
- `https://www.chts.cn/robots.txt` 返回 404，响应 SHA-256 为 `55f7d9e99b8e2d4e0e193b2f0275501e6d9c1ebd29cadbea6a0da48a8587e3e0`。这只表示已核验未发布，绝不推定允许采集。
- 公开成果导航与渲染页脚没有链接独立自动化使用条款，也未找到明确再分发许可。研究投影因此只允许题录、必要短摘与原链，排除全文和图片；后续事实不足必须失败关闭。
- 集合与样本无需登录、验证码、付费墙或访问控制绕过即可读取。

基于“有界集合已找到、未发现必须绕过的访问控制、全部未知项在后续准入继续失败关闭”的仓库既有语义，该流记录 `ADMISSION_READY`，但没有 SourceAdmission 或运行授权。

## `RES-005`《隧道建设（中英文）》

### 被替代的官方站入口

原集合 `http://www.suidaojs.com/CN/2096-4498/current.shtml` 的内容事实继续保留：HTTPS 证书过期，忽略证书的诊断请求会越界到作者登录主机，robots 端点也只返回自定义 HTTP404 页面。该入口没有被重新解释成安全入口，也不会进入后续准入。

### 替代集合与内容边界

- 集合：`https://c.wanfangdata.com.cn/magazine/sdjs`
- 允许主机：`c.wanfangdata.com.cn`、`d.wanfangdata.com.cn`
- 集合路径：精确 `/magazine/sdjs`
- 详情路径：`/periodical/sdjs{YYYY}{issue}{sequence}`，固定九位数字后缀
- 连接器：`DYNAMIC_HTML_LIST_DETAIL`
- MIME：`text/html`
- 候选频率：每周一次、每分钟最多一次

万方专页以 ISSN `2096-4498`、主管/主办单位和月刊周期识别同一《隧道建设（中英文）》Source，默认展示正式出版期次，而不是搜索结果或单篇材料。核验时公开呈现 2026 年 1—5 期；样本 `/periodical/sdjs202605001` 明确给出 DOI `10.3973/j.issn.2096-4498.2026.05.001`、卷期、题名、作者、日期、页码和中英文摘要。

集合与样本详情 HTTPS GET 均为 200、零重定向，原始应用壳 SHA-256 分别为 `9b2f41612e201adcb610280f200da12b9367c0b1921af951d9caceb791e5074f` 与 `70fde50d8a023051c4e40bf8ab70727b67e69232009b0be706d7ffc0e975b5cc`。动态渲染事实只作为研究证据；后续适配器若不能 raw-first 保存真实响应及定位，不得启用。

期刊文章只允许 `RESEARCH_CONCLUSION`。Reader 仍主动收窄为题录、公开摘要与万方原始详情链接；“在线阅读”、下载、PDF、图片和全文均排除，不登录、不使用机构权限、不绕过付费墙，也不直接调用页面内部 API。

### 公网、robots、条款与版权

- DNS-over-HTTPS 将两个允许主机解析到公网地址 `122.115.55.103`；HTTPS 证书有效，集合和详情均零重定向。
- 集合主机的 `/robots.txt` 返回与应用壳完全相同的 200 响应，而详情主机返回 404（SHA-256 `4ff444d1abe117bbe3055e97182351923ce4db715959b733900bb28f72fa0e29`）。这只记录“未发布有效 directives”，绝不解释为采集许可，SourceAdmission 必须重验。
- 期刊专页链接帮助、客户服务及平台权属信息，但未链接独立自动化使用条款。该已核验缺失不授予运行权，且禁止把内部接口当公开 API。
- 页面明确标注万方平台版权，并把公开题录/摘要与在线阅读、下载能力分开；研究边界因此只允许私有 raw 证据、题录、公开摘要和原链，不公开再分发全文或附件。
- 集合和样本题录/摘要无需登录、验证码或付费墙即可读取；受限阅读与下载按钮不属于本流。

在上述精确边界内，该替代流达到研究态 `BOUNDED + ADMISSION_READY`。这只允许进入后续 SourceAdmission Probe，不代表万方已授权真实采集或已经运行。

## 隧道瓦斯与关闭判断

期刊出现“隧道”“瓦斯”或“气体”关键词本身不授予专项 facet。只有逐文档分类同时具有 `TUNNEL` 与 `HIGHWAY` 或 `RAILWAY`，才可取得 `TUNNEL_GAS_MONITORING`；`MINING` 或单独 `TUNNEL` 均不满足。

Issue #28 要求两个流都达到 `BOUNDED + ADMISSION_READY` 才能关闭。中国公路学会流与万方替代期刊流现均满足研究态条件，因此 `closure_eligible=true`，可以关闭研究票并解除对应准入波次。关闭不改变 Owner 意图、SourceAdmission、实际运行、PAUSE 或覆盖信用；原官方站的 HTTPS 阻断事实继续保留，不能被运行适配器重新采用。
