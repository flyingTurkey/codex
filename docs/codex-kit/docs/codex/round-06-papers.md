# 第 06 轮：期刊论文

```text
执行第06轮：接入开放学术元数据并完成论文题录、研究解读和版权边界。

读取：docs/codex-kit/docs/04-data-source-compliance.md、docs/codex-kit/assets/source_registry.csv、docs/codex-kit/assets/content.schema.json、docs/codex-kit/assets/sample_items.json、docs/codex-kit/docs/06-ui-ux-spec.md、docs/codex-kit/docs/ui/02-component-contracts.md。

来源：OpenAlex API作为自动化主切片；Crossref用于DOI和更新关系补充；中国公路学报使用经过批准的RSS或目录固定样本。知网和万方不得绕过登录或付费机制。

必须交付：
- paper_profile：DOI、期刊、ISSN、作者、机构、卷期、年份、摘要、关键词、开放状态；
- DOI规范化与优先去重；无DOI时使用规范题名+作者+年份候选去重；
- OpenAlex连接器的分页、游标、限速、礼貌标识和契约测试；
- Crossref更新/撤稿关系候选；
- 论文类型、工程专业、技术标签和研究成熟度；
- 论文列表、筛选、详情、相似论文和原文入口；
- access_level控制全文、摘要和仅题录展示；
- 题录导出和引用复制；
- API Mock、固定响应、版权策略和E2E测试。

方案1 UI增量：在既有 /digital 和 IntelligenceCard 上增加论文Tab与 Paper TypeSummary；详情显示DOI、期刊、开放状态、研究成熟度、引用复制和原文入口。元数据、摘要、全文权限用明确文字区分。

硬性规则：
- 未授权全文不进入对象存储和前台；
- 论文研究结论不等于工程生产应用；
- 摘要许可不清时只存元数据和原文链接；
- 撤稿或更正必须显著显示。

验收：同一DOI从两个来源进入时只形成一个论文条目并保留两个来源；无法开放全文时仍可完成题录检索且无越权内容；论文卡加入既有Feed回归E2E和axe。

不做：付费数据库抓取、引文网络可视化、自动学术评价。
```
