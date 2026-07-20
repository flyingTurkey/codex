# 广联达与中国煤炭科工集团 SourceStream 发现

> **SUPERSEDED：** 本记录永久保留 Issue #32 两个原始信源的法律阻断证据。替代实现由 Issue #38 / T31R 承载，不得把本记录解释为原两流通过。

- GitHub Issue：#32（v2 T31）
- 父 Spec：#1
- 核验时间：2026-07-20T03:13:23Z
- 规则版本：`t31-stream-discovery-w5-v1`
- 机器记录：`docs/codex-kit/assets/validation/t31_glodon_ccteg_source_stream_discovery.json`

## 第一性原理结论

SourceStream 研究至少要同时回答两个问题：是否存在持续、精确、可重复定位的集合边界；平台能否在不违反 robots、条款、版权和公网安全约束的前提下执行强制 raw-first 保存。公开可达只能回答前一个问题，不能替代后一个问题。

本轮为两个机构各锁定一个稳定集合，因此 `StreamReadiness=BOUNDED`。但两个官网的现行条款都要求自动访问或复制前取得书面授权，而平台没有这项证据。由于 raw-first 是不可降低的架构不变量，两条流只能进入 `MANUAL_SHADOW`，Source 继续为 `CANDIDATE/DISABLED`。此结论不改变 `desired_enabled`、SourceAdmission、实际运行、PAUSE 或覆盖信用。

## 广联达

精确集合为 `https://www.glodon.com/case/index/5.html`，只允许 `www.glodon.com` 的该分类路径与 `/case/{numeric-id}.html` 详情。该页面公开列出数智施工案例，能够提供房建、市政、公路、铁路、桥隧、能源工程或项目管理中的实质数字化材料；全部案例、其他分类、根站、搜索、新闻、投资者内容和 CDN 媒体均不在边界内。

候选必须同时包含工程对象和规划、设计、施工、运营、养护、安全、监测、BIM/GIS/物联网、数字化或项目管理事实。财报、股价、融资、品牌大会、签约仪式、招聘、办公系统、ERP、泛 AI 和企业经营材料明确排除。所有产品能力和成效只能以 `MANUFACTURER_CLAIM` 进入后续候选，不能冒充独立验证。

点时 DNS 解析 `www.glodon.com` 为 `161.117.98.123`，协议主机 `account.glodon.com` 为 `47.74.175.46`，均为公网地址。集合与详情样本 GET 200、零重定向、MIME 为 `text/html`。`robots.txt` GET 404，不能推定自动访问许可。2025-06-30 版广联达用户协议第 2.13 条禁止未经书面授权的爬虫、垂直搜索、镜像、复制或传播；第 9 条保留网页与文本等内容权利。该证据直接阻断自动集合访问和 raw-first 保存，结论为 `BOUNDED + MANUAL_SHADOW`。

## 中国煤炭科工集团

精确集合为 `https://www.ccteg.cn/zh/article/textList/40?idss=183`，即集团新闻下的“煤科硬核”分类；只允许同主机 `/zh/article/infoDetails/{numeric-id}` 详情。集团综合新闻、基层动态、采购平台、外部媒体、搜索和单篇材料不属于该流；集团、所属企业和栏目关系不新增机构 Source。

逐文档只保留煤矿、矿井、矿山、井下、巷道、采煤、掘进或矿用装备，同时具有设计、建设、施工、开采、运营、安全、监测、通风、防灭火、装备、智能化或数字孪生新事实的内容。党建、党委、经营、招聘、品牌、展会、获奖、发运、财务、采购、泛 AI 和无工程事实的工业制造内容排除。集团或所属企业自述只允许 `MANUFACTURER_CLAIM` 或具备项目一方角色时的 `PROJECT_FIRST_PARTY_RECORD`，不能提升为 `INDEPENDENT_VERIFICATION`。

矿井瓦斯始终只归 `MINING`。该流不授予 `TUNNEL_GAS_MONITORING`；只有独立材料同时具备公路或铁路与隧道组合证据时，后续资格服务才可评估该 facet。

点时 DNS 经 `qaxcloudwaf.com` CNAME 解析至公网 `121.32.243.73`。规范集合、详情、robots 和法律声明均公开 GET 200；非 `/zh/` 路径只进行同主机规范化重定向。robots 对 `User-agent: *` 声明 `Allow: /`，但法律声明明确复制、再造、传播、出版、转帖、改编或陈列网站内容前必须取得中国煤科或相关权利人书面许可。robots 不覆盖条款，故结论同样为 `BOUNDED + MANUAL_SHADOW`。

## 关票与解除条件

Issue #32 要求两个流均达到 `BOUNDED + ADMISSION_READY` 才能关闭。本轮两流都因外部书面授权缺失而失败关闭，`closure_eligible=false`，#32 必须保持打开且不能解除 #33。可解除阻断的证据只能是对应权利人明确允许单一 Owner 研究平台自动访问及 raw-first 私有保存的书面许可，或同一机构另有经完整核验且条款允许的官方有界集合。

本研究没有调用真实采集、写 SourceAdmission、改变 Owner 意图或运行状态，也没有生成 Owner Gold、DeepSeek RealSchemaSuccess、观察窗口、覆盖信用或 closeout GO。
