# 第四阶段高信号替代 SourceStream 研究

- 核验时间：2026-08-01（Asia/Shanghai）
- 研究范围：第四阶段一次受控真实内容闭环；单一 Owner、隔离环境、单篇低风险 `INDUSTRY_UPDATE`
- 研究动作：仓库既有研究复核，加少量固定官方 URL 的只读 GET
- 明确未做：没有调用模型，没有写数据库，没有启动 SourceStream，没有下载 PDF，没有修改资格、发布或准入门禁

## 结论

唯一推荐是既有研究流 `CJHT_CURRENT_ISSUE`，即《中国公路学报》官方当期目录：

- SourceStream key：`CJHT_CURRENT_ISSUE`
- 列表：<https://zgglxb.chd.edu.cn/CN/current>
- 冻结详情：<https://zgglxb.chd.edu.cn/CN/10.19721/j.cnki.1001-7372.2026.07.016>
- 标题：`静动荷载下公路超大跨径管拱形钢波纹管涵洞的力学特性`
- 出版日期：`2026-07-30`
- 来源边界：仅 `zgglxb.chd.edu.cn` 的 `/CN/current` 与 `/CN/10.19721/j.cnki.1001-7372.YYYY.II.NNN`；PDF、下载、DOI 跳转和其他主机均排除
- ClaimBasis：`RESEARCH_CONCLUSION`；不得提升为主管机关认定、项目业主事实或独立工程验证

这是研究推荐，不是 SourceAdmission 或运行授权。真实运行前仍须在冻结 SHA 上重新解析公网地址、逐跳核验 TLS/重定向、复核 robots/条款/版权、执行 SourceAdmission，并失败关闭；任一事实变化均为 `NO_GO`。

## 为什么该文档是高信号低风险正例

官方详情页在题名、公开摘要和出版元数据的同一页面内同时提供了验收所需信号：

1. 工程对象明确：题名直接包含“公路”和“涵洞”；公开摘要进一步把涵洞界定为公路交通基础设施中的地下构筑物。
2. 工程活动明确：公开摘要说明研究依托某高速公路工程，对回填施工阶段进行测试，并建立和验证车—管—土模型。
3. 已发生的新事实明确：这是一篇已经出版的研究成果，不是计划、倡议或预测；详情元数据同时给出题名、摘要和出版日期。
4. evidence locator 稳定：题名、`citation_abstract`/`dc.description` 与 `citation_publication_date`/`dc.date` 均存在于详情 HTML 元数据；不需要 PDF、登录内容或跨站请求。
5. 主类型边界清楚：中心事实是公路涵洞施工阶段力学研究的发表，不以事故、处罚、法规效力、安全结论或数字化部署为中心，适合作为低风险 `INDUSTRY_UPDATE` 候选。
6. 不含营销中心事实：发布者是期刊编辑部，内容为研究结论；不会把设备厂商宣传、工程效果声明或获奖宣传当作独立验证。

2026-08-01 的有界 GET 对详情返回成功，原始 HTML 为 91,542 bytes，SHA-256 为 `7dd87125666757791e0d1483335705c3d14921ae20aeb734c26e1649022560b3`。元数据记录 `citation_title`、579 字符的公开摘要、`dc.date=2026-07-30` 和 `citation_publication_date=2026/07/30`。本研究只记录这些结构事实和必要短摘边界，不保存或再分发正文。

## 来源、robots、条款与版权

### 官方身份与公开访问

当期目录和详情均在《中国公路学报》官方域名下公开提供：<https://zgglxb.chd.edu.cn/CN/current>、<https://zgglxb.chd.edu.cn/CN/10.19721/j.cnki.1001-7372.2026.07.016>。详情页页脚声明网站版权所有者为《中国公路学报》编辑部。点时访问无需登录、验证码、付费墙或访问控制绕过。

仓库既有一手研究及机器清单已将该流定为 `BOUNDED + ADMISSION_READY`，见：

- `docs/research/2026-07-20-caac-cjht-bounded-stream-discovery.md`
- `docs/codex-kit/assets/validation/t18_source_stream_discovery_w4.json`

这两个记录只提供研究依据，不替代本次运行前的 SourceAdmission。

### robots

官方 <https://zgglxb.chd.edu.cn/robots.txt> 在 2026-08-01 的固定 GET 返回 76 bytes，SHA-256 为 `438e7728708a68cd5f2939f4fc47a1fd8b07ec7017410a9cb27d1300f35d7a68`；通配组明确为 `User-agent: *` 和 `Allow: /`。所选 `/CN/current` 与 `/CN/10.19721/...` 不在禁止路径内。robots 许可不替代条款、版权或 SourceAdmission。

### 条款与版权边界

官方投稿指南 <https://zgglxb.chd.edu.cn/CN/column/column3.shtml> 和出版伦理页 <https://zgglxb.chd.edu.cn/CN/column/column4.shtml> 在点时均公开可达；响应 SHA-256 分别为 `ab1c272bbff0aa56f9de852c9695326adbdfb6001d0cbc753f19e9eb41fef295` 与 `195eb9d2270048e5a24554bd5346efd9f99419ab4b406b90540bf43a30f43a90`。既有研究确认这些页面说明录用稿版权转让和出版使用边界，未发现独立自动化访问条款。

因此本流只能用于单一 Owner 的非商业研究：隔离对象存储可以保存验收所需 raw 证据；对 Reader 的投影仅限题录、accepted claims、必要短摘要和原文链接。PDF、图片、附件和受保护全文不得抓取或再分发。

## 与现有连接器和受控边界的匹配

不需要新增生产连接器、迁移或放宽网络边界。使用现有 `LIST_DETAIL`：

```json
{
  "allowed_hosts": ["zgglxb.chd.edu.cn"],
  "list_url": "https://zgglxb.chd.edu.cn/CN/current",
  "item_selector": "#art5465",
  "link_selector": "a",
  "title_selector": "a"
}
```

点时 DOM 中冻结文章位于 `li#art5465.noselectrow`，其首个 `a` 是同主机详情 URL；因此配置只发现一个冻结文档，不依赖通用搜索、PDF 或动态 API。受控运行的 `expected_host` 固定为 `zgglxb.chd.edu.cn`，`path_prefix` 固定为 `/CN/`，同时覆盖列表与详情而不放宽到站点根路径。

运行配置还应保持既有研究值：日频候选、每分钟最多一次、10 秒请求超时、最多 5 次同边界重定向；第四阶段本次 live 另行固定更严的硬截止、总请求、最大重试与模型费用。列表 DOM ID 若在冻结运行前变化，必须停止并报告 `FIXED_DOCUMENT_NOT_DISCOVERED`，不得改用搜索或直接详情注入。

## 被否决的近邻候选

### 国家能源局煤炭司

`nea-coal-department-updates` 的官方列表 <https://www.nea.gov.cn/sjzz/mts/index.htm> 中存在高信号煤矿项目核准文件，例如 <https://www.nea.gov.cn/2022-07/21/c_1310644445.htm>。该文档本身符合矿山工程和已发生核准事实，但不适合当前低代码 live profile：列表位于 `/sjzz/mts/`，详情位于根部日期路径；当前受控运行只支持单一 `path_prefix`，使用 `/` 会把授权边界扩大到整个主机。不得以扩大边界换取通过，因此否决。

### 中国民用航空局机场司

既有 `CAAC_AIRPORT_DEPARTMENT_DISCLOSURE` 的 robots 状态明确，但列表入口依赖带查询参数的站内检索，当前声明式配置不接受该形态；近期结果还以资质、规范、通报和行政通知为主，不如选定文档稳定地落入低风险 `INDUSTRY_UPDATE`。否决，不增加连接器代码。

### 四川省交通运输厅建设动态

内容信号很强，但既有记录把未发布 robots 与版权限制明确标为不能直接授予运行；没有新的权威证据改变该事实。否决，不把 404 解释为任意采集许可。

### 三一和其他制造商案例

三一同流两篇真实文档均已得到 `AUTO_FILTERED`；制造商案例的中心事实容易成为营销声明。徐工等同类来源即使 robots 明确，也不优于官方期刊的非营销研究正例。否决，不继续用真实模型选文。

## 运行前固定清单

后续 repair/live 只能采用以上唯一推荐，并在真实请求前固定：

- 代码 SHA、`CJHT_CURRENT_ISSUE`、精确列表和详情 URL；
- `zgglxb.chd.edu.cn` + `/CN/` 的受控边界；
- 上述 `LIST_DETAIL` 配置及其配置 SHA-256；
- 当前 robots、条款、版权、公网 DNS、TLS 和重定向证据 SHA；
- `RESEARCH_CONCLUSION` claim basis 与只读题录/摘要/原链投影边界；
- 既有 provider/model/prompt/schema、最大重试、硬截止和不超过阶段人民币 1 元的剩余预算。

如果 DOM ID、出版元数据、公开摘要、robots、条款、版权或公网安全任一项与本记录不一致，必须在调用模型前停止并追加 `NO_GO`，不得降低 SourceAdmission、资格或 PublicationService 门禁。
