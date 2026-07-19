# Handoff：DeepSeek“已启用但没有实际处理结果”诊断回传

日期：2026-07-19

## 诊断结论

“Secret/配置已启用”不是内容处理授权。现场有 10 条 outbox 伪停在 `WAITING_AI`，关联 pipeline 已失败且没有成功步骤；运行容器仍是旧代码，数据库为 `0033`。一条代表链路在模型任务已预留预算后、callback 落库前被人工停用来源，旧 callback 只写了泛化 `RUNTIMEERROR`，没有关闭 outbox 或结算预留。runtime probe 另外被 PostgreSQL timestamp 参数歧义和错误 model 映射阻断，Owner 页面无法得到真实健康状态。

## 修复

- 新增 `0036_ai_content_result_lifecycle`：用最小权限 `SECURITY DEFINER` 函数原子关闭 pipeline/outbox，并迁移历史伪等待状态；Worker 没有获得 outbox 直接写权限。
- callback 在读取步骤输入前复核授权。撤权时 fail closed：不读取既有 AI 结果、不保存或消费模型输出、不触发 repair，不生成 claims/summary/Event/投影；结构合法的已计费响应结算真实 usage/cost，畸形响应以未知用量结算，均稳定记录 `AI_RUNTIME_AUTHORIZATION_DENIED`。
- 修复 runtime probe 的 PostgreSQL timestamp cast 和 catalog model 映射。Owner API 现在显示 `configured=true`、`available=false`、`CONFIGURED_UNAVAILABLE/NO_RECENT_REAL_SCHEMA_SUCCESS`。
- 本地 compose 已升级到 `0036` 并重建 API、Worker、Parser、Publisher、Scheduler、AI Worker 和 Web。原始红色反馈从 `stuck_without_result=10` 变为 `0`。

## 测试命令

环境没有 Windows `make`，实际逐条执行了 Makefile 对应命令：Ruff/ESLint/tokens、mypy/TypeScript、Python/UI/Web 全量测试、契约生成与测试、fixture replay、Round09 评估、pip-audit、pnpm audit、Trivy、Web E2E 和 a11y。

结果：修复后重跑 Python `1066 passed, 27 skipped`；UI `53 passed`；Web `92 passed`；contracts `93 passed`；fixture replay `354 passed`；E2E `58 passed`；a11y `18 passed`；安全门禁通过。缺陷专项在显式本机 PostgreSQL 变量下 `9 passed`（包含真实 finalizer 状态转换），AI 链路定向集 `56 passed`。

## 仍存在的限制

- 当前 `admitted_running_sources=0`、`trial_current_documents=0`；没有合法内容可调用 DeepSeek，因此真实 Schema 成功仍为空，工程/生产 closeout 都是 `NO_GO`。没有为了验收启用来源或绕过门禁。
- 7 条历史 callback 已丢失的 `RESERVED` 预算记录没有可信 provider usage，不能事后伪造 Token/费用；需后续单独账务对账或人工处置。
- 真实内容成功需要服务端形成一个 ADMIT、RUNNING 来源和 CLEAN 当前 TRIAL/PRODUCTION 文档，再从 durable outbox 重放；模型成功仍不等于 PublicationService 发布成功。

## Commit

Owner 已明确授权将尚未提交的 v2 前置改动与本修复作为同一原子切片提交。实现 commit：`9e404a0651092d16f166e79fbaa6c3842671f7d5`（`feat(intelligence): deliver v2 closeout and durable AI results`）。
