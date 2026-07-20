# Issue #21 替代机构有界流研究

- 父 Spec：GitHub Spec #1
- 原 Issue：#21
- 核验时间：2026-07-20（Asia/Shanghai）
- 研究目标：不再以中国中铁与三一集团作为本票的两个目标机构，重新找到一个持续的工程项目第一方官方集合，以及一个持续的施工机械工程应用官方集合。
- 本文只是 `SourceResearchDisposition` 研究输入；不是 `SourceAdmission`、Owner GO、启用、实际运行或覆盖证据。

## 注册表去重

已核对 `docs/codex-kit/assets/source_registry.csv` 和 `docs/audit/phase-2/source-and-connector-inventory.csv`：

- 中国建筑已有唯一机构记录 `ENT-002`，本研究复用该记录，不另建同机构 Source。
- 徐工集团工程机械股份有限公司原不在注册表；替代票 #37 已为其分配新的规范候选代码 `ENT-010`，没有复用 `ENT-009` 三一集团。
- 中国铁建与大疆行业应用分别已是 `ENT-004` 和 `ENT-008`，下文明确记录它们为何不能作为这次的诚实替代。

## 结论

| 覆盖目标 | 机构与精确集合 | StreamReadiness | SourceResearchDisposition |
| --- | --- | --- | --- |
| 持续、直接的工程项目第一方官方集合 | `ENT-002` 中国建筑「企业动态」 `https://www.cscec.com/xwzx_new/zqydt_new/` | `BOUNDED` | `ADMISSION_READY` |
| 持续、直接的施工机械工程应用官方集合 | 徐工官网「施工案例」 `https://www.xcmg.com/case/case.htm` | `BOUNDED` | `ADMISSION_READY` |

两个 `ADMISSION_READY` 只表示可以交给后续服务端 SourceAdmission Probe。当前必须保持 `desired_enabled=false`、`source_admission=null`、`actual_running=false`，且不追加 `PAUSE` 或任何覆盖信用。

## 1. `ENT-002` 中国建筑企业动态

### 有界集合

- 官方主机：`www.cscec.com`
- 集合 GET：`https://www.cscec.com/xwzx_new/zqydt_new/`
- 分页模式：`/xwzx_new/zqydt_new/index_{positive_integer}.html`
- 详情模式：`/xwzx_new/zqydt_new/YYYYMM/{numeric_id}.html`
- 官方样例：`https://www.cscec.com/xwzx_new/zqydt_new/202607/3950899.html`
- 连接器：`HTML_LIST_DETAIL`
- MIME：仅 `text/html`
- 建议频率：1440 分钟；1 request/minute；10 秒超时；最多 5 次重定向；禁止跟随离开 `www.cscec.com` 的重定向。

该栏目持续发布中建所属单位的中标、开工、封顶、贯通、竣工、交工、交付与投运信息，当日列表包含房屋建筑、机场、铁路、高速公路、市政、水务和能源工程项目。它是明确栏目和可枚举分页，不是根站、通用搜索、单篇文章或媒体转载集合。

### 内容和 claim 边界

栏目中仍有奖项、安全宣传、品牌、养老商业、制造基地等噪声。候选必须同时命中产品边界内工程对象与规划、设计、中标、施工、竣工、运营、养护、安全或监测生命周期词，并排除党建、人事、资本市场、奖项、纯品牌和纯商业运营内容。

该来源中的项目节点只能标注 `PROJECT_FIRST_PARTY_RECORD`。中建对进度、质量、创新或效果的表述不是独立验证。

### 公网、robots、条款和版权核验

- 集合、样例详情和法律声明均实测 HTTPS 200、`text/html`、0 次重定向，无登录、验证码或付费墙。
- DNS-over-HTTPS 结果是 `www.cscec.com.cdn30.com`，A 记录 `138.113.89.175` 和 `115.127.225.136`，均为公网地址。
- `https://www.cscec.com/robots.txt` 返回 404。这表示点时核验中站点未提供 robots 规则，而不是服务端已获得永久许可；SourceAdmission 必须再次取得并按当时状态解释。
- 官方《法律声明》：`https://www.cscec.com/fzlm_new/flsm_new/`。声明明确网站信息“仅供参考之用、不用作任何商业用途”，并以访问、阅读、下载或使用作为接受条款的情形；同时保留文字、图形、图片等权利。

因此研究边界固定为 Owner 私有、非商业研究：仅为证据可追溯性保留必要 HTML，对外只投影题录、证据化必要短摘要和原文链接，不采集或再分发图片、视频、附件或全文，`public_redistribution=false`。

### 点时哈希

- collection SHA-256：`ce64bd1867ada0815f69f9de69adbee17b901e1f5791a57b70fd1044880d33aa`
- detail SHA-256：`5d85350287177c5aa6b73ab8365c0d2e1047f4f1697bbdddec218b9f03f62482`
- robots 404 response SHA-256：`304f5b8a577543a9cca38c8f59851b8768f4c5adf79074e07c20c89dd22873b3`
- legal statement SHA-256：`328c3a9dcd83420ca9f7a0bf4bf1988846a0bdd5df398c6a55c00086465b404c`

## 2. 徐工官网施工案例

### 有界集合

- 官方主机：`www.xcmg.com`
- 入口 shell GET：`https://www.xcmg.com/case/case.htm`
- 列表 POST：`https://www.xcmg.com/ext/ajax_case.jsp`
- 表单：`flag=case`、`ids=1,1,`、`channelId=22571`
- 详情模式：`/case/case-detail-{numeric_id}.htm`
- 官方样例：`https://www.xcmg.com/case/case-detail-11243013.htm`
- 连接器：公开 HTML shell + same-host form POST list + HTML detail；不得误写为纯 GET 列表。
- MIME：仅 `text/html`
- 建议频率：1440 分钟；1 request/minute；10 秒超时；最多 5 次重定向；禁止跟随离开 `www.xcmg.com` 的重定向。

实测 POST 列表返回 200 `text/html`、0 次重定向，并包含 300 个 `/case/case-detail-{digits}.htm` 详情链接。官方入口按设备类型和地区组织施工案例，直接覆盖公路市政、桥梁、隧道、机场、矿山、港口、房建和能源工程；不是根站、搜索或单篇。

### 内容和 claim 边界

只接受同时命中产品边界内工程对象与施工、运营、养护、安全或监测生命周期的案例。排除纯交付、发运、销售、品牌奖项，以及制造工厂、生产线、ERP 和泛制造数字化。

徐工对效率、油耗、稳定性、节省金额和客户评价的所有表述固定为 `MANUFACTURER_CLAIM`，不得投影为 `INDEPENDENT_VERIFICATION`。

### 公网、robots、条款和版权核验

- shell、POST 列表、样例详情、robots 与法律声明均实测 HTTPS 200、0 次重定向，无登录、验证码或付费墙。
- DNS-over-HTTPS A 记录为 `115.120.56.205`，是公网地址。
- `https://www.xcmg.com/robots.txt` 内容为 `User-agent: *` 与空 `Disallow:`，未禁止 `/case/` 或 `/ext/ajax_case.jsp`。
- 官方《法律声明》：`https://www.xcmg.com/site/legal-notices.htm`。第 1 条允许“以电子方式复制在此发布的文档，并只能用于传达或查看信息的目的”；同时禁止未经书面许可制作镜像、更改后再发布或将材料作商业利用。

因此研究边界固定为 Owner 私有、非商业研究和原始 HTML 留证，不获取或再分发图片、视频、手册、附件或全文；对外只允许题录、必要短摘要、claim basis 和原文链接，`public_redistribution=false`。

### 点时哈希

- shell SHA-256：`24f7a4f35befdca484e3a15f01aef922f5e608669166475925f30f1760d07cf8`
- POST list SHA-256：`584e9928ec1a27b4daa14c6a19e4704e058c7dd294838b9d5b7f271bded22b90`
- detail SHA-256：`5a55be80c588f98a7ef6f0adac6f70d44c633a13e0aca8415a20412343d217ab`
- robots SHA-256：`2e156fdd375cdc352ca208875f918b366b2a952c0793e92b9f558badaeecca87`
- legal statement SHA-256：`fe5b72ede5f729459ae81b2ce8febf55d69ebaa795528c7643a1e02d0feb3178`

## 明确不作替代的现有来源

### `ENT-004` 中国铁建

- 「生产经营」候选栏目 `https://www.crcc.cn/col/col1592/index.html` 在公开索引中可见，但本次真实浏览器访问显示「WEB 应用防火墙」与滑块人机识别；返回 200 的非浏览器请求也可能是 JS challenge body，不是集合内容。
- `https://www.crcc.cn/robots.txt` 实测 403；官网《法律声明》 `https://www.crcc.cn/col/col1649/index.html` 同样被人机识别拦截。
- 不得绕过验证码或 WAF，也不得把 challenge 的 HTTP 200 冒充成集合可达。结论是 `CANDIDATE/MANUAL_ONLY`，不是 `ADMISSION_READY`。

### `ENT-008` 大疆行业应用

- `https://enterprise.dji.com/cn/surveying/aec` 是一个固定建筑、工程与施工解决方案页，不是持续 SourceStream。
- 相对接近的「Building & Infrastructure」分类 `https://enterprise.dji.com/news/urbanplanning` 点时可见条目仍停留在 2018–2019 年，不能作为持续更新证据。
- 大疆官方 Terms of Use `https://www.dji.com/terms` 明确禁止使用 robot、spider、crawler、scraper 或其他自动方式访问站点或提取数据。
- 无人机、负载与软件解决方案也不能在未有产品域决策时自动扩张为首期 `CONSTRUCTION_MACHINERY`。
- 结论是 `NOT_ADMISSION_READY`；既有条款禁止自动访问，又没有符合本票的持续施工机械工程应用集合。

## 后续准入必须重做的检查

1. 由服务端 SourceAdmission 在实际运行前重新检查 DNS 和每次重定向，拒绝内网、回环、云元数据和出站目标。
2. 重新读取 robots、条款和版权声明；任一状态变为禁止、不明或需书面许可即不得启用。
3. 仅取得 HTML，不取图片、视频、PDF、手册或其他附件；不公开再分发受保护全文。
4. 必须通过统一 `SourceAdapter` 先保存许可边界内的原始响应再解析，不得绕过 raw-first、PublicationService、R3/R4 或公网安全门禁。
5. 中国建筑只产生 `PROJECT_FIRST_PARTY_RECORD`；徐工只产生 `MANUFACTURER_CLAIM`；两者均不得冒充独立验证。
