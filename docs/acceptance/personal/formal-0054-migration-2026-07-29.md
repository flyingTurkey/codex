# 正式 PostgreSQL 0047 → 0054 迁移验收（2026-07-29）

## 裁决与边界

本地正式 PostgreSQL 已从 `0047_owner_gold_override_go` 迁移到
`0054_policy_optimization`，结果为 `PASS`。迁移前建立了字节一致、只读挂载复验的 VHD 主恢复点，并完成独立逻辑恢复；迁移时只有 PostgreSQL、角色引导和 Alembic 迁移任务运行，所有业务 Writer 在迁移后校验通过前保持停止。

本记录证明的是 Owner 授权的本地正式数据库迁移和本地 Docker 运行恢复，不等同于外部生产部署、真实来源运行、AI 授权或 production closeout。

## 固定输入

| 项目 | 值 |
|---|---|
| 分支 | `codex/issue-40-docker-lite` |
| Git 提交 | `42dc786e0de7d7a4809fda2dd44f5a98edd1ef53` |
| 候选来源 | `codex/issue-40-integration` / `889aab64fc140b1207bcb841be643829d30b965a` |
| 迁移镜像 | `sha256:d4731cb7aaee99eecd10dc7a950a30d6851af0d55c46fc158379fea0c1b1a274` |
| 完成时间 | `2026-07-29T12:14:23.7161901Z` |
| 迁移前 revision | `0047_owner_gold_override_go` |
| 迁移后 revision | `0054_policy_optimization` |
| Compose 项目 | `srbg-intelligence` |
| 正式 PGDATA | `/mnt/host/wsl/SRBGDataDisk/srv/postgres` |
| 正式 WAL archive | `/mnt/host/wsl/SRBGDataDisk/srv/postgres-wal` |

迁移链固定为：

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

Issue #40 的 ACL 对称回滚修复和 `0047 → 0054 → 0047 → 0054` 隔离复验是本次正式迁移的前置条件。其历史验收见
[issue-40-acl-downgrade-fix-2026-07-29.md](issue-40-acl-downgrade-fix-2026-07-29.md)；其中“正式迁移未执行”是该前置验收当时的事实，已由本记录取代。

## 迁移前停写与空间

迁移前确认：

- 正式 Compose 项目容器为 0；
- 没有容器引用正式 PGDATA；
- PostgreSQL 17.10 的 `pg_controldata` 状态为 `shut down`；
- 不存在 `postmaster.pid`、recovery signal、standby signal 或外部 tablespace；
- D 盘可用空间约 131.48 GiB，满足至少 VHD 三倍加 20 GiB 的操作余量；
- 其余 41 个运行容器未停止、未改写；
- 正式 PostgreSQL 启动后迁移前 revision 为 `0047_owner_gold_override_go`，其他数据库会话为 0。

停库后的关键哨兵：

- `PG_VERSION` SHA-256：
  `54183f4323f377b737433a1e98229ead0fdc686f93bab057ecb612daa94002b5`
- `global/pg_control` SHA-256：
  `d58ec260438f6701c6b3b6bb59278998407b4069f22940f68f8b9096c823fcda`

## 主恢复点与备份

恢复点目录：

```text
D:\SRBGData\backups\pre-0054-20260729T115449Z
```

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `srbg-data.vhdx` | 19,528,679,424 | `8dc37373d07fd5702a1091e917809324b088c100888c14af06b846e7dea4b842` |
| `postgres-physical.tar` | 9,785,085,440 | `25b00752a7fbd6113bac1c7068f98a968a9b2457f818f4c729231425403db584` |
| `postgres.dump` | 4,706,755 | `1d9638936548207e8fdf7d1cb66c3c509aa1b2959a2cd65f9e7d3d24ab5175c1` |
| `schema.sql` | 1,183,814 | `4c069512ca08fa2affca9d757fa5bddb8280eb8af27c94e11d85d90805c3cd4a` |
| `table-acl.txt` | 113,208 | `f738058a0f8e6e66d5158ff5dd458e172e4e3a50a71249a14b14b191c3b0cd23` |
| `backup-manifest.json` | 3,123 | `c65dd7216008159668ba8348468a19d4dfaa58b2a586f6a9dc598455ee68ae69` |
| `migration-result.json` | 1,718 | `c08b3d7ee3882baa345f6b227d8bc623b94e63380db32dabaabe737621216705` |
| `pre-0054-table-counts.tsv` | 9,323 | `02b8852d270d59a67a1343040ae52419981a69a6c25bd281c4b06090a7507e1a` |
| `post-0054-table-counts.tsv` | 9,811 | `ed391d8ab792c012360b2f656d2a3551abd4b71a91e3920416e5427e88787c01` |

VHD 源文件与快照的 SHA-256 完全相同。快照以独立 WSL 名称只读挂载，`findmnt` 显示 `ro,relatime`，并核对了七个服务目录、`PG_VERSION` 和 `global/pg_control`，之后正常卸载。

物理 tar 的完整清单共 3076 项，包含：

- `postgres/PG_VERSION`
- `postgres/global/pg_control`
- `postgres-wal/`

BusyBox tar 不支持本次期望的 ACL/xattr 参数，因此物理 tar 只作为辅助证据；字节一致且只读复验的 VHD 是保留元数据的主恢复点。

## 独立逻辑恢复

`postgres.dump` 被恢复到全新、隔离的 PostgreSQL 17 实例。第一次执行
`pg_restore --no-owner --no-acl` 时，因 RLS policy 引用的数据库角色不存在而失败。

这是正确的失败关闭：`--no-acl` 不会消除 RLS policy 对角色的依赖。没有在半恢复数据库上继续；该数据库被删除并重新创建，先创建 9 个 `NOLOGIN` policy 角色，再完整恢复。第二次恢复成功，revision 为 `0047_owner_gold_override_go`，关键计数与正式源一致：

| 表 | 行数 |
|---|---:|
| `source` | 178 |
| `document` | 1544 |
| `document_version` | 1595 |
| `event` | 72 |
| `intelligence_item` | 54 |

隔离恢复没有连接或修改正式 PGDATA。验证完成后，临时容器和精确临时卷被删除，Docker 卷总数回到基线。

## 正式迁移执行

迁移阶段只启动正式 PostgreSQL，确认 revision、健康状态和零额外会话后：

1. 以固定提交构建迁移镜像；
2. 幂等运行 `role-bootstrap`；
3. 以 `--rm --no-deps` 运行 Alembic migration；
4. 七个 upgrade 步骤全部退出码 0；
5. 在启动任何 API、Worker、Scheduler、Publisher 前完成结构、ACL、计数和健康验证。

执行结果：

| 项目 | 结果 |
|---|---|
| `role-bootstrap` | `PASS` |
| Alembic 退出码 | `0` |
| revision | `0054_policy_optimization` |
| 正式迁移时运行的持久服务 | `postgres` |
| Docker 卷数 | `188 → 188` |

## 迁移后验证

| 检查 | 结果 |
|---|---:|
| PostgreSQL 健康 | `healthy` |
| 新表 | 12 |
| 安全视图 | 3 |
| 缺失预期 ACL | 0 |
| Prompt registry 行 | 1 |
| Schema registry 行 | 1 |
| 历史 `policy_bundle_id` 非空行 | 0 |
| 缺失既有表 | 0 |
| 既有表非预期计数变化 | 0 |

关键业务计数迁移前后保持不变：

| 表 | 迁移前 | 迁移后 |
|---|---:|---:|
| `source` | 178 | 178 |
| `document` | 1544 | 1544 |
| `document_version` | 1595 | 1595 |
| `event` | 72 | 72 |
| `intelligence_item` | 54 | 54 |

完整计数文件由 258 张表增加到 270 张表。仅有 14 项解释内变化：

- 12 张预期新表，均没有持久业务行；
- `ai_prompt_version` 从 3 增加到 4；
- `ai_schema_version` 从 3 增加到 4。

## 运行恢复中的失败关闭

正式迁移通过后，首次 `dev-lite` 验证因隔离工作树缺少本地忽略 `.env` 而失败。临时 Compose 命令虽带主工作树 `--env-file`，Make 导出的默认
`POSTGRES_PORT=5432` 仍优先，与未触碰的 `quant_stock_postgres` 冲突。

影响被限制在运行入口：

- API、Worker 等保持 Created，未进入业务运行；
- MinIO、Redis、ClamAV 和 Anchor MinIO 只短暂启动；
- 两项对象存储初始化任务退出码为 0；
- 精确项目随后执行全 profile `down --remove-orphans`；
- 正式项目容器和网络归零；
- 其他 41 个运行容器未停止；
- PostgreSQL 返回 `shut down`，revision 仍为 `0054`。

这不是迁移失败。复制同一份被 Git 忽略的本地 `.env` 到最终工作树后，标准入口解析到正式端口 `15432`，轻量和完整模式均通过。最终运行证据见
[docker-desktop-dev-lite-2026-07-29.md](docker-desktop-dev-lite-2026-07-29.md)。

## 主回滚步骤

正式主回滚必须恢复 VHD，不能把 Alembic downgrade 当作主回滚：

1. 停止正式全栈，确认 `srbg-intelligence` 项目容器为 0、没有容器引用正式 PGDATA，且 PostgreSQL clean shutdown。
2. 不覆盖故障现场；先保留当前迁移后 VHD 的带时间戳取证副本。
3. 卸载 `D:\SRBGData\srbg-data.vhdx`，确认不再挂载后才能切换。
4. 重新计算备份 VHD 和 `backup-manifest.json` SHA-256，必须分别等于
   `8dc37373d07fd5702a1091e917809324b088c100888c14af06b846e7dea4b842`
   与
   `c65dd7216008159668ba8348468a19d4dfaa58b2a586f6a9dc598455ee68ae69`。
5. 将备份 VHD 复制到临时恢复文件，完整校验 SHA-256；再把当前 VHD 移到故障现场路径，并把已校验恢复文件切换到正式路径。
6. 启动 PostgreSQL 前核对七个服务目录、`PG_VERSION` 和 `global/pg_control`。
7. 只启动 PostgreSQL，验证 revision 恢复为 `0047_owner_gold_override_go`，五项关键计数为 `178/1544/1595/72/54`，数据库健康且没有非预期会话。
8. 保持所有 Writer 停止并记录恢复结果。不能直接运行当前 `make dev-lite`，因为其 `migrate` 一次性任务会再次升级到 `0054`。
9. 后续只能使用已修复并重新验证的 `0047 → 0054` 受控迁移，或使用另行验证且确实兼容 `0047` 的应用版本恢复服务。

VHD 覆盖 PostgreSQL、WAL、Redis、两套 MinIO、Prometheus 和 Grafana，恢复会让七类服务数据共同回退到该恢复点。不得把部分迁移后数据直接拼回旧 VHD。

`postgres.dump` 是独立灾难恢复辅助手段，但恢复前必须在隔离数据库准备九个 RLS policy 角色并重新验证；它不能替代已验证 VHD 的主回滚路径。

## 最终边界

- 正式数据库已迁移并在轻量、完整、再轻量切换中保持 `0054_policy_optimization`。
- 正式恢复点未删除，哈希和恢复步骤已记录。
- 未执行 Alembic downgrade、手改 `alembic_version`、跳过断言、降低阈值或吞掉异常。
- 未启动真实公网采集、未授予来源准入、未调用真实 AI、未改变发布授权。
- 未推送 main、未创建或合并 PR；远端候选分支发布属于后续独立门禁步骤。
