# PERS-04 自动来源画像与轻量纠错验收记录

## 范围与边界

本轮为所有已有来源排队生成工程行业、内容域、语言、国家/地区、声明角色、权威和独立性画像。画像不改变来源启停、运行授权、审核或发布状态；不实现全网自动发现和内容自动发布。

## 实现证据

- 迁移：`0024_automatic_source_profiles`，快照、模型尝试和 Owner 覆盖追加保存；输入哈希及规则、Prompt、Schema、模型版本完整留痕。
- AI：隔离 Worker、`json_object`、thinking/stream/tools disabled、本地严格 Schema、服务端 Evidence ID、防提示注入和最多一次受控修复。
- 降级：DeepSeek 不可用、余额不足或预算关闭时输出 `PARTIAL` 本地画像并执行有界后台重试，不修改采集计划。
- 页面：画像侧栏区分自动结果与个人覆盖；权威和独立性仅显示自动推断语义。

## 固定回放

`apps/api/tests/fixtures/source_profiles/manifest.json` 包含政府、研究出版、厂商、独立媒体、恶意提示和证据不足六类无网络样本，并绑定 PERS-04 回放测试。

## 门禁结果

2026-07-17 完整执行结果：

- `make lint`：通过，Ruff、设计令牌与前端 ESLint 均无错误或警告。
- `make typecheck`：通过，mypy strict 检查 135 个源文件，UI、Nuxt 与生成契约 TypeScript 检查通过。
- `make test`：通过，Python 1282 passed / 32 skipped，UI 53 passed，Web 115 passed。
- `make contract-test`：通过，生成产物可复现，103 passed。
- `make security-check`：通过，无 HIGH/CRITICAL 依赖、安全配置或 Secret 发现；pnpm 报告 1 个既有 low 严重度依赖项。
- `make fixture-replay`：通过，365 passed，PERS-04 六类固定画像样本包含在内。
- `make quality-gate`：通过，完整 lint、typecheck、test、contract 与 security 组合门禁通过。
- `make personal-source-test`：通过，迁移 `0023 -> 0024 -> 0023 -> 0024` 回放成功，151 个 Python 专项测试及 115 个 Web 测试通过。
- `make web-e2e`：通过，54 passed。
- `make web-a11y`：通过，17 passed，axe violations 为空。

当前状态：PERS-04 实现与全部强制门禁通过，可提交验收。
