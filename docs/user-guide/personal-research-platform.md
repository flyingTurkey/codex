# 个人研究平台使用指南

平台只供本机回环地址上的单一 Owner 使用。日常优先使用 `make dev-lite`；只有确实需要来源发现、AI Worker 和完整观测能力时才使用 `make dev`。

## 添加和管理来源

打开“我的来源”或直接访问 `/sources`。在“添加 URL”中粘贴无需登录的公开 HTTPS 地址并选择“保存并探测”。页面可显示：

- Source 是否已经登记；
- RSS、Sitemap、公开 API、PDF 或列表页探测结果；
- 流级健康、异常原因、最近成功抓取和最近发现内容时间；
- Owner 的启停意图；
- 服务端投影的“实际运行”状态；
- 自动画像、个人覆盖、评分依据和活动记录。

这些状态不能互相替代。来源已登记不表示通过合规研究；`ADMISSION_READY` 不表示 SourceAdmission 已批准；“用户已启用”也不表示 Worker 正在采集。只有服务端的公网安全、robots、条款、版权、限速、预算、熔断和运行门禁全部通过后，流才可能显示“实际运行中”。

系统不会绕过登录、验证码、付费墙、IP 限制或访问控制。探测失败时可使用“重新探测”；失败不得覆盖此前保存的原始证据或健康记录。

## 阅读 Feed 和详情

首页和 `/all`、`/digital`、`/safety`、`/industry`、`/hot` 使用统一时间线；`/search` 查询 v2 搜索投影。卡片进入 `/events/{event_id}` 的统一 Reader。

阅读时分别判断：

- `SourceExcerpt` 和证据定位是否存在；
- 一句话事实、类型和摘要是否只引用当前 accepted claims；
- 内容是“机器整理/未人工复核”还是已经人工复核；
- 来源是否为官方一手来源。该状态与人工复核相互独立；
- 内容是否处于 R3 待审核投影；R4 只应在 Owner 隔离区出现；
- 热点是否只是派生展示资格。热点不改变三种主类型。

Feed 中可见不等于来源当前仍在运行，也不等于 AI 成功或人工复核已经完成。原文版本变更、撤回或更正后，相关 claims、摘要和投影应进入失效与重处理路径。

## 收藏、日报、版本和关系

- `/saved` 管理收藏。
- `/daily` 查看固定快照日报。
- Reader 中可查看引用、来源比较、版本时间线和版本差异。
- “自动关系与个人纠正”可撤销关系、保持材料独立、修正型号关系或拆分混合事件。纠正追加新事实，不删除原始记录。

## 技术异常、安全隔离和 Feed 偏好

`/technical-exceptions` 在同一 Owner 控制面显示技术异常和安全风险：

- 技术异常可以提交幂等的“立即重试”，也可以记录停用来源的个人意图；
- 可决定的安全项允许 Owner 提交允许或拒绝，但允许后仍必须重新通过服务端发布门禁；
- 私网、回环、云元数据、恶意载荷、访问控制绕过和强制扫描失败等硬阻断不能由 Owner 放行。

`/feed-suppressions` 管理展示隐藏规则。隐藏不会删除原文、证据、claims、decision 或历史投影；撤销后，只有当前仍满足 `PublicationService` 门禁的内容才会恢复。

## AI 设置

`/settings/ai` 用于查看受控 provider、激活固定目录中的模型并写入 Secret。Secret 只写不回显。以下状态必须分开：

1. provider 已配置；
2. AI Worker 已启动；
3. 当前预算与授权门禁通过；
4. 某个 DocumentVersion 的 LIVE AI 运行已耐久成功；
5. accepted claims/evidence 已形成；
6. `PublicationService` 已发布。

任何一个较早状态都不能证明后续状态。AI 不可用时，平台应保留已有题录、原文链接和有效证据，不得用伪摘要填补缺口。

## 运行模式

```powershell
make dev-lite
```

保留核心服务和 automation 执行平面，默认不启动来源发现、AI Worker 和完整观测栈。

```powershell
make dev
```

启动来源发现、AI 和观测 profile。启动完整服务仍不自动授予来源运行、真实 AI 调用或发布权限。

仓库当前没有 `make dev-content` 入口。

## 诊断基线

当前已验收 Git 基线为 `a83dda41fd00175a93a864901a898d411bf53b83`，单一 Alembic head 和本地正式数据库 revision 均为 `0054_policy_optimization`。

若诊断结果不是 `0054_policy_optimization`，请保持业务 Writer 和来源停止，按[个人平台备份恢复](../operations/personal-backup-restore.md)在隔离实例核验，不要手改 `alembic_version`、只读归档或业务事实。旧文档中的 `0033`、`0045` 和 `0047` 只描述历史迁移时点，不是当前运行目标。

本地正式运行验收证明 dev-lite、完整模式和回切可启动，不证明真实来源、真实 AI 或真实 Feed 闭环。当前能力与证据缺口以根 [README](../../README.md) 为准。
