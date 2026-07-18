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

### 2026-07-18 修复后两小时试点与只读复核

修复没有为五个站点硬编码选择器，也没有放宽公网安全、白名单、频率、预算、证据或事实规则。通用探测器从普通列表结构提取有标题的同域 HTTPS 详情链接；隐藏、导航、query/fragment、跨域和来源路径前缀外链接均被排除。严格零延迟 meta refresh、HTTP redirect 和同域 canonical 只在同一边界内跟随；JavaScript 跳转不执行、不推断。

- 运行 ID：`019f75ae-4fba-76d4-bc0f-3fb1744eaa86`；当前迁移头：`0032_controlled_run_worker_read`。运行达到 7200 秒 active limit 后结束，没有启动第二轮。
- 原始报告 `D:\SRBGData\reports\controlled-pilot-20260718T144305Z.json` 保持原样。由于当时三个画像回调已失联且停在 `RUNNING`，该报告按失败关闭；修复后没有重写历史报告。
- 独立只读复核报告：`D:\SRBGData\reports\controlled-pilot-reassessment-019f75ae-4fba-76d4-bc0f-3fb1744eaa86.json`；SHA-256 `B0271D1C92C1C8DEC4F280F530289C7DACBBA8042587A11B89923FCF09B3CB4A`；`reassessment_network_io_performed=false`。
- 结论为 `LIMITED_PASS`：中国政府网政策、交通运输部、四川省交通运输厅 3/5 完成探测、画像、受控计划和至少一个正常采集周期；应急管理部事故调查入口、交通运输部信息公开根入口均以 `UNSUPPORTED_CLIENT_REDIRECT` 失败，未绕过客户端跳转。
- 资源账本：50 次物理 HTTP 全部结算，响应 1,745,429 字节，1 次 `OSERROR` 抓取失败，失败率 2%；没有悬挂预约。AI 为 `DEGRADED_DISABLED`，调用 0、费用 0。
- 真实链路：13 个原始版本均通过对象哈希复核，形成 7 条内容、16 个 accepted claims 和 16 个有效 Evidence IDs；关键数字/日期无证据数 0，未验证 AI 写入事实索引数 0。7 条内容只由 PublicationService 投影，API/Worker 均无直接投影写权限。
- 样例内容 `019f75c0-bddd-743d-ae83-7d1196e0da19`，原文 `https://jtt.sc.gov.cn/jtt/c101585/2026/7/17/40e261598f1648a5924e1fb47e009d1e.shtml`。本轮远端原文没有自然变化，报告为 `NOT_OBSERVED`；不可跳过的哈希变化集成测试证明旧结果立即失效机制，没有伪造现场变化。
- 到期后五个来源全部停用、预约排空；从最早 `manual_disabled_at` 起的停止后联网尝试数为 0。按锁定规则，`LIMITED_PASS` 只完成安全收尾和报告，不进入界面审查或候选图制作。

### 信源替换候选（尚未验收）

若下一轮获准重跑，可优先用静态公开目录替换两个脚本跳转入口：应急管理部 `https://www.mem.gov.cn/gk/index.shtml`，交通运输部政策解读 `https://www.mot.gov.cn/gongkai/zcjd/`。两者只是基于官方网站结构的候选，尚未通过平台新一轮 Probe、路径边界、robots、受控采集和证据门禁，不能计入本轮 3/5，也不能在未经授权时自动启动试点。

### 2026-07-19 固定五源正式重判

- 策略版本：`pers10-fixed-five-3of5-v1`。它只适用于上述五个 URL 精确集合；未来或不同来源集合仍以 4/5 为正式 `PASS` 门槛。
- 对运行 `019f75ae-4fba-76d4-bc0f-3fb1744eaa86` 重新读取数据库事实并生成独立报告，未创建 Probe、Fetch、调度或任何网络请求；`reassessment_network_io_performed=false`。
- 新报告仍位于 `D:\SRBGData\reports\controlled-pilot-reassessment-019f75ae-4fba-76d4-bc0f-3fb1744eaa86.json`，SHA-256 为 `DA15762E9B7A7F32EF1B73DC0352C587A7105CCAD9318F97AA5BC2311A5C0ABD`。旧原始报告及旧复核哈希保持在历史记录中，不被改写或冒充新运行。
- 结论为正式 `PASS`：3/5 来源成功，端到端证据、PublicationService 独占写入、旧结果失效机制、停止后零联网和全部资源上限均通过。
- 两条失败仍保留为可靠性风险。应急管理部候选 `https://www.mem.gov.cn/gk/index.shtml`；交通运输部候选 `https://xxgk.mot.gov.cn/2020/zhengce/qtwjlist_3.html` 与 `https://www.mot.gov.cn/gongkai/zcjd/`。只有新有界 Probe 通过后才允许替换。
- 历史运行的 AI 状态仍真实记录为 `DEGRADED_DISABLED`，没有追写 AI 结果。当前 `0033_controlled_ai_budget_bridge` 已补齐费用权威链，但生产 AI 专项仍须独立真实运行，不能用迁移测试冒充。

### 2026-07-19 界面审查前数据完整性复核

- 审查发现真实个人事件 `019f75c0-e4dd-7c55-882c-86dfbed2d9f4` 已进入 Feed，但详情仍只查旧投影而返回 500。修复后详情 HTTP 200，返回 2 条 claims、2 个 Evidence IDs 和 1 个 `EVIDENCE_FACT` 自动结果；同一事件的旧 metadata 与个人信号在 Feed 合并为 1 条。
- 历史主库中 74 个 `.test` 来源有 72 个未显式标记。修复前保存 `D:\SRBGData\backups\pre-ui-data-isolation-20260718T181239Z\postgres.dump`，4,196,483 字节，SHA-256 `D3AE6EC0567D72ED1DC2D261F8E7E50922FE992EDC3D27F403D1E38A040F2065`；随后把 72 条记录标为 `FIXTURE_TEST` 并停用。业务查询只依据显式状态隔离，不按域名推断。
- PublicationService backfill generation 5 的 build run `019f7670-c487-70a0-8598-e5496e13c648` 投影 8 个真实来源和 8 个事件、失效 40 个旧投影、差异 0；自动发现经 Owner API 关闭。正常来源 API 与 Feed 均不再返回 Fixture/Test-only 内容。
- 只读审查、问题标注和唯一推荐候选图位于 `D:\SRBGData\reports\ui-review\core-pages-20260719T0225Z`。正式界面未修改，审查完成后停止等待 Owner 确认。
