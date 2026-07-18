# PERS-10 迁移与回滚 Runbook

升级前执行 PostgreSQL `pg_dump -Fc` 并校验备份可读取；确认所有启用来源至少有一个 READY 个人流，且不存在 ACTIVE `LEGACY_GOVERNED` 调度。执行 `alembic upgrade 0029_legacy_governance_retirement` 后查询 manifest，要求每类 `original_count = archive_count`，并保存汇总哈希。

回滚命令为 `alembic downgrade 0028_automatic_relationships`。降级会先重新规范化归档 JSON并校验每行、每类数量和汇总哈希；任一差异都会抛出 `PERS10_ARCHIVE_CORRUPT` 并保持事务不变。验证通过后，迁移把原表及原数据、约束、触发器和授权移回 `public`，最后删除归档 Schema。随后可再次升级并比较 manifest。

禁止手工修补损坏归档后继续恢复。若归档校验失败，停止应用写入，保留数据库现场，从升级前物理/逻辑备份恢复到新实例，验证后切换。不得用部分 `INSERT` 或忽略失败类别恢复。
