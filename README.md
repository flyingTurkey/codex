# 四川路桥·智安情报

本仓库是绑定本机回环地址、由单一 `owner` 使用的个人研究平台。它覆盖公开来源添加与探测、受控采集、来源健康与画像、证据化内容、Feed、搜索、日报和自动关系；不提供企业模式开关、审批工作台或 `source_admin`、`platform_admin`、`reviewer` 等产品角色。

## 当前架构

- Web：Nuxt 4、Vue 3、TypeScript strict、Tailwind CSS、Nuxt UI 4。
- API/Worker：Python 3.12、FastAPI、Pydantic、Celery。
- 权威事实：PostgreSQL；Redis 只用于缓存、锁和任务队列。
- 原始证据：私有对象存储，始终先保存原始响应再解析。
- 发布边界：`PublicationService` 是 Feed、搜索和日报投影的唯一写入路径。
- 身份：仅回环地址固定 `owner` 和必要的内部数据库/Worker 服务主体。

公网安全、robots、条款、逐跳 SSRF 校验、限速、预算、熔断和原始证据保留不会因个人模式降低。证据事实与 AI 判断保持不同语义；无证据的关键数字和日期不得发布，未验证 AI 不得进入事实索引。

## PERS-10 企业治理退场

数据库头为 `0031_controlled_personal_runs`。`0029` 在同一事务中归档旧治理关系；`0030` 补齐三个企业数据库角色的规范快照并删除最后的来源治理角色；`0031` 只新增无人值守真实试点的内部预算与停止账本，不恢复任何企业治理能力。归档保存规范化 JSON、逐行 SHA-256、分类计数和分类汇总 SHA-256；数量、哈希、角色状态或跨数据库依赖不一致时拒绝退场。正常业务角色没有归档 Schema 使用权，业务代码禁止读取归档。

降级先重新验证每行和每类 manifest，损坏时以 `PERS10_ARCHIVE_CORRUPT`/`PERS10_ARCHIVE_HASH_MISMATCH` 中止；验证通过后恢复旧表、数据、约束、触发器、授权和 0029 前调度函数。操作见[迁移回滚 Runbook](docs/operations/pers10-migration-rollback-runbook.md)和[备份恢复说明](docs/operations/personal-backup-restore.md)。

旧 `/api/v1/admin/**` API、企业后台任务、生成契约、页面组件、运行时模块和企业产品角色均已退场；只保留 `owner` 语义及必要内部服务主体。历史企业文档的状态总表见[失效企业流程说明](docs/ENTERPRISE-PROCESSES-RETIRED.md)。

## 本地运行

首次安装依赖并构建镜像：

```bash
make setup
```

```bash
make dev
make smoke
```

正式业务数据、备份与验收报告的持久化根目录是 `D:\SRBGData`。七类在线服务数据位于 `srbg-data.vhdx` 的 ext4 文件系统；`make dev` 和 `make runtime-ready` 会先执行 `scripts/mount_personal_data.ps1`，挂载或目录校验失败时拒绝启动。切换前必须按备份恢复说明完成隔离恢复验证，不得直接移动仍在使用的数据目录；原 Docker 数据卷只停用并保留。

Web 与 API 默认只绑定 `127.0.0.1`。不要把固定本地身份头、端口或数据库凭据代理到局域网或公网。Secret 只允许通过环境变量或 Git 忽略的本地 Secret 文件提供，不得提交到仓库。

个人操作说明见[个人使用手册](docs/user-guide/personal-research-platform.md)，架构和边界见[个人研究模式架构](docs/architecture/personal-research-mode.md)。

## 质量门禁

```bash
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make quality-gate
make personal-source-test
make personal-content-test
make personal-migration-test
make web-e2e
make web-a11y
```

`personal-migration-test` 使用隔离的真实 PostgreSQL 执行 `0028 → 0029 → 0030 → 损坏降级拒绝 → 0029 → 0028 → 0029 → 0030`，并覆盖已应用 0029 缺失角色快照的修复路径，再运行 30 个来源与 30 个内容固定样本评估。Fixture 和固定样本只用于确定性回归，不得冒充真实联网验收。

`personal-pilot-control-test` 另行执行 `0030 → 0031 → 0030 → 0031`。真实试点入口为 `powershell -File scripts/run_personal_pilot.ps1`；`-PreflightOnly` 只检查条件且绝不联网。试点严格绑定五个公开 URL，DeepSeek 在费用账本接入前按降级状态关闭。

PERS-10 实现与归档统计见[本轮验收记录](docs/acceptance/personal/round-pers10-legacy-retirement.md)；真实交通运输部链路、受控原文变化和失效证据见[最终个人平台验收](docs/acceptance/personal/final-personal-platform.md)。
