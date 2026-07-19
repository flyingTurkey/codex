# Handoff：诊断并修复“DeepSeek 已启用但没有产生实际处理结果”

## 新任务目标

在 `D:\CodexProjects\srbg-intelligence-platform` 中诊断并修复：Owner 界面显示 DeepSeek 已启用或 Secret 已配置，但没有产生实际内容处理结果。

先用可复现证据确定任务停在哪个状态/队列/权威门禁，再以 TDD 做最小修复。不得把“已配置”、无网络 heartbeat、mock 输出或固定 canary 当作真实内容处理成功；不得降低发布、安全、来源准入或预算边界。

## 开始前

1. 完整阅读仓库根 `AGENTS.md`。
2. 检查 `git status --short`。工作区已有大量未提交的 v2 实现和用户改动，必须保留；遇到重叠变更先审查 diff，不要 reset、checkout 或覆盖。
3. 先做只读诊断。不要输出 Secret 文件内容、环境变量值、Authorization header、Cookie、原文正文或模型完整输入输出。
4. 当前会话没有确认任何真实 DeepSeek 成功。此前只读检查发现本地 compose 数据库的 Alembic head 为 `0033_controlled_ai_budget_bridge`，尚无 `0035` 的 v2 runtime/source assessment 表；宿主进程没有发现可用 AI Secret 配置。重新核实当前状态，因为新会话启动时环境可能已经改变。

## 必须先区分的三条 AI 路径

1. **AI 配置/状态页面**：Secret 保存成功只表示配置存在，不表示队列、预算、来源、文档版本和真实模型调用可用。入口参考 `apps/api/src/srbg_api/ai_admin/service.py`、`apps/web/app/components/AiConfigurationPanel.vue`、`apps/web/app/pages/settings/ai.vue`。
2. **来源画像 AI**：独立的 personal-source profile 路径，有本地 PARTIAL fallback；参考 `apps/worker/src/srbg_worker/source_profile.py` 和 `apps/worker/src/srbg_worker/app.py` 中 source-profile tasks。不要把画像结果误认为内容处理结果。
3. **内容处理 AI**：durable source-content outbox → `srbg.ai_content.start` → CLASSIFY → EXTRACT → SUMMARIZE → VERIFY。主要入口在 `apps/worker/src/srbg_worker/source_content_bridge.py`、`apps/worker/src/srbg_worker/app.py`、`apps/worker/src/srbg_worker/ai_content_preparation.py`、`apps/worker/src/srbg_worker/ai_app.py`。

固定 v2 canary 是第四条隔离路径：只证明真实 Schema 调用能力，不物化 AcceptedClaim、Event 或投影。参考 `apps/worker/src/srbg_worker/v2_canary.py` 以及 `apps/worker/src/srbg_worker/app.py` 中 `srbg.ai.v2_canary_dispatch/result`。

## 已确认的内容 AI 行为

- 外部内容先 raw-first 保存、扫描和解析；AI Worker 只接收受控请求，不直接访问数据库或对象存储。
- 内容 outbox 只传 ID；成功 claim 后才创建/取得 pipeline run，并投递 `srbg.ai_content.start`。
- 每次真实调用前，API Worker 重新加载当前文档和权威上下文。
- `authorize_real_run` 当前要求同时成立：
  - pipeline run 对应当前 `document.current_version_id`；
  - raw scan 为 `CLEAN`；
  -文档版本 execution domain 为 `TRIAL` 或 `PRODUCTION`；
  -来源 `desired_enabled=true`、未被人工停用、`runtime_state=RUNNING`；
  -该来源最新一条 v2 准入评估为 `ADMIT`；
  -DeepSeek budget policy 为 active。
- 真实调用固定 provider/model 契约、JSON object、temperature 0、禁止 thinking/stream/tools，并经过本地 Pydantic/JSON Schema 校验。
- 处理状态主链为 CLASSIFYING → EXTRACTING → EVIDENCE_GATING → SUMMARIZING → VERIFYING → SUCCEEDED。低相关或需复核分类会进入 `WAITING_CLAIM_REVIEW`，这不是“没有运行”。
- AcceptedClaims、摘要和投影必须继续经过证据门禁与 `PublicationService`；模型成功不等于发布成功。
- 30 秒 runtime probe 无网络、无正文，只能证明 AI 队列存活。6 小时 fixed canary 只在验收类环境和全部真实调用门禁成立时运行，且与发布链隔离。

## 已确认的失败与降级规则

- Secret 缺失：物理调用返回 `MODEL_DISABLED`；内容开始阶段降级，不生成伪结果。
- 余额不足：`PROVIDER_BALANCE_INSUFFICIENT`，记录余额不足事实，不自动重试。
- 当前版本、来源准入、来源运行态、raw scan、execution domain 或预算不满足：`AI_RUNTIME_AUTHORIZATION_DENIED`，fail closed。
- prompt injection：记录安全事实，降级为 `PROMPT_INJECTION_R4`，不得调用模型或发布。
- timeout/network/transient unavailable：可创建持久补偿运行，最多 3 次，退避 5/15/45 分钟，总墙钟不超过 2 小时。
- Schema/模型输出拒绝：最多一次受控 repair；第二次失败后 CLASSIFY 为 FAILED，后续步骤为 DEGRADED。
- SUMMARIZE/VERIFY 失败：保留题录、来源、AcceptedClaims/证据和明确失败状态，不生成替代事实或伪摘要。
- 永久输入错误、权限错误、余额不足、提示注入和不可修复 Schema 错误不得自动网络重试。
- mock provider 仅允许 test 环境；不得用 mock 证明真实 DeepSeek 已工作。

## 推荐诊断顺序

建立一个能稳定变红的反馈命令，再修复：

1. **确认用户所说的“结果”是哪一种**：来源画像、内容 pipeline、AI summary、AcceptedClaim、Event 投影还是 canary readiness。用数据库状态和页面/API response 证明，不靠猜测。
2. **确认运行版本一致**：检查当前代码、容器镜像/启动时间、Alembic head、Worker 注册任务与队列。重点排查“代码已有 0035/新任务，但运行容器仍是旧镜像/旧迁移”。不要为诊断直接迁移生产数据。
3. **沿 durable handoff 查一条具体 ID**，只打印 ID、枚举状态、reason code、时间和计数：raw object → document/current version → source-content outbox → ai pipeline run → step results → budget reservation/settlement → candidate/accepted claims → judgment/summary → publication outbox/projection。
4. **检查 Celery 路由和 Worker 消费队列**：parser 应消费 outbox/start/result；isolated AI Worker 应消费 `ai` 队列；callback 应回到受控 API Worker 队列。检查 pending/active/reserved/failed 计数和结构化日志 reason code，不打印 payload。
5. **逐项计算 `authorize_real_run` 门禁**，不要只看最终 false。最可能的静默断点包括：最新来源评估不是 ADMIT、来源未 RUNNING、document_version 不是 current、execution domain 仍为 FIXTURE/DEVELOPMENT、budget inactive、outbox 没有进入 WAITING_AI、运行容器尚未包含新代码。
6. **核对 Secret 可见性而不读取 Secret**：只检查目标 Secret 文件在 AI Worker 容器内是否存在、是否为普通文件、权限是否允许进程读取、长度是否大于零；输出只能是布尔值/权限元数据，不能输出内容或哈希。配置 UI 与 AI Worker 使用的挂载路径必须一致。
7. **确认真实请求结果分类**：检查 provider error code、HTTP 类别、预算是否 settle、callback 是否成功返回。日志中禁止出现正文、密钥或完整 provider response。
8. 修复后重放一条隔离 TRIAL 文档，证明至少经过预期状态链；若最终进入复核或降级，应解释为规则结果而不是伪装成成功发布。

## 优先测试 seam

- `apps/api/tests/test_ai_admin_api.py`：配置、固定 provider/model、Secret 不回显。
- `apps/api/tests/test_ai01_content_preparation.py`：DeepSeek payload、固定能力、Secret store、重试/repair、文档输入。
- `apps/api/tests/test_ai01_orchestration.py`：服务端授权、完整内容编排和 evidence gate。
- `apps/api/tests/test_ai_gateway.py`、`apps/api/tests/test_ai_pipeline_runtime.py`：严格输出、工具调用拒绝、prompt injection、accepted-claim-only summary。
- `apps/worker/tests/test_ai_worker_isolation.py`：AI Worker 隔离、runtime probe、mock 禁止、fixed canary 输入。
- `apps/worker/tests/test_worker.py`：Celery beat、queue route、canary 环境拒绝。
- `apps/api/tests/test_v2_ai_compensation.py`：瞬态与永久错误分类、补偿上限。
- `apps/api/tests/test_source_profile_ai.py`、`apps/worker/tests/test_source_profile_worker.py`：仅当问题属于来源画像路径时使用。
- 集成门禁入口：`make ai-content-preparation-test`；修复后按 `AGENTS.md` 执行 lint、typecheck、test、contract-test、security-check，涉及内容处理再执行 fixture-replay、quality-gate。

先为实际断点写失败测试。测试应断言可观察状态/reason code/side effect，而不是内部调用次数；不得通过放宽授权 SQL、禁用 Schema、吞异常、改成 mock 或直接写发布状态让测试变绿。

## 上下文与决策文档

不要在 handoff 内复制这些文档，直接阅读：

- `CONTEXT-MAP.md`
- `docs/contexts/evidence-ai/CONTEXT.md`
- `docs/contexts/intelligence-qualification/CONTEXT.md`
- `docs/contexts/publication-reader/CONTEXT.md`
- `docs/adr/0002-api-v2-empty-projection-cutover.md`
- `docs/adr/0003-intelligence-v2-closeout-profiles.md`
- `docs/acceptance/phase-2/intelligence-quality-reader-v2.md`
- `CHANGELOG.md` 当前 v2 条目
- `docs/codex-kit/assets/schemas/` 中对应 CLASSIFY/EXTRACT/SUMMARIZE/VERIFY Schema

## 完成标准

- 有一个在修复前稳定失败、修复后通过的回归测试。
- 能用一条隔离 TRIAL 文档和安全的 ID/状态证据说明真实调用是否发生、停在哪一步、为何产生或没有产生结果。
- Secret 配置、runtime probe、canary、内容处理和发布结果的语义不再混淆。
- 瞬态/永久错误、补偿、预算结算、旧版本失效和无重复副作用保持正确。
- 不降低来源、文档、风险、证据、Schema、预算或 PublicationService 门禁。
- 更新 `CHANGELOG.md` 和相应验收记录；所有适用门禁通过后才能宣称完成。

## Suggested skills

- `diagnosing-bugs`：先建立紧反馈循环并定位真实断点。
- `tdd-workflow`：用失败测试驱动最小修复。
- `verification-loop`：修复后分层验证状态链、回归与安全门禁。
- `security-review`：若问题涉及 Secret 挂载、日志或 provider 请求边界时使用。
