# Handoff：土木工程情报 v2 工程收口活动

日期：2026-07-19

## Git 与基线

- 分支：`codex/round-10-feed-search-daily`
- 实施基线/当前 HEAD：`95648af292aa6ddbb31a8ff80098f9cec4e5dcc6`
- DeepSeek 生命周期修复 `9e404a0651092d16f166e79fbaa6c3842671f7d5` 已是 HEAD 祖先；本轮没有重复实现、合并或改写该提交。
- Alembic 单一 head：`0037_engineering_closeout_campaign`。
- 本轮改动尚未提交。工作区另有用户产生、与本任务无关的未跟踪目录 `docs/codex-kit/prototype/owner-reader-detail/` 和 `docs/research/`；本轮未修改或纳入本任务实现，仅由既有安全门禁作为当前可交付工作区的一部分统一扫描。

## 已实现

- `0037` 新增不可变 campaign 头与 append-only event，覆盖 prepare/start/finalize/restore、证据导出、历史预算对账和 acceptance-only 故障注入；包含最小 RBAC、有事实 downgrade 阻断及只读归档/审计验证函数。
- 新增 `make intelligence-v2-engineering-campaign ACTION=prepare|start|status|finalize CAMPAIGN_ID=<uuid>`。中断后 start 会重新确认 acceptance 服务环境；finalize 恢复原环境后才运行门禁，已有 RESTORED 但缺 readiness 时会继续生成，不会误报成功。
- 固定 20 个官方 HTTPS 来源，缺失 5 源只登记为 `CANDIDATE_ONLY`。样本 cutoff 固定为 campaign 启动时刻，最近 90 天按当前 DocumentVersion 去重后最多 30 条；不改变 `desired_enabled`，不设生产 `ACTIVE`。
- 来源评估从 durable policy/health/raw/claim/evidence 事实计算。数据库传输成功值使用 `SUCCEEDED`；缺少耐久 locked-negative 集时显式保存 `hard_negative_evaluated=false` 并强制 `PAUSE`，不把观测零泄漏冒充已验证零泄漏。
- runtime、来源、Feed、补偿、历史 `RESERVED` 对账、备份/对象清单、审计尾锚、v1 归档和 context 均导出到私有忽略目录。当前 campaign 的同名证据会原子发布到 closeout 根目录；缺失文件和旧 readiness 会先移除，避免跨 campaign 混证据。
- acceptance-only 故障注入仍要求合法真实 DeepSeek 调用前置条件。无 `ADMIT + RUNNING + CLEAN current` 文档时稳定拒绝，不制造真实成功、Token/费用、claim、Event 或投影。

## 实际活动

- Campaign：`019f79e1-5d04-73e5-880b-ab9ce5fb37f7`
- 私有证据目录：`.cache/intelligence-v2-evidence/019f79e1-5d04-73e5-880b-ab9ce5fb37f7`
- 活动从原 `test` 环境切到 `acceptance`。活动中一次误执行 `web-e2e` 的 `runtime-ready` 导致服务重建；已立即恢复 acceptance，但实际最大 observation gap 为 138.68 秒，超过 90 秒门禁。该缺口保留，不改写时间戳。
- 活动结论、manifest SHA-256、最终来源/Feed/AI 数量和恢复状态见本文“最终验收结果”。证据不含 API Key、令牌、Secret 值或采集正文全文。

## 执行命令

Windows 使用仓库内 make：

```text
.\.tools\make\tools\install\bin\make.exe intelligence-v2-engineering-campaign ACTION=prepare
.\.tools\make\tools\install\bin\make.exe intelligence-v2-engineering-campaign ACTION=start CAMPAIGN_ID=019f79e1-5d04-73e5-880b-ab9ce5fb37f7
.\.tools\make\tools\install\bin\make.exe intelligence-v2-engineering-campaign ACTION=status CAMPAIGN_ID=019f79e1-5d04-73e5-880b-ab9ce5fb37f7
.\.tools\make\tools\install\bin\make.exe intelligence-v2-engineering-campaign ACTION=finalize CAMPAIGN_ID=019f79e1-5d04-73e5-880b-ab9ce5fb37f7
.\.tools\make\tools\install\bin\make.exe intelligence-v2-closeout ACCEPTANCE_PROFILE=engineering
```

## 最终验收结果

- Campaign 已追加 `FINALIZED`（2026-07-19 11:19:01 UTC）和 `RESTORED`（11:19:26 UTC）；API、Worker、Parser、Publisher、Scheduler、AI Worker 和 Source Discovery 均已恢复原 `test` 环境，相关容器处于 running，API/Worker/AI Worker 为 healthy。
- 数据库 Alembic head 为 `0037_engineering_closeout_campaign`。活动备份 SHA-256：`d028446584c098f6a682748871192916be3ecffd92d7f51864e41fe63a48b811`；对象清单文件 SHA-256：`5128874b24404dad5f5c1e80703226a51ae59d05e322111d932a016af7d549a6`。只读预检通过且 `mutation_performed=false`。
- runtime observation 共 115 条，首末跨度 3628 秒；最大间隔 138.68 秒。真实 Schema 成功为 0，余额状态为 `UNKNOWN`。AI 原因：`AI_RUNTIME_OBSERVATION_GAP`、`AI_EXTERNAL_BALANCE_UNKNOWN`、`AI_REAL_SCHEMA_SUCCESS_INSUFFICIENT`、`AI_REAL_SCHEMA_SUCCESS_STALE`。
- 来源 20/20 有结论，均为 `PAUSE`；20 源样本数均为 0，均记录 `hard_negative_evaluated=false`。来源完整性检查通过，但没有来源被自动启用。
- Feed 投影/样本为 0，原因 `FEED_SAMPLE_INSUFFICIENT`。没有合格真实调用前置条件，故障注入未执行，原因 `AI_COMPENSATION_INCOMPLETE`。7 条历史 `RESERVED` 保持 `UNSETTLED_NO_TRUSTWORTHY_PROVIDER_USAGE`，无 mutation。
- 九项门禁均通过：lint、typecheck、test、contract-test、security-check、fixture-replay、quality-gate、web-e2e、web-a11y。最终全量 Python 为 `1083 passed, 27 skipped`，UI `53 passed`，Web `92 passed`；本轮未新增 skip。
- `make intelligence-v2-closeout ACCEPTANCE_PROFILE=engineering` 实际非零退出，最终 `decision=NO_GO`。稳定原因仅为上述 AI 四项、`FEED_SAMPLE_INSUFFICIENT` 和 `AI_COMPENSATION_INCOMPLETE`；20 源、工程门禁和只读预检已通过。
- Engineering readiness 内部 `manifest_sha256`：`4ae61768e8ef9131b869e300125397773e8a617b28dda83cbe483f96d526e4a0`；`readiness.json` 文件 SHA-256：`a10b0b84b834d1f403506492a052b1a0b5acc8314845cc9b58982ac9e2819f09`。同一证据在 production profile 下仍为 `NO_GO`，production manifest SHA-256 为 `8bcf08bc7beba430be9511de238df4865664f31924a317c13dbedea6008dc982`。

## 下一轮建议

1. 不要重做 0036 或本轮 0037；先核对本文件记录的 HEAD、diff、数据库 head 和 readiness hash。
2. 要取得新的 engineering GO，必须创建新 campaign，并在不重建 runtime 服务的情况下保持完整 1 小时观察；旧 campaign 的 138.68 秒缺口不可修补。
3. 先通过正式来源准入形成至少一个 `ADMIT + RUNNING` 来源和 CLEAN 当前 TRIAL/PRODUCTION 文档，再由 durable outbox 触发真实 DeepSeek Schema 成功；不得手工把来源改为 ADMIT/RUNNING。
4. 从隔离环境真实 FULL/R3 v2 投影形成至少 200 条 Feed。现有不足不得用 v1、fixture 或生成内容补齐。
5. 建立耐久 locked-negative 自动评估事实后才能把 `hard_negative_evaluated` 置真；仅有零计数不够。
6. 满足真实调用前置条件后重跑 acceptance-only 瞬态/永久故障注入，验证恢复、永久错误不重试、零重复副作用和零旧版本回填。

## 必读上下文

- `CONTEXT-MAP.md`
- `docs/contexts/acquisition/CONTEXT.md`
- `docs/contexts/evidence-ai/CONTEXT.md`
- `docs/contexts/intelligence-qualification/CONTEXT.md`
- `docs/contexts/publication-reader/CONTEXT.md`
- `docs/adr/0002-api-v2-empty-projection-cutover.md`
- `docs/adr/0003-intelligence-v2-closeout-profiles.md`
- `docs/acceptance/phase-2/intelligence-quality-reader-v2.md`
- `docs/srbg-deepseek-no-results-return-handoff-2026-07-19.md`
