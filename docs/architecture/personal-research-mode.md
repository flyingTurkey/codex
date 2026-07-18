# 个人研究模式架构

- 状态：PERS-10 最终个人形态
- 日期：2026-07-18
- 产品形态：本机单一 Owner，无企业模式开关

## 不可变边界

1. `desired_enabled` 只表达 Owner 意图；公网安全、robots、条款、限速、预算、熔断和运行门禁共同决定实际运行状态。
2. 原始响应先进入私有对象存储，再解析；解析失败不得损坏原始证据。
3. 只有 accepted claims 与有效 Evidence ID 能形成证据事实。AI 判断独立存储，未验证 AI 不进入事实索引。
4. `PublicationService` 是 Feed、搜索、日报和关系投影的唯一写入路径；原文版本变化会事务性失效旧 claim 与投影。
5. 交互身份只有绑定回环地址的 `owner`；内部登录主体按 API、Worker、Publisher 和只读投影职责最小授权。

## 运行图

```text
Loopback Owner → Personal API → Source/Profile/Content services → PostgreSQL
                         │                         │
                         └→ Celery personal tasks └→ private raw object storage
Accepted claims + evidence → PublicationService → Feed/Search/Daily/Relations

legacy_governance_archive (read-only, no business dependency)
```

来源 URL 经公网边界、重定向、robots、条款和预算门禁后生成流。调度器只领取已通过门禁且未被 Owner 停用的流；停用会暂停全部调度并在执行前重新校验绑定。内容版本变化先失效 accepted claims，再由 durable outbox 驱动 PublicationService 撤销旧投影。

## 企业治理退场

迁移 `0029_legacy_governance_retirement` 在一个事务中归档并验证旧治理数据；`0030_pers10_role_archive_repair` 补齐三个企业数据库角色的可回滚快照并删除最后的来源治理角色。旧角色、审批 API、资格/批准 Worker、人工审核页面、生成契约和企业 Operations 已退出源树和执行图。归档 Schema 只供迁移完整性校验与受控降级，业务角色没有 USAGE，业务模块不得查询。

降级前必须停机并完成备份。迁移会重新验证逐行 SHA-256、逐类计数与汇总 SHA-256；损坏时拒绝降级。验证通过后才恢复旧表、约束、授权、触发器和原始数据。详见 [迁移回滚 Runbook](../operations/pers10-migration-rollback-runbook.md)。

## 回滚原则

本地正式数据保存在 `D:\SRBGData\srbg-data.vhdx` 的 ext4 文件系统，Compose 只从 `/mnt/host/wsl/SRBGDataDisk/srv` 挂载七类业务状态目录。启动门禁先验证 VHD 和目录；不允许在挂载失败时隐式创建空 named volume。原 named volumes 作为切换前恢复点保留，未经人工确认不得删除。

- 代码与数据库回滚分开，先备份 PostgreSQL 与对象存储并在隔离环境验证恢复。
- 仅在应用版本已回退且企业代码确有兼容需求时执行 `0030 → 0029 → 0028`。
- 降级不得自动启用来源，也不得降低公网安全、证据或发布边界。
- 归档校验失败时保留当前个人模式，不得手工跳过验证或恢复部分数据。
