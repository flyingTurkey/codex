# 个人平台备份恢复

业务持久化根目录为 `D:\SRBGData`。Docker Desktop 程序和镜像不迁移；PostgreSQL、WAL、MinIO、Anchor MinIO、Redis、Prometheus 与 Grafana 的在线数据保存在 `D:\SRBGData\srbg-data.vhdx` 的 ext4 文件系统中，并由 Docker Desktop 通过 `/mnt/host/wsl/SRBGDataDisk/srv` 访问。备份、测试结果和报告分别保存在 `D:\SRBGData\backups`、`test-results` 和 `reports`。

## 启动与失败关闭

Windows 启动前执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/mount_personal_data.ps1
make runtime-ready
```

挂载脚本只接受 `D:\SRBGData` 内的 VHD，检查七个服务目录后才允许 Compose 启动。VHD 不存在、挂载失败或目录不完整时以 `PERSONAL_DATA_MOUNT_FAILED` 退出；不得临时改回空卷继续运行。`.env` 中的 `SRBG_DATA_ROOT` 必须是 `/mnt/host/wsl/SRBGDataDisk/srv`，自动发现保持 `false`。

## 备份

备份前统计在线数据量与 D 盘空间；可用空间必须不少于当前数据量三倍且至少 20GB。停止写入后同时保存：

- PostgreSQL 事务一致的 `pg_dump -Fc`；
- PostgreSQL 数据目录和 WAL 归档的离线 tar；
- 两套对象存储、Redis、Prometheus、Grafana 的离线 tar；
- 每个备份文件的 SHA-256、数据库表记录数/关键表哈希、对象版本数量/字节数/规范化清单哈希；
- 当前 Alembic 头和 Git 提交。

备份必须包含只读 `legacy_governance_archive`，不得只备份 `public`。Secret 不写入备份清单、日志或报告；需要单独迁移时使用受保护目录和最小权限。

## 隔离恢复验证

任何切换或试点前，先恢复到全新的隔离容器，禁止覆盖在线实例。依次验证：

1. 备份文件 SHA-256 与清单一致；
2. Alembic 头为 `0032_controlled_run_worker_read`，并核对受控运行、来源绑定和物理请求表的记录数；
3. 关键表记录数和规范化哈希与备份基线完全一致；
4. 对象版本数量、字节数和规范化清单哈希完全一致；
5. 归档 manifest 数量/哈希一致，三个退场角色不存在；
6. accepted claims 到 Evidence ID 双向引用有效，PublicationService 投影代次一致；
7. Redis、Prometheus 和 Grafana 可从备份启动并通过健康检查。Redis 是非权威数据，带 TTL 的键可能自然到期，但原始 AOF 备份哈希必须一致。

任一数量、哈希、对象或迁移验证失败，立即停止；不得修改原数据库、切换目录或启动试点。

## 切换与回退

恢复验证通过后，停止全栈，把已验证数据恢复到 VHD 的七个目录，再执行挂载脚本和 `make runtime-ready`。通过 `docker inspect` 确认全部业务挂载来源都位于 `/mnt/host/wsl/SRBGDataDisk/srv`，随后重新核对数据库与对象指纹并运行 Compose Smoke。

原 Docker named volumes 只停止使用并保留，不得自动删除。若 D 盘切换后验证失败，停止新栈，保留 VHD 现场，重新启用原卷并按切换前指纹验收；不要把部分新数据合并回旧卷。

数据库降级严格执行 PERS-10 Runbook 的 `0030 → 0029 → 0028`。归档损坏必须拒绝降级；不得手工跳过验证或恢复部分数据。

恢复到 0031 后还要核对 `personal_controlled_run.requests_reserved` 与物理请求记录数、`bytes_settled` 与已结算响应字节汇总。存在活动或未结算请求时不得切换恢复库；0031 有运行事实时拒绝直接降至 0030。
