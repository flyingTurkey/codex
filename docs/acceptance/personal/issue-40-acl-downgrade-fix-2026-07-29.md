# Issue #40 迁移 ACL 修复与隔离复验（2026-07-29）

## 裁决

本轮在独立分支 `codex/issue-40-acl-downgrade-fix` 和独立工作树
`D:\CodexProjects\srbg-intelligence-platform\.cache\worktrees\issue40-acl-downgrade-fix-11971f6`
中，以 `codex/issue-40-integration` 的固定提交
`11971f6933d92c27e933bc246bd81629b4370b1f` 为基线，修复上一轮物理克隆验证发现的
降级权限漂移并复验：

```text
0047_owner_gold_override_go
  -> 0048_autonomous_policy_foundation
  -> 0049_autonomous_content_switch
  -> 0050_autonomous_handoff_state_order
  -> 0051_technical_exception_recovery
  -> 0052_feed_suppression_projection
  -> 0053_safety_exception_lifecycle
  -> 0054_policy_optimization
```

最终裁决：

| 门禁 | 结果 |
|---|---|
| 三处已知/新增降级 ACL 缺陷修复 | `PASS` |
| 逐版本真实 PostgreSQL ACL 等价复验 | `PASS` |
| `0047 -> 0054 -> 0047 -> 0054` 完整真实回放 | `PASS` |
| 正式数据只读物理克隆复验 | `PASS` |
| 完整退回 `0047` 的结构、数据和 ACL 指纹 | `PASS` |
| ACL/依赖修复五项仓库质量门禁 | `PASS` |
| 候选修复本地提交/合入/远端推送 | `EXECUTED_AUTHORIZED` |
| 正式 PostgreSQL 迁移 | `NOT_EXECUTED_NOT_AUTHORIZED` |

本裁决证明本轮修复在隔离环境和正式数据的只读物理副本上满足迁移与回滚要求。
Owner 已在后续消息中依次授权本地提交、快进合入、修复复验和远端候选分支推送；
该授权不包含正式数据库迁移，也不构成生产 closeout。

## 修复内容

### `0049 -> 0048`

`0049` 升级给 `srbg_worker_role` 增加：

- `qualification_policy_bundle_v2` 的 `INSERT`；
- `automated_qualification_decision_v2`、
  `qualification_policy_evaluation_v2`、
  `qualification_shadow_decision_v2` 的 `SELECT, INSERT`。

修复后的 downgrade 只撤销 bundle 表在 `0049` 新增的 `INSERT`，保留 `0048` 已有
`SELECT`；对其余三张候选表撤销 `SELECT, INSERT`。这关闭了复验中新发现的
`0049 -> 0048` ACL 漂移，同时不削弱旧 revision 的合法基线权限。

### `0052 -> 0051`

修复后的 downgrade 撤销 `srbg_publication_writer` 对既有
`feed_suppression_rule_v2` 的 `INSERT`，消除上一轮已确认的逐版本权限残留。

### `0054 -> 0053`

修复后的 downgrade 撤销 `srbg_api_role` 和 `srbg_worker_role` 对以下对象在
`0054` 新增的 `SELECT`：

- `publication_decision_v2`
- `event_suppression_match_v2`
- `feed_suppression_effective_v2`

`0053` 已有的 `ai_budget_*` 读取权限保持不变；`0054` 的函数交接和新函数仍按原
downgrade 顺序恢复或删除。

## 测试驱动证据

先扩展真实 Alembic 回放验证器，对 `public` schema 中的直接表/视图授权做排序快照，
再分别在 `0048`、`0051` 和 `0053` 比较升级后降级的 ACL。实现修复前，回放依次
复现：

```text
0049 downgrade did not restore the 0048 table ACL
0052 downgrade did not restore the 0051 table ACL
0054 downgrade did not restore the 0053 table ACL
```

最小修复后：

- 三个定向迁移测试文件共 `27 passed`；
- 真实回放通过
  `0048 -> 0049 -> 0048`、
  `0051 -> 0052 -> 0051`、
  `0053 -> 0054 -> 0053`；
- 完整 ACL 重复性回放
  `0047 -> 0054 -> 0047 -> 0054` 通过；
- 最终完整迁移输出到达 `0054_policy_optimization`。

中间 revision 的新自动比较范围是 `information_schema.table_privileges` 可见的
`public` 直接表/视图授权；它不把该查询描述为全部数据库对象 ACL。函数授权同时由
迁移顺序、定向测试、静态复审以及完整 schema+ACL dump 回退指纹覆盖。

## 正式数据只读物理克隆复验

### 隔离边界

- 正式 PGDATA 和归档目录仅以只读 bind mount 提供给一次性复制容器。
- 迁移只在任务专属 named volume 和隔离网络中的 PostgreSQL 副本上执行。
- 正式项目数据库未启动、未挂入迁移容器，也未执行 Alembic。
- 正式路径挂载过滤在复验前后均为 `0`。
- 任务容器、网络和 named volume 已删除；意外产生的两个空匿名卷经精确识别后删除，
  Docker 卷总数恢复为 `188`。

正式源验证前后哨兵保持：

```text
PG_VERSION:
54183f4323f377b737433a1e98229ead0fdc686f93bab057ecb612daa94002b5

global/pg_control:
5b3b7cdf09f10ae930c350a0a2eee1889e18713c63818d341b13408300642e88
```

复制时源和副本的 PGDATA 路径清单一致，归档路径清单一致；两端文件字节数分别为：

```text
PGDATA: 153375146
archive: 9613344768
```

正式 PGDATA、WAL 和 `alembic_version` 未被本轮修改；正式库仍处于
`0047_owner_gold_override_go`。

### `0047` 物理基线

```text
schema+ACL pg_dump SHA-256:
4fb52baf308129a7d8115d5179668fcf9e6c95c65ba71969b3fc9a7bc05ad312

full data pg_dump SHA-256:
f338bd9f80e79afe84b18833b5fe4880668938a0333e1763d6b923c325821e61

public direct table ACL SHA-256:
f7589b151e24d33c12f63b3f83e8b0bde1626c03e8da32f424b311d454b31a87
rows: 2244
```

基线业务计数：

| 表 | 行数 |
|---|---:|
| `source` | 178 |
| `document` | 1544 |
| `document_version` | 1595 |
| `event` | 72 |
| `intelligence_item` | 54 |

### 升级、逐段降级和完整回退

首次 `0047 -> 0054` 通过，`12` 张预期新表、`3` 个预期视图及正向授权均存在，
上述五项基线业务计数保持不变。

逐段降级结果：

- `0054 -> 0053`：六项新增 API/Worker 读取授权全部消失；既有 budget `SELECT`
  保留。
- `0053 -> 0051`：Publisher 对 `feed_suppression_rule_v2` 的 `INSERT` 消失；
  `0052` 投影对象消失。
- `0051 -> 0048`：Worker 对 bundle 保留 `SELECT`、不再有 `INSERT`；对三张候选表
  均无 `SELECT` 或 `INSERT`。

完整 `0054 -> 0047` 后：

- Alembic revision 精确为 `0047_owner_gold_override_go`；
- schema+ACL SHA-256 精确恢复基线；
- full data SHA-256 精确恢复基线；
- `2244` 条直接表 ACL 的 SHA-256 精确恢复基线。

从该降级副本再次升级到 `0054` 后，`12` 张表、`3` 个视图、授权和五项基线计数
再次通过；再升级 schema+ACL SHA-256 为：

```text
ec7ccd0e9cf09cf3c53c2bb53f8560c869e7380958d936d2014214f5429f102c
```

## 远端 CI 暴露的技术异常恢复回归

候选分支首次远端推送后，GitHub Actions run
`30439776057` 的 integration job 连续两次稳定复现同一失败：第一次 Owner 恢复成功，
恢复流水线再次耗尽后，第二次有效 Owner 恢复返回 `False`；后一条“存在两个 open
exception”是前一测试未清理状态造成的级联失败。

失败不是本轮 ACL downgrade 变更导致。根因是 `reconcile()` 按
`ai_pipeline_run.started_at DESC` 从同一文档的历史流水线中猜测当前失败流水线，
而 SourceStream handoff 使用墙钟、技术重试使用可注入时钟。旧固定测试时钟跨过
2026-07-24 后，原始流水线时间反而晚于恢复流水线，Owner exception 因而被重新绑定
回旧流水线；数据库恢复函数按 fail-closed 条件拒绝了不一致的请求。

最小产品修复改为读取每个 document version 唯一的
`source_content_outbox.pipeline_run_id`。该字段由既有恢复函数与 outbox 状态在同一
事务中切换，是当前工作流水线的权威绑定，不依赖历史时间排序，也不需要新增迁移。
投影还要求 outbox 已为 `DEAD_LETTER`、流水线已为
`FAILED/TECHNICAL_FAILED`；decision 与流水线终结之间的短事务窗口因此只会等待
下一轮 reconcile，不会提前错绑。该查询不要求 `0054` 新增的 nullable
`pipeline.policy_bundle_id`，因此不会漏掉升级前已经存在的在途流水线。
回归场景把注入时钟固定在 handoff 墙钟之前 30 天，并在第二轮耗尽后直接断言
exception metadata 已绑定到实际恢复流水线，随后仍通过公开 `retry_now()` 行为验证。

修复后的本地复验结果：

- `make lint` 与 `make typecheck` 通过，mypy strict 检查 156 个源文件；
- `make test` 通过：Python `1553 passed / 27 skipped`、UI `53 passed`、
  Web `106 passed`；
- `make contract-test` 通过，生成物可复现，`123 passed`；
- `make fixture-replay` 通过，`377 passed`，Round 09 证据、Schema、恶意样本和
  unsupported-expansion 门禁全部通过；
- `pip-audit` 与 `pnpm audit --prod --audit-level high` 均无已知漏洞，
  security scan 输入成功冻结为 `1286` 个文件。

Docker Desktop 引擎在本机复验期间无响应，因此未重启 Docker Desktop、未停止其他
项目容器，也未把本地 Trivy 容器超时冒充为通过。推送后的 Linux GitHub Actions
`quality` / `security` job 负责执行相同的完整 Trivy 门禁；`integration` job 负责
执行真实 PostgreSQL/MinIO、迁移 verifier 和本回归场景。

首次 follow-up CI run `30444040841` 已证明完整 quality/security 和迁移 verifier
通过，原二次 Owner recovery 失败也已消失。随后一条非重试错误场景发现测试隔离问题：
前一场景领取最终恢复任务并模拟接受后，没有把对应 compensation 从 `PROCESSING`
完结；30 天反向时钟令这条遗留租约在下一测试中可再次领取，导致全局
`claim_due()` 返回两条。成功路径现显式完成该 compensation，使测试数据库状态与
“恢复后接受”的叙述一致；这不改变生产恢复规则。

## 依赖安全门禁修复

最终门禁首次执行时，生产依赖审计发现任务期间新发布的三个公告。经 Owner 授权，
使用最小 workspace overrides 更新锁文件：

| 包 | 修复版本 | 公告 |
|---|---:|---|
| `brace-expansion` | `5.0.8` | `GHSA-mh99-v99m-4gvg`，High |
| `postcss` | `8.5.18` | `GHSA-r28c-9q8g-f849`，High |
| `tar` | `7.5.21` | `GHSA-r292-9mhp-454m`，Moderate |

`pnpm install --frozen-lockfile`、完整前后端测试和 `pnpm audit --prod` 均通过；
生产审计最终为 `0` 个已知漏洞。

## ACL 与依赖修复的既有质量门禁

| 命令 | 最终结果 |
|---|---|
| `make lint` | 通过；Ruff、design tokens、UI/Web ESLint 全绿 |
| `make typecheck` | 通过；mypy strict 156 个源文件，UI/Web/contracts 类型检查全绿 |
| `make test` | 通过；Python 1553 passed/27 skipped、UI 53、Web 106 |
| `make contract-test` | 通过；生成可复现，123 passed |
| `make security-check` | 通过；pip-audit 与 pnpm production audit 无已知漏洞，Trivy HIGH/CRITICAL 为 0 |

安全扫描输入为 `1286` 个文件。`pip-audit` 仅按工具语义跳过仓库内三个未发布到
PyPI 的本地包；Trivy `0.69.3` 的 secret/misconfiguration 扫描及三个 Dockerfile
检查均通过。

最终复审未发现 `0048` 至 `0054` 的剩余实际 ACL 不对称。`0050` 的函数替换保留
原 ACL，`0051`/`0053` 新函数在 downgrade 删除，`0054` 恢复 v3 handoff 的 Worker
执行授权并删除新增函数。

## 当前状态与下一授权点

- Owner 已授权本地提交、快进合入、修复复验和推送
  `codex/issue-40-integration`；远端 CI 作为候选分支最终门禁持续跟踪。
- 原候选工作树保持 clean；正式项目工作树的既有 Docker 优化改动未被覆盖。
- 正式数据库未迁移，当前仍是 `0047`。
- 任务级容器、网络、卷和候选迁移镜像均已清理。

正式数据库迁移仍是独立授权动作。执行前必须生成并验证可恢复的 PGDATA/VHD
物理快照。
