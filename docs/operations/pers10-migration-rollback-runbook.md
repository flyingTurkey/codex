# PERS-10 迁移与回滚 Runbook

升级前执行 PostgreSQL `pg_dump -Fc` 并校验备份可读取；确认所有启用来源至少有一个 READY 个人流，且不存在 ACTIVE `LEGACY_GOVERNED` 调度。执行 `alembic upgrade 0030_pers10_role_archive_repair` 后查询 manifest，要求每类 `original_count = archive_count`，三个企业角色均不存在，并保存汇总哈希。若报告 `PERS10_ROLE_EXTERNAL_DEPENDENCIES`，先识别依赖数据库；只允许清理经确认、无连接且符合隔离测试命名的临时数据库，不得修改或删除业务数据库。

回滚命令为 `alembic downgrade 0028_automatic_relationships`，Alembic 必须依次执行 `0030 → 0029 → 0028`。0030 先验证三角色归档并恢复来源治理角色，再把角色 manifest 恢复为 0029 所需的两个角色；0029 再次校验全部归档后才恢复旧表、数据、约束、触发器和授权。任一差异都会抛出归档损坏错误并保持事务不变。随后按 `0028 → 0029 → 0030` 再次升级并比较 manifest。

禁止手工修补损坏归档后继续恢复。若归档校验失败，停止应用写入，保留数据库现场，从升级前物理/逻辑备份恢复到新实例，验证后切换。不得用部分 `INSERT` 或忽略失败类别恢复。
