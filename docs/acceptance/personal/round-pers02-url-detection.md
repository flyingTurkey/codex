# PERS-02 任意公开 URL 自动识别与多采集入口验收记录

- 日期：2026-07-17
- 迁移：`0022_personal_source_streams`
- 前置提交：`654e01d feat(personal): establish single-owner source control`

## 交付边界

- Owner 只填写公开 HTTPS URL，不填写连接器、策略、选择器、JSON Pointer 或试运行表单。
- `desired_enabled` 仍只表示 Owner 意图；探测成功把流置为 `READY`、来源运行状态置为 `STOPPED`，不会宣称采集正在运行。
- 本轮只分发有界一次性探测任务，没有创建 `fetch_schedule`、长期调度、自动发现、画像、AI 或发布。

## 探测与安全

- 固定识别直接 RSS/Atom、Sitemap、JSON API、PDF，再检查 HTML 公开入口，最后识别受支持的公开列表结构。
- 每次请求执行精确 allowlist、逐跳 DNS/IP/peer 校验、DNS 重绑定防护、robots、HTTPS 重定向边界、5 秒单请求超时、2 次最大尝试、3 次最大重定向和 10 MiB 响应上限；单次运行最多 6 个逻辑 URL、30 秒。
- 登录、验证码、付费墙、MIME 伪造、私网/回环/元数据和越界重定向均失败关闭。响应字节先写入私有 SHA-256 对象键，再进行解析。
- 同一规范化 Origin 归入同一来源；重复 URL 和活动任务幂等。失败保留来源与原因，不替换已有健康流或配置。
- 暴露探测结果计数和待处理队列指标；队列持续非空 15 分钟触发 `PersonalSourceProbeQueueStalled` 告警。

## TDD 与迁移证据

- RED：契约、迁移、检测器、API、Worker 和页面测试因缺少 PERS-02 能力失败。
- GREEN：`make personal-source-test` 通过，包含 `0021 → 0022 → 0021 → 0022`、URL/Origin 幂等、同源多流、82 项 Python 定向测试和 Web 全套 114 项测试。

## 最终门禁

| 门禁 | 结果 |
| --- | --- |
| `make personal-source-test` | PASS（82 Python；114 Web；迁移回放 PASS） |
| `make lint` | PASS |
| `make typecheck` | PASS；mypy 132 个源文件及 Nuxt/TypeScript strict 通过 |
| `make test` | PASS；1255 passed，30 skipped；UI 53 + 114 passed |
| `make contract-test` | PASS；96 passed，生成物可复现 |
| `make security-check` | PASS；无 HIGH/CRITICAL 漏洞、配置错误或密钥泄漏 |
| `make fixture-replay` | PASS；364 passed，离线评估通过 |
| `make quality-gate` | PASS |
| `make web-e2e` | PASS；53 passed |
| `make web-a11y` | PASS；17 passed |

任一最终门禁失败时不得宣称完成或提交。
