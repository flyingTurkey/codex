# 个人研究模式架构

- 产品形态：本机单一 Owner，无企业模式开关
- 交互边界：回环地址上的固定 `owner`
- 业务事实：PostgreSQL
- 原始证据：私有对象存储

## 不可变边界

1. `desired_enabled` 只表达 Owner 意图；公网安全、robots、条款、版权、限速、预算、熔断和运行门禁共同决定实际运行状态。
2. 所有外部来源通过 `SourceAdapter` 接入。原始响应先进入私有对象存储，再解析；解析失败不得损坏原始证据。
3. 只有当前 accepted claims 与有效 Evidence ID 能形成证据事实。AI 候选、判断和运行状态独立保存，未通过证据门禁的内容不进入事实投影。
4. `PublicationService` 是发布状态以及 Feed、搜索、日报和相关读取投影的唯一业务写入路径；原文或 accepted claims 变化会使旧摘要和投影失效。
5. R3 只通过服务端投影暴露有限元数据与待审核状态；R4 只进入隔离区。完整数据不得先发送到浏览器再隐藏。
6. PostgreSQL 是业务事实唯一权威；Redis 只承担缓存、锁和队列；对象存储默认私有。
7. API、Worker 和 Publisher 使用最小权限内部主体。旧企业角色不属于当前产品身份模型。

## 运行图

```text
Loopback Owner
  → Nuxt Web
  → Personal/v1 API ───────────────→ Source、收藏、日报、版本、关系、AI 设置
  → Intelligence/v2 API ───────────→ Feed、搜索、热点、Reader、Owner 复核
                    │
                    ├→ PostgreSQL（权威事实、门禁、审计、投影）
                    ├→ Redis（队列、锁、缓存）
                    └→ private object storage（raw、附件、OCR、哈希）

SourceAdapter
  → SourceAdmission / runtime gates
  → raw object / DocumentVersion
  → policy-bound AI and deterministic processing
  → accepted claims ↔ evidence
  → PublicationService
  → v2 projections
```

来源 URL 必须先经过公网地址、逐跳重定向、robots、条款、版权、限速和预算门禁。调度器只领取已获得服务端运行授权且未被 Owner 停用的流，并在实际 I/O 前重新验证权威状态。

## 模块边界

- `apps/web`：Nuxt/Vue Owner 界面，只消费服务端投影，不持有发布或来源授权。
- `apps/api`：模块化单体、权威业务服务和 API；模块不得直接读取其他模块的 ORM 表。
- `apps/worker`：复用 API 侧业务服务与契约，执行采集、解析、AI 和耐久任务，不复制门禁。
- `packages/contracts`：共享枚举、Schema 和生成契约。
- `infra`：Compose、数据库角色、观测与部署配置。

v1 保留收藏、日报、引用、版本/diff、关系纠正、来源和 AI 设置；v2 提供 Feed、搜索、热点、Event Reader、媒体与 Owner 复核。详情见 ADR-0002。

## 发布与失效

候选、模型输出或页面按钮不能直接写发布状态。`PublicationService` 使用当前 SourceAdmission、DocumentVersion、accepted claims、evidence、复核、风险、安全扫描与 suppression 事实统一评估。

原文变更、撤回或更正时：

1. 保存新的 DocumentVersion 或来源状态事实；
2. 失效旧 claims、`SourceExcerpt` 与 AI 摘要候选；
3. 由耐久任务重新处理当前版本；
4. 只经 `PublicationService` 撤销、重建或拒绝读取投影；
5. 保留历史事实和审计记录。

Feed suppression 不删除原始材料。安全 hold 在排序、分页、详情和媒体授权之前失败关闭；Owner 允许决定仍需重新通过 `PublicationService`。

## 运行模式

`make dev-lite` 启动核心和 automation 执行平面，默认停止 discovery、AI 和 observability。`make dev` 启动完整 profile。两种模式只控制服务集合，不改变 SourceAdmission、AI 授权或发布门禁。

本地正式数据保存在 `D:\SRBGData\srbg-data.vhdx` 的 ext4 文件系统，Compose 从 `/mnt/host/wsl/SRBGDataDisk/srv` 挂载七类状态目录。挂载失败时不得隐式创建空卷继续运行。

## 历史治理与恢复

旧企业治理数据保留在只读归档中，仅用于迁移完整性、历史审计和受控恢复；业务代码不得依赖该归档。历史 PERS 迁移、角色退场和 Owner Gold 记录不能反向定义当前产品能力。

数据库恢复优先使用经过哈希与隔离恢复验证的备份或 VHD 恢复点，不把破坏性 Alembic downgrade 当默认回滚。当前操作见[个人平台备份恢复](../operations/personal-backup-restore.md)；历史企业流程见[失效企业流程说明](../ENTERPRISE-PROCESSES-RETIRED.md)。
