# Docker Desktop 本地轻量运行验收（2026-07-29）

## 结论

本轮从“个人研究平台必须保持哪些事实与隔离边界”出发，优化默认启动集合、Worker 并发和本地数据保留，而不追求表面上的单容器或单进程。

- PostgreSQL、Redis 和私有对象存储继续是不同运行时。
- Parser 继续隔离不可信内容解析；AI Worker 不获得数据库或对象存储凭据；Publisher 继续使用独立发布写凭据。
- `make dev-lite` 保留 `automation` 执行平面，避免来源仍显示“实际运行中”但 Scheduler/Worker 已停止的错误状态。
- 轻量模式由完整模式的 18 个常驻容器降为 12 个；5 个一次性初始化任务成功后退出，不持续消耗 CPU。
- 隔离数据栈运行验收通过；正式 VHD 因既有迁移谱系与当前 checkout 不一致而保持关闭，数据库未被改写。

当前结论为：

- `IMPLEMENTATION=PASS`
- `ISOLATED_RUNTIME=PASS`
- `FORMAL_VHD_RUNTIME=BLOCKED_BY_EXISTING_MIGRATION_LINEAGE`
- `SINGLE_PROCESS=NOT_A_GOAL`

## 基线与范围

- 分支：`codex/issue-40-docker-lite`
- 固定起点：`889aab6`
- Docker Engine：29.6.1
- Docker Compose：5.3.0；支持本轮使用的 `start_interval`
- Docker Desktop：4.80.0
- Docker 可见 CPU：12
- 初始工作区已有另一轮审计修改：
  - `CHANGELOG.md`
  - `docs/research/project-history-memory-audit-2026-07-29.md`
  - `docs/acceptance/project-history-memory-audit-2026-07-29.md`

用户已明确允许保留这些并发改动并在其上增补；本轮没有删除或覆盖审计内容。

本轮修改 Compose、Make 入口、环境示例、运行冒烟、基础设施测试和说明文档。不改变生产业务 Schema、来源准入、Owner 意图、发布状态或真实 AI 配置。

## Docker 恢复与旧栈清理

Docker Desktop 当时显示运行，但 Engine 的 `version`、`ps`、Compose 查询和 `_ping` 均超时；`vmmemWSL` 工作集约 14.2GB。执行 `docker desktop restart` 后 Engine 恢复响应。

恢复后识别到 254 个 SRBG 容器，其中 219 个属于 13 个明确的旧测试项目：

- `srbg_issue41`
- `srbg-issue40`
- `srbg-issue43`
- `srbg-issue44`
- `srbg-issue45`
- `srbg-issue46`
- `srbg-unattended-11971f6`
- `srbg-unattended-rerun2-10d702f2`
- `srbg-unattended-rerun3-ef601c5`
- `srbg-unattended-rerun4-8ea461a`
- `srbg-unattended-rerun5-92fd809`
- `srbg-unattended-rerun6-fe1077a`
- `srbg-unattended-rerun7-db21b99`

清理使用每个项目的精确 Compose project label 和 `down --remove-orphans`，未使用 `--volumes`。少数旧 Compose 无法识别的孤立容器在核对 project/service 标签和挂载后按容器 ID 删除，仍未使用 `-v`。

| 安全核验 | 结果 |
|---|---:|
| 旧测试项目 | 13 → 0 |
| 旧测试容器 | 219 → 0 |
| 批次清理前后 Docker 卷 | 188 → 188 |
| 旧项目网络 | 全部删除 |
| `srbg-offline-p0-smoke-db21b99` | 未触碰 |
| 非 SRBG 项目 | 未触碰 |
| `D:\SRBGData` / `srbg-data.vhdx` | 未删除、未重建 |

正式项目旧容器随后也以 `down --remove-orphans` 下线，数据卷保持不变；历史恢复验证容器 `srbg-pers10-restore-pg-800286` 被删除，但同名恢复卷被保留。

## 运行模型

Compose 不带 profile 时只展开 12 个核心服务，其中 7 个常驻、5 个一次性：

- 常驻：PostgreSQL、Redis、ClamAV、业务 MinIO、审计锚点 MinIO、API、Web
- 一次性：`minio-init`、`anchor-minio-init`、`role-bootstrap`、`migrate`、`role-init`

能力分组如下：

| Profile | 服务 | 是否单独构成完整工作流 |
|---|---|---|
| `automation` | worker、parser、personal-source-worker、publisher、scheduler | 是，依赖无 profile 核心 |
| `discovery` | source-discovery | 否；需要核心和自动化生产/调度语义 |
| `ai` | ai-worker | 否；需要核心和自动化调用/回调语义 |
| `observability` | prometheus、alertmanager、grafana、otel-collector | 否；观测完整运行栈 |

`make dev-lite` 启用核心加 `automation`，共 17 个容器条目、12 个常驻进程边界；显式停止 discovery、AI 和 observability 六个服务。`make dev`、`make runtime-ready`、`make setup` 和 `make down` 显式启用全部 profile，保留原有完整模式语义。

纯阅读核心没有在本轮暴露为正常可写模式。原因是现有来源 `actual_running` 投影不读取 Worker heartbeat；若停掉整个执行平面，页面仍可能显示来源正在运行，Owner 操作也可能长期停在 `QUEUED`。该模式只能在未来加入服务端执行平面暂停事实和相应投影后实现。

## 资源约束

### Celery

主 Worker 原先没有 `--concurrency`，会按 Docker 可见的 12 个 CPU 创建默认 prefork 执行槽。本轮默认：

```text
--concurrency=${SRBG_WORKER_CONCURRENCY:-1}
```

隔离运行的 `docker top` 显示 Celery 主进程和 1 个执行子进程，共 2 个 OS 进程。这里减少的是任务槽和子进程，不宣称 Celery 变成单 OS 进程。

### 健康检查

8 个显式健康检查统一为：

- 启动期：`start_interval: 3s`
- 启动宽限：`start_period: 30s`
- 稳定期：`interval: 30s`
- 连续失败：`retries: 4`

因此正常运行时减少探测频率，启动仍快速收敛；稳定期故障约 2 分钟进入 unhealthy，不会因保留旧重试次数而放大到 6–10 分钟。

### 日志和指标

18 个常驻服务使用 `json-file`，默认 `max-size=10m`、`max-file=3`，单服务本地日志上限约 30MB。一次性初始化任务不属于长期日志上限范围。

Prometheus 默认同时使用：

- `--storage.tsdb.retention.time=15d`
- `--storage.tsdb.retention.size=2GB`

正式指标目录只读测量为 21.4MiB；现有 block 从 2026-07-15 23:00 UTC 到 2026-07-20 15:00 UTC。按观察到的约 4.7 天摄入量线性外推，15 天约 69MiB，2GB 容量有约 29 倍余量。两个上限以先达到者为准；若未来指标基数显著上升，容量上限可能早于 15 天清理，需继续监测 14 天报表覆盖。

### 一次性角色任务卷

`role-bootstrap` 和 `role-init` 复用 PostgreSQL 镜像，镜像默认声明 `/var/lib/postgresql/data` 卷。若不覆盖，两项任务每次重建都会产生无用途的匿名卷。本轮均用同路径 tmpfs 覆盖；运行验收会核对新容器前后 Docker 卷数不增加、任务退出码为 0，且两项任务都没有数据卷挂载。

## 隔离运行证据

由于正式数据库不可安全启动，本轮使用项目 `srbg-dev-lite-verify-20260729` 和任务专属 Docker 卷运行同一 Compose 配置，没有挂载正式 PostgreSQL、Redis、MinIO 或审计数据。

| 项目 | 实测 |
|---|---:|
| Compose 展开服务 | 17 |
| 常驻容器 | 12 |
| 成功退出的一次性任务 | 5 |
| discovery / AI / observability 容器 | 0 |
| 项目容器内存快照 | 2743.5MiB |
| `docker stats` PIDs 快照 | 72（包含线程） |
| 主 Worker OS 进程 | 2 |
| Web `/` | HTTP 200 |
| API `/health/live` | HTTP 200 |
| API `/health/ready` | HTTP 200；PostgreSQL、Redis、对象存储均 up |
| API `/api/v2/feed?limit=1` | HTTP 200 |
| Web 同源代理 `/api/v2/feed?limit=1` | HTTP 200 |
| `make smoke` | 通过 |

ClamAV 在该快照约占 1.08GiB，是项目内最大的单容器内存来源；它仍是上传失败关闭门禁，未为追求容器数或内存数字而移除。

`vmmemWSL` 同期约 15.6GB，但该值包含 Docker Desktop VM、镜像构建缓存和其他用户项目，不能作为本项目独占内存。项目级验收以同一时点的 12 个容器 `docker stats` 合计为准。

## 正式 VHD 阻塞

正式 PostgreSQL 挂载核验为：

```text
/mnt/host/wsl/SRBGDataDisk/srv/postgres -> /var/lib/postgresql/data
/mnt/host/wsl/SRBGDataDisk/srv/postgres-wal -> /wal-archive
```

与 `.env` 的 `SRBG_DATA_ROOT=/mnt/host/wsl/SRBGDataDisk/srv` 一致。迁移任务每次稳定失败：

```text
FAILED: Can't locate revision identified by '0047_owner_gold_override_go'
```

数据库 `alembic_version` 正是 `0047_owner_gold_override_go`；当前 checkout 和新构建镜像均不含该 revision，但 Git 其他历史线包含它。这证明阻塞来自既有数据库与当前分支迁移谱系不一致，不是 profiles、挂载或镜像缓存问题。

本轮没有修改 `alembic_version`、没有伪造 merge revision、没有重建正式数据库，也没有把隔离空库冒充正式业务数据。恢复正式运行前必须由 Owner 选定 canonical Git/迁移谱系，再按备份恢复流程验证。

## 测试与门禁

实施过程按 TDD 逐项观察 RED → GREEN，覆盖：

- 主 Worker 默认单任务槽并允许环境覆盖
- profile 分组、轻量/完整 Make 语义和停止清单集合一致性
- 执行平面在轻量模式继续运行
- 健康检查启动/稳定期与失败窗口
- 18 个常驻服务日志轮转
- Prometheus 时间/容量双上限
- `role-bootstrap` 和 `role-init` 均不再创建匿名 PostgreSQL 数据卷
- Smoke 使用 v2 Feed，且不把客户端水合前 SSR 壳误判为空状态缺失

| 命令 | 结果 |
|---|---|
| 定向基础设施与运行脚本测试 | 40 passed；覆盖本轮全部新增契约 |
| `make lint` | 通过；Ruff、设计令牌、UI/Web ESLint 全绿 |
| `make typecheck` | 通过；mypy strict 155 个源文件，Vue/Nuxt/生成契约 TypeScript 全绿 |
| `make test` | 通过；Python 1407 passed、27 skipped，UI 53/53，Web 105/105 |
| `make contract-test` | 通过；生成可复现，113 passed |
| `make security-check` | 通过；pip-audit 无已知漏洞（3 个本地包按工具语义跳过），pnpm 1 个 moderate、无 high，Trivy Secret/Misconfiguration 无 HIGH/CRITICAL |
| `make smoke` | 隔离 `dev-lite` 运行栈通过 |
| `docker compose config --quiet` | 核心、轻量和完整 profile 配置均可渲染 |
| `git diff --check` | 通过 |

本轮没有修改前端实现，也没有执行采集或内容处理，因此不触发 `make web-e2e`、`make web-a11y`、`make fixture-replay` 的附加门禁。运行时 Web/API/Feed 由隔离 Compose 栈和 `make smoke` 验证。

## 回滚

- 完整模式：`make dev`
- 停止全部已知 profile：`make down`
- Worker 并发临时提高：在本地 `.env` 设置 `SRBG_WORKER_CONCURRENCY` 后重建 Worker
- 日志/Prometheus 上限：通过 `.env` 中对应变量调整后重建容器
- 代码回滚只需撤销本轮 Compose、Make、Smoke 和测试改动；数据迁移未发生

不得通过删除 VHD、删除正式卷、手工改写 `alembic_version` 或把缺失 revision 标记为已应用来“修复”正式运行阻塞。

## 后续：Issue #40 候选迁移隔离验证

Owner 随后选定 `codex/issue-40-integration` 取代 #36 作为候选。本轮已在固定提交
`11971f6933d92c27e933bc246bd81629b4370b1f` 和正式 PGDATA 的只读物理克隆上完成
`0047 -> 0054 -> 0047 -> 0054`：

- 正向迁移、既有数据保全和二次升级可重复性通过；
- 表、数据和无 ACL 结构可精确退回 `0047`；
- Alembic downgrade 会残留两条 `publication_decision_v2 SELECT`，退到 `0051`
  时还会残留一条 `feed_suppression_rule_v2 INSERT`；
- 正式数据盘未被挂载为可写，任务容器、网络、卷、镜像和 worktree 已清理。

因此正式迁移更新为
`NO_GO_PENDING_DOWNGRADE_ACL_FIX`。完整证据见
[`issue-40-isolated-migration-validation-2026-07-29.md`](issue-40-isolated-migration-validation-2026-07-29.md)。
