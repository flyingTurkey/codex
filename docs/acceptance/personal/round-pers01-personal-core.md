# PERS-01 个人模式基础与单一 Owner 验收记录

- 日期：2026-07-17
- 迁移：`0021_personal_source_core`
- 产品形态：本机单一 Owner
- 范围结论：只交付个人模式基础和来源控制，未实现 PERS-02 或后续能力

## 第一性原理与边界

- `desired_enabled` 是 Owner 意图，`runtime_state` 是实际运行事实；API 和页面分别投影，启用不会自动宣称运行。
- 手工停用写入 `manual_disabled_at`、不可变 `MANUAL_DISABLED` 事件并关闭旧 `enabled` 兼容开关；数据库触发器拒绝在标记存在时重新启用或写入 `RUNNING`。
- 公网安全、robots、限速、预算、raw-first、证据追溯、Schema 校验和 `PublicationService` 单一发布边界未放宽。
- 证据事实继续只来自原文证据和 accepted claims；AI 输出保持候选判断语义。

## 实现验收

- `owner` 已加入共享契约。个人 API 只接受固定本地 UUIDv7 Owner；旧角色只供旧代码兼容。
- `GET /api/v1/sources`、`GET /api/v1/sources/{id}` 和 `PATCH /api/v1/sources/{id}` 已实现；PATCH 只接受 `desired_enabled` 和 `display_name`。
- `/sources` 展示名称、URL、用户启停状态、运行状态和直接启停开关；`PENDING_CONFIGURATION` 显示“待自动配置”，不展示治理表单。
- Compose 继续绑定回环地址。远程 Owner 认证未实现，文档明确禁止把本地身份模式暴露到远程网络。

## TDD 与迁移证据

- RED：契约/API 测试因缺少 `PersonalSource*` 和 `owner` 导入失败；Web 测试因 `/sources` 不存在失败。
- GREEN：PERS-01 契约、API、静态迁移测试 14 项通过；Web 全套单元测试 112 项通过。
- 隔离 PostgreSQL 完成 `0020 → 0021 → 0020 → 0021`；验证单例 Owner 设置、默认关闭、运行状态独立、重复停用只产生一条事件及自动覆盖被数据库拒绝。

## 页面状态

- 桌面：1440×900 Playwright 场景覆盖来源状态与开关。
- 移动：390×844 Playwright 场景覆盖单列布局与开关。
- 无障碍：语义 `switch`、键盘操作、状态播报和 axe 扫描纳入 `make web-a11y`。

## 质量门禁

最终结果在提交前填写；任一门禁失败时不得提交。

| 门禁 | 结果 |
| --- | --- |
| `make pers01-test` | PASS |
| `make lint` | PASS（Ruff、ESLint、设计 Token 一致性） |
| `make typecheck` | PASS（mypy 130 个源文件、Vue/Nuxt/生成契约） |
| `make test` | PASS（Python 1232 passed / 30 skipped；UI 53；Web 113） |
| `make contract-test` | PASS（95；生成结果可复现） |
| `make security-check` | PASS（Python 无已知漏洞；pnpm 仅 1 个 low；Trivy 无 HIGH/CRITICAL） |
| `make web-e2e` | PASS（52） |
| `make web-a11y` | PASS（17，含个人来源 axe 场景） |

## 已知限制

- 仅支持本机回环访问，没有远程 Owner 认证。
- 不执行 URL 探测、自动配置、持续采集或自动画像。
- 旧角色、审批、治理表和后台页面尚未删除。
- Owner 启用只记录意图；在后续自动配置完成前，运行状态保持“待自动配置”。
