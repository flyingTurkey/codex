# 第 10 轮：信息流、搜索、专题与日报

```text
执行第10轮：在第02—09轮已经持续建设的方案1信息流上，完成搜索、日报、收藏与全部状态收口。不得重写既有壳层、Feed、Card、详情和证据组件。

读取：docs/codex-kit/docs/06-ui-ux-spec.md、docs/codex-kit/docs/01-PRD.md、docs/codex-kit/docs/ui/全部文件、docs/codex-kit/assets/ui/design_tokens.json、docs/codex-kit/assets/ui/page_inventory.csv、docs/codex-kit/assets/ui/page_state_matrix.csv、docs/codex-kit/assets/ui/copy_examples.md。

必须交付：
- 完善既有 GET /api/v1/feed?mode=selected|all 与 GET /api/v1/items/{id}、/events/{id}；新增或完善 /hot-topics、/search、/daily、/fingerprint、/version、/saved-items；列表不得另建 /items 或 /events 平行接口；
- Cursor分页、ETag、组合筛选和ACL；
- 编号/文号/标准号/DOI精确搜索，标题实体标签pg_trgm，正文中文索引；
- 可配置语义召回作为增强，不能压过精确编号结果；
- 验收并完善既有首页、精选、全部、数字化、安全、详情、事件；新增或完善搜索、日报、收藏；
- 详情事实与证据联动、来源冲突和版本状态；
- 日报草稿按固定快照生成，经审核后一键发布；
- Markdown导出，防CSV公式注入；
- 收藏和自定义专题；站内关注作为P1可在时间允许时开启；
- 1920×1080、1440×900、1024×768适配，并验证768阅读宽度；
- Loading、空态、来源延迟、原文失效、撤回和无AI降级状态；
- Playwright关键路径和axe无障碍测试。

首页不使用大幅装饰Hero；首先显示今日重点、数据更新时间和异常提示。安全状态必须用文字而不只靠颜色。第10轮不能创建第二套IntelligenceFeedPage、IntelligenceCard或详情页。

验收：用户可从精选/全部进入两大频道，搜索“隧道+监测预警+四川”及精确文号，查看证据、收藏并阅读当天日报；P95达到SLO；未授权用户看不到管理内容。

不做：公网开放、复杂个性化推荐、企业微信推送、开放API密钥体系、Codex Skill。
```
