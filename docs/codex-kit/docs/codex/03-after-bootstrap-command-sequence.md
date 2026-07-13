# 已执行第 00 轮后的 Codex 指令顺序

你已经执行 `01-bootstrap-prompt.md`，下一条不要直接发第 01 轮，先执行新增的第 00A 轮，将方案 1 视觉基线落到现有工程。

## 1. 下一条立即发送

把 `docs/codex-kit/docs/codex/round-00a-ui-foundation.md` 中代码块完整复制给 Codex。

如果开发包在仓库中的路径不是 `docs/codex-kit/`，只替换路径前缀，不改任务内容。

## 2. 之后严格按顺序发送

| 顺序 | 指令文件 | 通过后得到 |
|---:|---|---|
| 00A | `round-00a-ui-foundation.md` | 牛油果设计系统、壳层、响应式和无障碍基线 |
| 01 | `round-01-source-vault.md` | 来源注册、上传、预览 |
| 02 | `round-02-safety-regulation-html.md` | 首条安全规定进入同一时间线与证据闭环 |
| 03 | `round-03-pdf-ocr-versioning.md` | PDF证据、版本差异与撤回 |
| 04 | `round-04-safety-case-lifecycle.md` | 安全案例事件时间线 |
| 05 | `round-05-digital-cases.md` | 数字化案例卡片与详情 |
| 06 | `round-06-papers.md` | 论文题录与证据边界 |
| 07 | `round-07-products-equipment.md` | 软件、物联网、低空、AI设备 |
| 08 | `round-08-dedup-events-scoring.md` | 聚类、热点和真实可解释分项 |
| 09 | `round-09-ai-editorial.md` | AI摘要、审核、修订和撤回 |
| 10 | `round-10-feed-search-daily.md` | 组合完善搜索、日报、收藏与全部状态 |
| 11 | `round-11-production-gates.md` | 质量、运维、安全和独立验收证据包 |

## 3. 每一轮发送前的固定前言

```text
你正在四川路桥行业数智与安全情报平台仓库中工作。

开始前必须：
1. 完整阅读根目录 AGENTS.md；
2. 阅读 docs/codex-kit/README.md、docs/codex-kit/docs/codex/00-usage.md；
3. 阅读 docs/codex-kit/docs/06-ui-ux-spec.md 与 docs/codex-kit/docs/ui/全部文件；
4. 阅读当前轮次引用的规范和素材；
5. 检查 git status、现有实现、测试和上一轮验收记录；
6. 先实际重跑上一轮关键门禁；失败则只修复上一轮，不开始本轮；
7. 先复述本轮用户场景、范围、不做项、必须复用的组件/契约、实现步骤和验收命令；
8. 发现文件缺失、已有修改冲突或需求矛盾时停止并报告，不得猜测。

必须测试驱动并交付可演示纵向切片。必须复用 AppShell、IntelligenceFeedPage、IntelligenceCard、FeedPage/ItemSummary 和唯一 PublicationService；不得创建平行实现。
```

将固定前言与当轮文件代码块放在同一个 Codex 任务中。每轮单独开任务，不要一次粘贴多轮。

## 4. 进入下一轮的硬门禁

只有当 Codex 返回以下内容且可复核时，才进入下一轮：

- 实际完成的用户价值；
- 变更文件；
- 迁移与回滚；
- API样例或页面截图；
- 验收命令和真实输出；
- 已知限制；
- Git提交哈希；
- 明确写出“满足进入下一轮门禁”。

任何测试失败、视觉/无障碍阻断、未提交改动或门禁未过，都先让 Codex修复当前轮，不要继续。

