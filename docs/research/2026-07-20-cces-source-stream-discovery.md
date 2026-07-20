# 中国土木工程学会有界 SourceStream 发现

- GitHub Issue：#26（v2 T25）
- 父 Spec：#1
- 最终核验时间：2026-07-20T03:40:10.5816790Z
- 规则版本：`t25-cces-source-stream-discovery-v2`
- 机器记录：`docs/codex-kit/assets/validation/t25_cces_source_stream_discovery.json`

## 结论

中国土木工程学会继续只计一个机构 Source（`RES-011`）。学会旧站的标准与詹天佑奖集合均有稳定边界，但只可通过明文 HTTP 读取，不能进入准入准备态。本轮没有降低 TLS 门槛，而是将标准流替换为全国团体标准信息平台中的 CCES 固定机构集合。

全国团体标准信息平台由国家标准化管理委员会组织、中国标准化研究院建设。公开集合通过唯一 `organUniqueId=lqql38h6za4w73tg0faju6skjiub8cb` 固定为中国土木工程学会，点时返回 73 条记录；样本详情明确记录“由中国土木工程学会在团体标准信息平台公布”，同时将标准正文标为“不公开”。因此该替代流达到研究态 `BOUNDED + ADMISSION_READY`，Issue #26 的关闭条件满足。`ADMISSION_READY` 不是 SourceAdmission，也不构成运行授权。

| SourceStream | 精确边界 | 研究结论 |
| --- | --- | --- |
| `RES-011-STANDARD-RELEASES` | `https://www.ttbz.org.cn/standard.html#org_bHFxbDM4aDZ6YTR3NzN0ZzBmYWp1NnNraml1YjhjYg==`；页面调用固定 POST `/cms-proxy/ms/portal/standardInfo/getPortalStandardList`；详情 `/standardDetail/{31位id}.html` | `BOUNDED + ADMISSION_READY`，只读公开 JSON/HTML 元数据 |
| `RES-011-ZHANTIANYOU-AWARDS` | `http://cces.net.cn/html/tm/29/38/38.html` 及已记录详情边界 | `BOUNDED + BOUNDARY_DISCOVERY`，继续因 `HTTPS_UNAVAILABLE` 停用 |

标准流连接器固定为 `JSON_POST_FILTER_HTML_DETAIL`，请求体固定为 `pageNo=1`、`pageSize=20`、CCES 唯一机构 ID 和 `standardStatus=1`；允许主机只有 `www.ttbz.org.cn`，预期 MIME 只有 `application/json` 与 `text/html`。候选频率为每日一次、最小请求间隔 15 秒、每次最多 3 个列表页、10 秒超时和最多 5 次同边界重定向；`frequency_authorized=false`。

## 公网、安全与合规证据

- `www.ttbz.org.cn` 点时解析为公网地址 `28.0.0.98`；平台页、固定过滤 API 和样本详情均通过有效 HTTPS 直接返回 200、零重定向。原始响应 SHA-256 保存在机器记录中。
- `robots.txt` 返回 200，包含 `Allow: /`，并显式禁止 `/ms/`、`/cms/`、登录、注册、账户、静态资源和 PDF 预览等路径。选定的 `/standard.html`、`/standardDetail/` 与 `/cms-proxy/ms/` 不匹配这些禁止前缀；所有登录、账户、PDF、`/ms/` 和 `/cms/` 路径仍排除。
- 平台介绍说明其用于发布团体标准信息，并向公众提供标准获取、评价与监督渠道。用户管理规定约束注册用户；本流不注册、不登录，也不访问账户能力。该事实仍不是无限制采集许可，后续 SourceAdmission 必须复核。
- 页脚版权归中国标准化研究院；样本明确把标准正文标为“不公开”。流只读取并保存公开元数据 raw response，Reader 只允许 AcceptedClaims、必要短摘和原文链接；不得请求、保存或再分发标准正文、PDF、图片、附件或账户内容。
- 列表 API 返回的 `organName=中国土木工程学会`、`organCode=CCES` 和机构唯一 ID 必须同时匹配；任何不匹配记录失败关闭，不得借平台综合列表扩大边界。

## 内容与 ClaimBasis

替代平台承载的是 CCES 自行公布的标准记录，因此标准编号、标题、公布日期、发布日期、实施日期、状态及“由中国土木工程学会公布”只能使用 `PROJECT_FIRST_PARTY_RECORD`。平台或学会身份不能把团体标准提升为法规效力认定、独立验证或技术效果证明。

文档级 DirectRelevance 仍须同时满足既定十一类 `EngineeringObject` 或工程生命周期直接相关装备范围；公交经营、泛组织动态、会议宣传、会员活动和无工程对象的新事实继续排除。标准正文不可公开时不得通过附件或预览端点补取。

詹天佑奖仍使用旧 HTTP 边界，仅保留为 `BOUNDARY_DISCOVERY`。奖项事实也只允许 `PROJECT_FIRST_PARTY_RECORD`；获奖不能自动证明工程效果或独立验证。

## 第二批 W2 与控制面

第二批 W2 仍由本票 `RES-011-STANDARD-RELEASES` 与既有 `GOV-008-STANDARD-METADATA-CANDIDATE` 组成。后者沿用[全国标准信息公共服务平台既有研究](2026-07-19-civil-engineering-authoritative-source-expansion.md#s05-全国标准信息公共服务平台)中的 `https://std.samr.gov.cn/search/std` 国家/行业/地方标准元数据候选，本票不重复其研究或授予 SourceAdmission。

控制状态保持不变：`desired_enabled=false`、`source_admission=null`、`actual_running=false`，不追加 `PAUSE`，不授予覆盖信用，不执行真实采集或 W2 准入。研究票关闭只表示已经形成至少一个 `BOUNDED + ADMISSION_READY` 精确 SourceStream。
