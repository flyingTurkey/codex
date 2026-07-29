# 土木工程情报 v2 维护手册

状态：机制工程已实现；真实外部闭环尚未由当前基线证明。

本文是当前维护入口，不替代历史验收记录。历史文档中的迁移头、运行计数、Txx/PERS 编号和 Owner Gold 结论只描述其验收时点。

## 权威阅读顺序

1. 根目录 `AGENTS.md`：长期产品、架构、证据、发布、安全和风险测试规则。
2. `CONTEXT-MAP.md` 及 Acquisition、Intelligence Qualification、Evidence & AI、Publication & Reader Projection 四个 Context：领域术语和模块边界。
3. 当前 GitHub Spec 与 ticket：本次任务范围和验收。
4. ADR-0002 至 ADR-0006：投影、工程/真实运行隔离、自主策略、生产切换和策略生命周期。
5. 当前精确 Git SHA 的测试、迁移和运行证据。
6. 历史验收与研究记录：只能证明对应时间点，不能自动代表当前运行态。

发生冲突时，停止会扩大正式数据、来源、AI 或发布状态的动作并交给 Owner；不得靠降低阈值、构造 fixture 或追加绕过标记获得 `GO`。

## 当前技术基线

- 已验收 Git 基线：`a83dda41fd00175a93a864901a898d411bf53b83`
- 单一 Alembic head：`0054_policy_optimization`
- 本地正式 PostgreSQL revision：`0054_policy_optimization`
- dev-lite：核心与 automation；来源发现、AI Worker 和完整观测栈默认停止
- 完整 dev：核心、automation、discovery、AI 和 observability

本地正式数据库迁移和两种 Compose 模式已验收，但不等于真实来源、真实 AI、真实 Feed 抽检或 production closeout。详细证据见：

- `docs/acceptance/personal/formal-0054-migration-2026-07-29.md`
- `docs/acceptance/personal/docker-desktop-dev-lite-2026-07-29.md`

## 唯一内容链路

```text
Source / SourceStream
  → SourceAdmission 与运行门禁
  → raw object / DocumentVersion
  → policy-bound LIVE pipeline
  → automatic decision
  → accepted claims / evidence / SourceExcerpt
  → PublicationService
  → v2 Feed / search / hotspot / Event Reader
```

维护时逐段核对权威事实：

- `desired_enabled` 只是 Owner 意图。
- 研究 disposition 只是研究结论。
- SourceAdmission 才表达服务端运行授权。
- Worker 或容器运行不代表某个 SourceStream 实际运行。
- 请求成功不代表 raw 对象与 DocumentVersion 已保存。
- AI 配置或任务入队不代表 AI 已进入合法耐久终态。
- accepted claims/evidence 不代表已经发布。
- 只有 `PublicationService` 可以形成发布 revision 和读取投影。
- Feed 可见性与人工复核状态独立。

当前最重要的证据缺口是：尚未在本次基线上用真实来源和真实外部服务证明上述整条链路。隔离 PostgreSQL/MinIO、协议 stub、fixture、mock、canary、SHADOW、离线 replay 和接口 smoke 都不能代替该证据。

## 自主策略维护

- 新建 LIVE 或 SHADOW pipeline run 时固定不可变 `policy_bundle_id`；回调、技术重试、语义 recheck 和恢复必须沿用该值。
- 离线评估固定 `authorizes_production=false`；SHADOW 固定 `affects_production=false`，并在 Item、claim、Event 与 Feed 物化前终止。
- Challenger 只有在版本化离线门禁和完整 SHADOW 聚合窗口均通过后，才可追加晋级事实。
- 激活和回滚只追加 `qualification_policy_activation_v2`；派生 active pointer 不得修改 bundle、decision、evaluation、shadow 或历史 activation。
- 生产健康监测覆盖 Feed yield、技术异常、安全、suppression、Schema/投影失败、硬负例、预算与类别漂移；达到失败条件时追加幂等回滚。
- Prompt、Schema、模型、SourceStream policy 和代码版本必须精确绑定。聚合 replay 不得保存、提交或输出私有逐案内容。

历史 Owner Gold `.4` 在原协议下为 `NO_GO`，该历史事实不得改写。Issue #40 的自主机制已经取代它作为日常分类运行入口；它既不再是当前机制的全局阻断，也不能被重新包装为生产授权。完整历史见 `docs/acceptance/phase-2` 与 `CHANGELOG.md`。

## PublicationService 与读取面

- `PublicationService` 是发布状态以及 Feed、搜索、日报和相关读取投影的唯一业务写入边界。
- v2 Feed、搜索、热点、Event Reader、ReaderAppendix 与媒体授权必须读取服务端当前投影。
- R3 只投影有限元数据和待审核状态；R4 只进入隔离区。
- suppression 与安全 hold 必须在数据库安全视图、排序、分页和媒体授权之前生效。
- 原文或 accepted claims 变化后，旧 `SourceExcerpt`、AI 摘要和发布投影必须失效。
- 热点只追加派生资格，不修改 `PrimaryType`，普通读取不展示模糊总分。

## 真实运行前置条件

真实来源、真实 AI 或正式数据验收只能由 Owner 明确触发。开始前至少确认：

1. 工作树干净，精确 SHA 已记录；
2. 备份与隔离恢复验证有效；
3. Alembic 单一 head 与正式数据库 revision 均符合当前版本；
4. SourceStream 边界、robots、条款、版权、限速、预算和逐跳 SSRF 门禁已复核；
5. SourceAdmission、Owner 意图和 Worker 执行平面状态分别可观测；
6. Secret 不进入命令输出、日志、报告或 Git；
7. 停止条件、熔断、恢复和回滚路径已准备；
8. 报告逐段记录 raw、DocumentVersion、AI、claims/evidence、PublicationService 和 Feed 证据，不以单一“运行成功”概括。

若任一前置条件缺失，保持失败关闭。不要为形成演示结果启动真实来源或真实 AI。

## 开发验证

按路径风险选择稳定入口：

```powershell
make check-fast
make check-pr
make check-release
make check-live
```

- 文档改动检查 diff、格式、链接与引用。
- Python、契约、迁移、前端、Compose/CI、依赖和隔离集成按根 `AGENTS.md` 的触发矩阵增加门禁。
- 发布候选以精确 SHA 复用可追溯证据，只补缺失门禁。
- `check-live` 才能触发正式数据、真实 Docker 栈、真实来源或外部服务验收。

任何 `GO` 报告都必须说明它属于机制工程、候选晋级还是 production closeout，并列出仍缺失的真实证据。“已配置”、研究完成、fixture、mock、canary、SHADOW 或运行了一段时间都不是 production closeout。

## 历史索引

- v2 工程与阶段验收：`docs/acceptance/phase-2`
- 本地正式运行与迁移验收：`docs/acceptance/personal`
- 来源研究：`docs/research`
- ADR：`docs/adr`
- 已退场企业流程：`docs/ENTERPRISE-PROCESSES-RETIRED.md`
- 迁移级历史变化：`CHANGELOG.md`

历史记录不得因当前文档收口而删除或改写。需要了解某一阶段的数字、命令或裁决时，进入对应验收记录，不把它重新复制为“当前状态”。
