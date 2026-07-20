# 中国民用航空局与《中国公路学报》有界流发现

- GitHub Issue：#19（v2 T18）
- 父 Spec：#1
- 核验时间：2026-07-20T02:25:51Z—2026-07-20T02:36:26.634Z
- 策略版本：`t18-stream-discovery-w4-v1`
- 机器可读记录：`docs/codex-kit/assets/validation/t18_source_stream_discovery_w4.json`

## 结论

本票锁定两个不同机构 Source 下的两个精确 SourceStream。两者均为 `StreamReadiness=BOUNDED`、`SourceResearchDisposition=ADMISSION_READY`，只表示已经形成可提交后续 SourceAdmission Probe 的研究输入，不表示准入、启用或实际运行。

| Source | 精确集合 | 连接器 | 频率 | 研究边界 |
| --- | --- | --- | --- | --- |
| `GOV-014` 中国民用航空局 | `https://www.caac.gov.cn/was5/web/search?page=1&channelid=211383&fl=60` | `LIST_DETAIL` | 120 分钟候选值 | `fl=60` 仅表示机场司机构分类，文档仍须通过机场工程生命周期 DirectRelevance；排除航班经营、时刻、旅游消费和一般经营新闻 |
| `RES-004` 《中国公路学报》 | `https://zgglxb.chd.edu.cn/CN/current` | `LIST_DETAIL` | 1440 分钟候选值 | 只接受在域公路、桥梁、隧道、道路工程和直接施工机械研究；研究结论固定为 `RESEARCH_CONCLUSION` |

民航局结果页虽然由站内检索服务提供，但它带有官网固定的 `channelid=211383&fl=60` 机构分类约束，并由机场司页面的“更多”入口自然到达；它不是通用搜索结果。允许的详情边界仅为同主机 `/XXGK/XXGK/.../tYYYYMMDD_ID.html`，结果中出现的 HTTP 链接必须升级为同主机 HTTPS 后重新验证，不能授权降级或跨主机跳转。

《中国公路学报》官网 RSS 服务页公开了当期目录和最新录用 RSS，但点时核验发现“当期目录” RSS 仍返回 2023 条目，“最新录用”为空；官网 `/CN/current` 同时明确显示 2026 年第 39 卷第 6 期。因此本票选择正式当期目录 HTML 集合，不把失真的 RSS 冒充当前更新流。详情仅允许同主机 `/CN/10.19721/j.cnki.1001-7372.YYYY.II.NNN` 元数据/摘要页面，PDF 与下载端点不在该流边界内。

## 公网、robots、条款与版权证据

### 中国民用航空局

- [机场司入口](https://www.caac.gov.cn/dev/jcs/)和[机场司机构分类集合](https://www.caac.gov.cn/was5/web/search?page=1&channelid=211383&fl=60)在核验时公开返回 200，未发生跨主机重定向；[跑道建设项目样本](https://www.caac.gov.cn/XXGK/XXGK/TZTG/202606/t20260608_230989.html)可公开读取，无登录、验证码或付费墙。
- [`robots.txt`](https://www.caac.gov.cn/robots.txt) 的 wildcard 组为空 Disallow，并单独禁止 `/CAAC/local/` 与 `/image/`；所选列表与详情边界不在禁止路径内。
- 官网页脚声明网站版权归中国民用航空局。核验入口和[网站地图](https://www.caac.gov.cn/WZDT/)未链接独立自动访问条款；这项点时事实不被解释为转载许可，后续 SourceAdmission 必须重新核验。研究边界只允许题录、必要短摘录和原文链接，不公开再分发全文或附件。

### 《中国公路学报》

- [正式当期目录](https://zgglxb.chd.edu.cn/CN/current)在核验时公开返回 200，并显示 2026 年第 39 卷第 6 期；[RSS 服务页](https://zgglxb.chd.edu.cn/CN/rss/showRssInfo.do)仅作为“RSS 当前性不可靠”的复核证据。
- [`robots.txt`](https://zgglxb.chd.edu.cn/robots.txt) 对 wildcard 明确 `Allow: /`；robots 许可不被解释为版权或条款许可。
- [投稿指南](https://zgglxb.chd.edu.cn/CN/column/column3.shtml)和[出版伦理](https://zgglxb.chd.edu.cn/CN/column/column4.shtml)说明录用稿版权转让和版权使用范围，官网页脚声明编辑部版权所有。没有发现独立自动访问条款，因此后续准入必须重新核验；本票固定为题录、官网公开摘要边界和原文链接，禁止受保护全文再分发。

## 控制面与后续工作

- 两个 Source 仍分别只计一个机构；SourceStream 不增加机构数。
- `desired_enabled=false`，`source_admission=null`，`actual_running=false`，不追加 `PAUSE`，不授予运行或覆盖信用。
- 本票不执行真实采集、样本评估或 72 小时波次。Issue #20 必须重新核验公网目的地址、逐跳重定向、robots、条款、版权、限速、预算和运行事实，且只有服务端 SourceAdmission 可以改变后续授权。
- 期刊论文的主张只使用 `RESEARCH_CONCLUSION`；不得投影为权威机关认定、独立工程验证或已落地成效。
