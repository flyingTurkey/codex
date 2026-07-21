# v2 T02：Owner Gold 与自动通过阈值校准验收记录

日期：2026-07-19

对应 GitHub Issue：`flyingTurkey/codex#3`；父 Spec：`#1`；原生 blocker `#2` 已于开工前确认关闭。

## 2026-07-20 范围变更

- `owner-gold-2026-07-20.1` 的 40 条 Owner 尝试已按真实 `15/3/22` 分布确定性 `NO_GO`；15 条已知正例仅作为 `production_calibration_eligible=false` 的培训回放，不能签发生产授予。
- `.2` 在 Owner 标注前发现铁路安全正文与数字化正例槽位不一致，`.3` 在 Owner 标注前发现三个预注册工程对象没有正文证据；两次均未查看预测输出或 Owner 标签即整版确定性 `NO_GO`。带哈希 amendment 递增产生 `.4`，新增正文对象/主类型/专项/设备硬门禁、重新生成 case ID、冻结 40 条并在 Owner 标注前重新执行 40 条独立预测；旧 `.1`/`.2`/`.3` 即使存在版本内自洽的 fixture fact 也必须失败关闭。本记录不把预测运行计入 DeepSeek 可用性、AI 运行窗口或任何来源 closeout 证据。
- Owner 将 #3 正式改为 20 条人工试标流程 pilot，并以 `PILOT / SUPERSEDED` 关闭；关闭不表示 20 条已经标注完成，也不表示自动通过或生产校准 GO。
- Pilot 按 10 条正例、5 条边界例、5 条锁定负例组织，固定 `authorizes_auto_pass=false`，仅验证标注说明、真实哈希、UTC 时间、证据定位和领域判断流程。
- 生产级 Owner Gold、独立预测、阈值校准、服务端安全入库和耐久消费要求完整迁移到 #36；#14 的原生 blocker 同步迁移到 #36。
- #36 已将生产协议限定为 40 条，旧 360 条只保留为 `STRUCTURAL_REPLAY`；数据库失败关闭约束不降低，20 条 pilot 不得通过修改阈值、删除断言或伪造事实取得 GO。
- Owner 后续完成 20 条真实人工判断及私有 reviewed artifacts；交叉校验确认 10/5/5 分布、4/3/3 正例主类型、十一对象、P07 交通隧道瓦斯组合、施工机械覆盖以及 20/20 manifest 哈希和字节数一致。私有报告结论为 `PILOT_PASS`，自动通过真值行数为 0，且 `production_calibration_eligible=false`。

## 本票纵向范围

- 公共 seam 为“私有 Owner 标注 + 独立候选预测 → 版本化校准事实”。入口不生成标注、不调用模型、不启用来源，也不写发布状态。
- 语料必须严格为 20 条正例、10 条边界例和 10 条锁定负例；三个 `PrimaryType` 正例按 7/7/6 分层，并覆盖十一类 `EngineeringObject`、合法交通隧道瓦斯组合和 `CONSTRUCTION_MACHINERY`。
- 每条标注要求 `HUMAN_OWNER`、UTC 标注时间、内容与原始对象 SHA-256、证据定位、规则版本、模型 ID 和 prompt 版本；预测必须按 case ID、内容哈希和模型/prompt 精确对应。
- 阈值从实际置信分布中选择满足 precision/recall 均至少 90% 且锁定负例零泄漏的最低可行值。0.90 没有特殊地位，不能作为缺省批准值。
- 校准事实包含 corpus/rule/model/prompt、分片指标、证据 manifest SHA-256 和事实 SHA-256；字段被修改后不能签发授予。

## 失败关闭与消费者

- 输入 Schema 无效时只输出 `label_authority=UNVERIFIED` 的校准尝试 `NO_GO`，不能装成 Owner Gold 事实。
- 语料不完整、标签语义错误、哈希或版本错配、指标未达标时输出 `NO_GO`、空阈值和稳定原因码。
- qualification 没有精确版本授予时返回 `CALIBRATION_UNAVAILABLE` 并进入既有 `QualificationReviewCase` 路径，不进入抽取或 Event 链路。
- production SourceAdmission 在其他准入指标全过但没有校准授予时仍返回 `PAUSE`；工程 profile 不要求 Owner Gold，继续遵守 ADR-0003。
- `PublicationService` 仅提供精确 rule/model/prompt 的只读授予查询；发布仍只能走既有 PublicationService 门禁。
- production closeout 同时读取人工验收文件与防篡改校准事实，缺失或无效时增加 `OWNER_GOLD_CALIBRATION_*` 的 `NO_GO` 原因。

## 数据库与回滚

- `0038_owner_gold_calibration` 在 0037 后创建 append-only 校准事实表；并行 T04 迁移 0039 以它为直接前序，当前迁移链保持单一 head。
- 迁移不插入任何 `GO` 行，不修改来源、运行或发布状态；API 角色可插入经服务端校准的事实，Worker 与 publication writer 仅可读取。
- 表内已有耐久事实时 downgrade 以 `OWNER_GOLD_CALIBRATION_DOWNGRADE_BLOCKED` 拒绝，生产恢复采用向前修复。

## TDD 证据

- RED 1：公开校准模块不存在；Green 后从 0.93 正例与 0.92 反例分布派生 0.93，而不是 0.90。
- RED 2：CLI 不存在；Green 后分别消费标注/预测并写单一版本化事实。
- RED 3：无校准时 0.99 高置信仍继续；Green 后稳定返回 `CALIBRATION_UNAVAILABLE`。
- RED 4：篡改阈值仍能签发授予；Green 后重新计算事实 SHA-256 并拒绝篡改。
- RED 5：迁移不存在；Green 后追加式事实、最小权限、无种子 GO 与 downgrade 阻断均有回归。
- RED 6：无效字符串布尔值被隐式解释；Green 后 JSON Schema 拒绝并输出不具 Owner 权威的确定性 `NO_GO` 尝试。

## 验证结果

- #3 定向 Ruff、mypy 与纵向测试通过；核心定向集合为 `46 passed`，随后增加严格输入与 production SourceAdmission 回归后相关测试为 `9 passed`，未新增 skip。
- 修复并行 T04 切片的 4 个严格类型错误并重新生成契约后，全量 Python 为 `1133 passed, 27 skipped`，UI 为 `53 passed`，Web 为 `92 passed`；全仓 Ruff、mypy、Vue/Nuxt/TypeScript 检查全部通过，未新增 skip。
- contract assertions 为 `95 passed`，生成一致性检查通过。
- fixture replay 为 `355 passed`；Round09 报告明确 `provider=mock`、`cost_microusd=0`，只证明协议回归。
- security-check 通过：pip-audit、pnpm production audit 无已知漏洞，Trivy 未发现 HIGH/CRITICAL secret 或 misconfiguration。
- Windows 环境无 `make`，按 Makefile 原样执行 lint、typecheck、test、contract-test、security-check、fixture-replay 与 quality-gate 的底层命令；全部通过，未降低规则、阈值或删除断言。

当前结论：#3 已按正式需求拆分以 `PILOT / SUPERSEDED` 关闭，而非按原生产验收通过；20 条 HUMAN_OWNER pilot 已在私有验收目录完成并取得非授权 `PILOT_PASS`。生产校准仍由 #36 承接。自动通过保持禁用，production SourceAdmission 保持 `PAUSE`，现有 engineering/production closeout 真实结论不变。
