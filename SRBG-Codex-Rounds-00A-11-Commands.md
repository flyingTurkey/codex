# 四川路桥行业数智与安全情报平台：Codex 第00A—11轮执行顺序

版本：`v1.1.0-avocado-ui`

## 现在应该发送什么

你已经执行第 00 轮 bootstrap，下一条应把以下文件中的代码块完整发给 Codex：

```text
docs/codex-kit/docs/codex/round-00a-ui-foundation.md
```

第 00A 轮只在现有工程中落地方案 1 的牛油果设计系统、应用壳层、响应式和无障碍基线，不重新脚手架，也不开发虚假业务页。

## 之后依次发送

| 顺序 | 指令文件 | 用户可见结果 |
|---:|---|---|
| 00A | `round-00a-ui-foundation.md` | 牛油果主题、壳层和基础组件 |
| 01 | `round-01-source-vault.md` | 来源登记、上传和预览 |
| 02 | `round-02-safety-regulation-html.md` | 第一条安全规定进入同一时间线 |
| 03 | `round-03-pdf-ocr-versioning.md` | PDF证据、版本与撤回 |
| 04 | `round-04-safety-case-lifecycle.md` | 安全案例生命周期 |
| 05 | `round-05-digital-cases.md` | 数字化案例 |
| 06 | `round-06-papers.md` | 期刊论文 |
| 07 | `round-07-products-equipment.md` | 软件、物联网、低空和AI设备 |
| 08 | `round-08-dedup-events-scoring.md` | 聚类、热点和可解释评分 |
| 09 | `round-09-ai-editorial.md` | AI摘要、审核、修订和撤回 |
| 10 | `round-10-feed-search-daily.md` | 搜索、日报、收藏和状态收口 |
| 11 | `round-11-production-gates.md` | 质量、运维、安全和独立验收 |

完整说明位于：

```text
docs/codex-kit/docs/codex/03-after-bootstrap-command-sequence.md
```

## 每轮固定前言

把下面前言和当轮指令文件中的代码块放到同一个 Codex 任务中：

```text
你正在四川路桥行业数智与安全情报平台仓库中工作。

开始前必须：
1. 完整阅读根目录 AGENTS.md；
2. 阅读 docs/codex-kit/README.md 和 docs/codex-kit/docs/codex/00-usage.md；
3. 阅读 docs/codex-kit/docs/06-ui-ux-spec.md 与 docs/codex-kit/docs/ui/全部文件；
4. 阅读当前轮次引用的规范、Schema和素材；
5. 检查 git status、现有实现、测试和上一轮验收记录；
6. 实际重跑上一轮关键门禁；失败则只修复上一轮，不开始本轮；
7. 先复述本轮用户场景、范围、不做项、必须复用的组件/契约、实施步骤和验收命令；
8. 发现文件缺失、已有修改冲突或需求矛盾时停止并报告，不得猜测。

必须测试驱动并交付可演示纵向切片。必须复用AppShell、IntelligenceFeedPage、IntelligenceCard、FeedPage/ItemSummary和唯一PublicationService；不得创建平行实现。
```

## 每轮完成后发送

```text
现在不要开始下一轮。请对刚完成的当前轮执行独立验收，并持续修复，直至通过或确认存在需要用户决策的真实阻断项。

重新阅读根目录AGENTS.md、当前轮指令文件、docs/codex-kit/docs/06-ui-ux-spec.md及验收标准；检查git diff、git status、迁移、权限、前后端实现、测试、观测、CHANGELOG和验收记录。

重新运行当前轮全部专项测试和全局门禁。不得只复述旧结果，不得使用缓存日志冒充本次执行，不得跳过失败测试、降低阈值、删除断言或伪造页面截图/连续运行数据。

重点检查：
1. 每项必须交付和硬性测试是否有代码与测试；
2. 前端、API、Worker、数据库与权限是否形成真实纵向闭环；
3. 是否复用既有AppShell、Feed、Card、详情和PublicationService，而非创建平行实现；
4. 是否存在占位按钮、Mock冒充生产、TODO、静默吞错或发布旁路；
5. 是否破坏上一轮功能、安全门禁、响应式或无障碍；
6. 迁移可正向执行且回滚策略明确；
7. 工作区只保留当前轮相关且已提交的改动。

发现一般问题时直接修复并重跑；只有需要扩大范围、外部授权、真实生产凭据或用户业务决策时才停止。

最终提供验收矩阵、实际命令与真实结果、修复内容、页面/API证据、剩余风险和提交哈希。全部通过才明确写“当前轮验收通过，可以进入下一轮”；否则写“当前轮未完成”。
```

## 硬规则

- 每轮单独开任务，不能一次发送多轮；
- 上一轮未通过，不进入下一轮；
- 第02—07轮持续扩展同一信息流和情报卡；
- 第08轮前正式页面不显示演示评分；
- 第10轮只组合完善，不重写平行Feed/Card；
- 开发预览可跳过人工预计算证据摘要哈希；生产由服务端自动计算并校验SHA-256。
# 历史命令（PERS-10 后失效）

本文件中的企业角色、审批和 Operations 命令只作历史记录，不得用于当前个人平台。现行迁移与验收见 PERS-10 文档。

