# 个人平台备份恢复

备份必须同时覆盖 PostgreSQL、私有对象存储及其版本/哈希元数据。数据库使用事务一致的 `pg_dump -Fc`；对象存储按 bucket 版本清单复制，并保存清单 SHA-256。备份中包含只读 `legacy_governance_archive`，不得只备份 `public`。

恢复到隔离实例后依次验证：Alembic 头 `0030_pers10_role_archive_repair`、归档 manifest 数量/哈希、三个退场角色不存在、原始对象哈希、accepted claims 到 Evidence ID 的双向引用、PublicationService 投影代次。需要降级时严格执行 PERS-10 Runbook 的 `0030 → 0029 → 0028`；归档损坏必须拒绝降级。完成验证前不得让 Worker 联网或开放调度。
