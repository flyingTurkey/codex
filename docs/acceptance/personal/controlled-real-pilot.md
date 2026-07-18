# 个人平台受控真实试点记录

## 实现门禁

迁移 `0031_controlled_personal_runs` 提供持久化的全局停止、物理请求、字节、失败和墙钟账本。五个来源以精确 HTTPS 主机和路径前缀绑定；robots 只允许同主机 `/robots.txt`。Probe 与 Fetch 共用账本，重试和重定向均按物理请求计数。停止状态拒绝新预约并等待已预约请求结算。

专项命令 `make personal-pilot-control-test` 使用一次性 PostgreSQL 验证 `0030 → 0031 → 0030 → 0031`、有运行事实时拒绝降级、路径越界拒绝、网络对端异常失败结算以及既有 Probe/HTTP 安全回归。

## 真实试点状态

本文件只记录真实运行产生的新证据，不复用 Fixture 或旧日志。正式启动前必须补写当前提交、数据库迁移头、D 盘备份恢复校验、Compose 健康状态和预检输出。两小时结束后从 `D:\SRBGData\reports` 引用报告的哈希、五来源结果、请求/流量、证据完整性和 P0/P1；在报告产生前不得标记试点通过。

DeepSeek 尚未接入同一耐久请求与费用账本，因此本轮真实试点固定为 `DEGRADED_DISABLED`，费用为 0，不允许 mock 或伪摘要进入真实验收。基础题录、证据事实、原文链接及明确未验证状态继续运行。

### 2026-07-18 失败关闭结果

- 运行 ID：`019f7518-c9ad-7a70-aa08-36c05550112f`；代码提交：`678a619`；迁移头：`0031_controlled_personal_runs`。
- D 盘报告：`D:\SRBGData\reports\controlled-pilot-20260718T115946Z.json`；SHA-256：`3e19cbb31429136af3a9bb1d937e40cce6ce1bb436bda532513a5c608214a612`。
- 运行 385 秒后以 `SOURCE_RELIABILITY_GATE` 失败关闭；12 个物理 HTTP 全部结算，0 个悬挂预约，173,268 字节，传输失败 0，AI 调用/费用 0。
- 四个来源取得真实正文后均为 `UNRECOGNIZED_PUBLIC_ENTRY`：中国政府网 39,843 字节、应急管理部 34,895 字节、交通运输部 92,327 字节、交通运输部信息公开 3,390 字节。四川省交通运输厅只完成 robots 146 字节，因成功上限已不可能达到 4 而由全局门禁停止。
- 四个正文对象已写入私有 MinIO；逐对象重新读取并计算 SHA-256，4/4 与 capture manifest 一致。没有内容进入 PublicationService、事实索引或页面，因此不得宣称“采集→证据→事实→展示”通过。
- 五个来源最终 `desired_enabled=false`、`enabled=false`、`runtime_state=STOPPED`；AI Worker 保持停止；没有第二轮、没有界面实施。
- P0：0。P1：1（个人流识别器无法识别四个目标政府公开入口，试点成功来源 0/5，低于 4/5 门槛）。后续应以这四份真实原文重放定位列表/直接内容识别缺口；修复不得放宽白名单、频率、预算、事实规则或数据库设计。
