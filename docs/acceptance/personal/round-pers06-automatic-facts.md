# PERS-06 验收记录：证据事实自动接受

## 范围结论

新 AI 内容流水线从抽取直接进入 `EVIDENCE_GATING`，不再创建 Claim 人工审核任务。通过服务端确定性门禁的 Claim 成为 `EVIDENCE_FACT`；未通过的模型候选保存为独立 `AI_JUDGMENT`，仅在 Event 详情预览。本轮没有让未验证 AI 进入搜索、日报、推荐、通知或时间线卡片，也没有生成 AI 摘要。

## 数据与写边界

- 迁移头为 `0026_automatic_evidence_facts`，前驱为 `0025_personal_source_discovery`。
- 自动接受保存 `AUTOMATED_EVIDENCE_GATE`、规则版本、输入文档版本、Evidence 集合 SHA-256、固定系统主体和追加式生命周期状态。
- `AI_JUDGMENT` 不写 Claim 事实表；模型置信度只作预览信息，不授予事实或发布权限。
- AI Worker 只写事实、判断和 ID-only Outbox；只有 `PublicationService` 的 publisher 仓储可写 `personal_content_projection`。
- 迁移后数据库拒绝新 `CLAIM_REVIEW`；历史任务及决定只读保留。

## 降级与失效

DeepSeek 不可用时先保存题录、原文链接及本地规则可直接定位的题录/显式标量，不生成伪摘要。文档换版、撤回或替代会在同一数据库事务追加自动事实失效状态、失效 AI 判断、排队隐藏旧投影并为新版本创建唯一重处理任务。

## 验收命令

```text
make lint
make typecheck
make test
make contract-test
make security-check
make ai-content-preparation-test
make fixture-replay
make quality-gate
make personal-content-test
make web-e2e
make web-a11y
```

验收结果：全部命令通过。`quality-gate` 完成 1325 项 Python 测试（32 项环境条件跳过）、53 项 UI 单元测试、116 项 Web 单元测试、108 项契约测试及高危/严重级安全扫描；`personal-content-test` 完成 0025→0026→0025→0026 回放、33 项后端测试和 116 项 Web 测试；`fixture-replay` 365 项通过；`web-e2e` 54 项通过；`web-a11y` 17 项通过。`ai-content-preparation-test` 的 32 项后端、116 项 Web 测试及无发布副作用检查通过。
