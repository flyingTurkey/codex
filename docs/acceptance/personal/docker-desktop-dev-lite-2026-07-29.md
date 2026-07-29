# Docker Desktop 本地轻量运行验收（2026-07-29）

## 裁决

本轮结论为 `PASS`。默认本地开发入口已从完整模式的 18 个长期容器收敛为 12 个长期容器，并保留个人研究平台正常工作所需的数据库、缓存、对象存储、恶意文件扫描、API、Web 和自动化执行平面。

“单进程”不是合理目标。PostgreSQL、Redis、两套私有对象存储、ClamAV、API、Web，以及具有不同凭据和信任边界的 Worker、Parser、Publisher 必须保持隔离。轻量化目标是减少不必要的常驻能力、任务执行槽、探针频率、日志和指标保留，而不是把这些边界压进一个故障域。

最终状态：

- `IMPLEMENTATION=PASS`
- `FORMAL_DEV_LITE_RUNTIME=PASS`
- `FULL_TO_LITE_TRANSITION=PASS`
- `FORMAL_DATABASE_REVISION=0054_policy_optimization`
- `ANONYMOUS_VOLUME_LEAKS=0`
- `SINGLE_PROCESS=NOT_A_GOAL`

正式数据库迁移与恢复点证据见
[formal-0054-migration-2026-07-29.md](formal-0054-migration-2026-07-29.md)。

## 固定范围

- 候选来源：`codex/issue-40-integration`
- 候选基线：`889aab64fc140b1207bcb841be643829d30b965a`
- 最终集成分支：`codex/issue-40-docker-lite`
- 正式迁移执行提交：`42dc786e0de7d7a4809fda2dd44f5a98edd1ef53`
- Compose 项目：`srbg-intelligence`
- 正式 PostgreSQL 端口：`127.0.0.1:15432`
- 正式数据根：`/mnt/host/wsl/SRBGDataDisk/srv`

本轮没有改变业务 Schema 之外的产品边界、来源准入、Owner 意图、发布状态、真实 AI 配置或公网采集授权。

## 运行模型

Compose 按能力拆为四组：

| 组 | 服务 | 轻量模式 |
|---|---|---|
| 无 profile 核心 | PostgreSQL、Redis、ClamAV、两套 MinIO、API、Web，以及 5 个一次性初始化/迁移任务 | 启用 |
| `automation` | worker、parser、personal-source-worker、publisher、scheduler | 启用 |
| `discovery` | source-discovery | 停止 |
| `ai` | ai-worker | 停止 |
| `observability` | Prometheus、Alertmanager、Grafana、OpenTelemetry Collector | 停止 |

`make dev-lite` 启用核心和 `automation`，并显式停止其余六个可选服务。`make dev`、`make runtime-ready`、`make setup` 和 `make down` 保留完整 profile 语义。

轻量模式仍保留自动化执行平面，因为现有来源运行投影不读取 Worker heartbeat。若只保留纯阅读核心，页面可能继续显示来源在运行，而 Owner 操作会停留在 `QUEUED`。在服务端增加可验证的执行平面暂停事实之前，隐藏这一不一致不是可接受优化。

## 资源约束

### Worker

Worker 默认参数为：

```text
--concurrency=${SRBG_WORKER_CONCURRENCY:-1}
```

最终 `docker top` 显示一个 Celery 主进程和一个 prefork 子进程，两者命令均为 `--concurrency=1`。这里的“1”表示一个任务执行槽，不表示 Celery 只使用一个 OS 进程。

### 健康检查

8 个显式健康检查统一为：

- 启动期 `start_interval: 3s`
- 启动宽限 `start_period: 30s`
- 稳定期 `interval: 30s`
- 连续失败 `retries: 4`

稳定运行时降低探针频率，启动仍快速收敛；稳定期故障约两分钟进入 unhealthy。

### 日志和指标

18 个长期服务统一使用 `json-file`，默认 `max-size=10m`、`max-file=3`。Prometheus 同时限制：

- `--storage.tsdb.retention.time=15d`
- `--storage.tsdb.retention.size=2GB`

两项限制以先达到者为准。

### 一次性任务和 Alertmanager 卷

`role-bootstrap` 与 `role-init` 使用 PostgreSQL 镜像。两者以 tmpfs 覆盖镜像声明的 `/var/lib/postgresql/data`，避免每次重建产生匿名 PGDATA 卷。

完整模式首次切换复验又发现 Alertmanager 镜像声明了 `/alertmanager`，原 Compose 未覆盖，因而新建了一个匿名卷。该问题按 TDD 修复为：

```text
/alertmanager:uid=65534,gid=65534,mode=0750
```

这是供镜像内 `nobody` 用户写入的 tmpfs。初版无 uid/gid 的 tmpfs 会因权限不足导致 Alertmanager 重启，测试和运行配置随后补齐所有权参数。验证期间产生的唯一匿名卷和故障容器已按精确 ID 清理；未删除任何命名卷。

## 正式轻量运行证据

最终正式 VHD 上的轻量模式实测：

| 项目 | 结果 |
|---|---:|
| Compose 容器条目 | 17 |
| 长期运行容器 | 12 |
| 一次性任务 `Exited (0)` | 5 |
| discovery / AI / observability 容器 | 0 |
| Docker 卷总数 | 188 |
| 项目匿名卷挂载 | 0 |
| 项目内存瞬时样本 | 2687.68 MiB |
| `docker stats` PID 瞬时样本 | 82 |
| Worker OS 进程 | 2 |
| Alembic revision | `0054_policy_optimization` |
| API `/health/live` | HTTP 200 |
| API `/health/ready` | HTTP 200，三项依赖均 up |
| API `/api/v2/feed?limit=1` | HTTP 200 |
| Web `/` | HTTP 200 |
| Web 代理 Feed | HTTP 200 |
| `scripts/smoke.py` | `PASS` |

12 个长期容器中，8 个定义了 healthcheck 且均为 healthy；Parser、Personal Source Worker、Publisher 和 Scheduler 没有 Compose healthcheck，均为 running。

另一次轻量样本为 2692.05 MiB、77 PIDs。ClamAV 约占 977.6 MiB，是最大单项；这说明剩余资源的主要来源是上传安全门禁，而不是 Worker 多并发。`vmmemWSL` 还包含 Docker VM、镜像构建缓存和其他 41 个运行容器，不作为本项目独占内存指标。

## 完整模式与回切

完整 profile 实测：

| 项目 | 结果 |
|---|---:|
| Compose 条目 | 23 |
| 长期运行容器 | 18 |
| 一次性任务 `Exited (0)` | 5 |
| `scripts/smoke.py` | `PASS` |
| Docker 卷总数 | 188 |
| 项目匿名卷 | 0 |
| Alertmanager `/alertmanager` | tmpfs |

随后执行完整模式到轻量模式的回切：

- 六个可选服务全部停止；
- 为使 Docker Desktop 最终视图保持清晰，本次验证创建的六个可选容器随后被删除，持久目录和命名卷未删除；
- 最终恢复为 17 个项目容器、12 个长期运行容器、5 个正常退出的一次性任务；
- Smoke 再次通过，数据库仍为 `0054_policy_optimization`；
- Docker 卷总数保持 188。

## 失败关闭记录

### 首次轻量启动的端口冲突

隔离工作树最初没有被 Git 忽略的本地 `.env`。虽然临时 Compose 覆盖传入了主工作树 `--env-file`，Make 导出的默认 `POSTGRES_PORT=5432` 优先，因而与未触碰的 `quant_stock_postgres` 冲突。

该次运行失败关闭：

- API、Worker 等业务写入者保持 Created，未进入运行；
- 精确对 `srbg-intelligence` 执行全 profile `down --remove-orphans`；
- 项目容器和网络清零；
- 其他 41 个运行容器未停止；
- PostgreSQL 返回 clean shutdown，revision 仍为 `0054`。

随后只把主工作树中已忽略的 `.env` 原样复制到最终工作树；长度和 SHA-256 相同，目标仍被 Git 忽略且未提交。标准入口解析回 `15432` 后重试通过。

### Alertmanager tmpfs 权限

首次以无所有权参数的 tmpfs 覆盖 `/alertmanager` 时，Alertmanager 因无法创建 `data/` 而重启。日志明确为 `permission denied`。配置补充镜像用户的 uid/gid/mode 后，容器变为 healthy，完整模式恢复 18 个长期服务，卷数保持 188。

两次失败都保留了故障证据、先验证原因再修复，没有以忽略状态或降低门禁方式宣称成功。

## 质量门禁

最终提交前执行并通过：

| 门禁 | 结果 |
|---|---|
| Ruff | `PASS` |
| mypy strict | `PASS`，156 个源文件 |
| Python pytest | `PASS`，1561 passed / 27 skipped |
| UI lint / typecheck / test | `PASS`，53 tests |
| Web lint / typecheck / test | `PASS`，106 tests |
| Tokens / 生成契约 TypeScript | `PASS` |
| 契约可复现检查 | `PASS` |
| 契约 pytest | `PASS`，123 tests |
| pip-audit | `PASS`，105 个依赖、0 漏洞；3 个仓库内本地包跳过 |
| pnpm production audit | `PASS`，0 漏洞/公告 |
| Trivy Secret/Misconfiguration | `PASS`，1288 个文件、0 HIGH/CRITICAL |
| 正式轻量 / 完整 / 再轻量 Smoke | `PASS` |
| Compose 轻量 / 完整渲染 | `PASS` |
| `git diff --check` | `PASS` |

由于没有修改前端实现，也没有执行采集或内容处理，本轮不触发 `web-e2e`、`web-a11y`、`fixture-replay` 和 `quality-gate` 的附加条件。

## 回滚

运行配置回滚：

- 恢复完整模式：`make dev`
- 停止全部已知 profile：`make down`
- 临时提高 Worker 并发：在本地 `.env` 设置 `SRBG_WORKER_CONCURRENCY` 后重建 Worker
- 回滚本轮代码：撤销 Docker 轻量化、角色任务 tmpfs 和 Alertmanager tmpfs 对应提交

正式数据库不能把 Alembic downgrade 当作主回滚。其主恢复点、哈希、停写边界和 VHD 恢复步骤见正式迁移验收记录。
