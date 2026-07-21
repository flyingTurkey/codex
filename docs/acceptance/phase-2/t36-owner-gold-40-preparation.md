# Issue #36：Owner Gold NO_GO 收口与当前盲标准备验收记录

日期：2026-07-20  
状态：`NO_GO_OVERRIDE_CONFLICT`

> 当前状态增量（2026-07-20）：本文其余章节保留 0046 盲标准备完成时的点时证据，其中“尚无 Owner 标注、自动授权事实为 0、数据库头为 0046”等陈述已不再代表当前本地环境。

`.4` 现已形成 40 条 `HUMAN_OWNER` 标注，且 40 条独立预测仍保持先于 Owner 标注封存。只读聚合复核显示，Owner 实际分布为正例 20、边界例 0、负例 20，领域对象覆盖也未达到冻结协议；标准校准为确定性 `NO_GO`，precision 为 55.55%、recall 为 75%，锁定负例泄漏为 9。它不满足 Issue #36 的 20/10/10、正例 7/7/6、十一对象、P/R 均至少 90% 和锁定负例零泄漏要求。

随后出现未提交的 0047 migration、override CLI/测试和仓库外授权文件；当前本地 PostgreSQL 已应用 `0047_owner_gold_override_go`，并持久化一条 `authorizes_auto_pass=true` 的 override `GO`，但同一事实仍记录 `OWNER_GOLD_QUALITY_THRESHOLD_NOT_MET` 及上述低质量指标。可见对话中没有改变 #36 门槛或允许低质量自动通过的 Owner 决策，因此该事实属于未批准冲突，不构成生产授予、#36 完成或 #14 解锁证据。

在 Owner 作出新的明确决定前，禁止将 override 合入基线或用于 Worker、SourceAdmission、PublicationService 和 production closeout；也不得删除或改写追加式事实掩盖冲突。推荐保留标准 `NO_GO`，隔离当前本地数据库，并以新冻结版本改进语料/分类器后重新校准。

## `.1` Owner 尝试 NO_GO

- `owner-gold-2026-07-20.1` 的 40 条 Owner 尝试分布为 `15/3/22`，正例主类型为 `7/8/0`，仅覆盖 9/11 个工程对象，且缺少交通隧道瓦斯与施工机械覆盖，因此确定性 `NO_GO`。
- 私有目录保留 40 条尝试标签、corpus/prediction seal、失败原因和 append-only manifest；没有创建可供校准器读取的 `annotations/owner-gold.jsonl`，也没有写入校准事实。
- 15 条已知正例派生为 Owner 培训回放，明确记录 `selection_basis=KNOWN_OWNER_LABEL` 和 `production_calibration_eligible=false`；任何生产消费者都不能将其当作 Gold。

## `.2` 标注前设计校验 NO_GO

- `.2` 从 80 条全新公开候选按 40 个预注册槽位和 canonical URL SHA-256 顺序冻结，完成 40 次独立预测并生成 seal 后，在 Owner 标注前的内容/槽位复核中发现 `P-DIGITAL-02` 实际是铁路建设安全重大隐患标准解读，而不是数字化应用中心事实。
- 该发现没有读取 Owner 标签或预测输出。由于版本已经封存，禁止原地替换；`.2` 以 `PREREGISTERED_POSITIVE_CENTRAL_FACT_MISMATCH` 确定性 `NO_GO` 保留，Owner 标注数为 0，`production_calibration_eligible=false`。
- `.2` 的 corpus、预测、seal、blind pack 和失败 manifest 均保留为私有审计证据；CLI 拒绝将该退役 blind pack 作为正式标注入口。

## `.3` 标注前对象证据校验 NO_GO

- `.3` 重新生成 40 个 UUIDv7 case ID，完成 40/40 冻结、独立预测与 seal 后，在 Owner 标注前的完整正文复核中发现 3 个预注册工程对象没有正文证据：铁路站房材料误带 `BRIDGE`，城市燃气/管线安全材料误带 `BUILDING`，抽水蓄能电站材料误带 `MUNICIPAL`。
- 该发现没有读取 Owner 标签或预测输出。由于 `.3` 已封存，禁止原地修补；`.3` 以 `PREREGISTERED_ENGINEERING_OBJECT_NOT_EVIDENCED` 确定性 `NO_GO` 保留，Owner 标注数为 0，`production_calibration_eligible=false`。
- `.3` 的 corpus、预测、seal、blind pack 和失败 manifest 均保留为私有审计证据；CLI 拒绝将该退役 blind pack 作为正式标注入口。

## `.4` 当前冻结语料

- 使用带 base hash 的显式 source-pool amendment 将版本递增为 `owner-gold-2026-07-20.4`；重新生成全部 40 个 UUIDv7 case ID，不复用 `.3` 预测。
- 冻结器新增正例正文的 `EngineeringObject`、`PrimaryType`、`TUNNEL_GAS_MONITORING` 和 `CONSTRUCTION_MACHINERY` 硬门禁。首次 freeze 因两个对象元数据门禁失败而在 38 个原始对象处停止；该尝试及输入哈希以私有 NO_GO manifest 保留。由于当时尚未形成 corpus 或 prediction seal，修正预注册对象元数据后重新生成 case ID 并完成冻结，没有修改任何已封存案例。
- 最终冻结 40 个 case：20 正例、10 边界例、10 锁定负例；正例主类型 `7/7/6`，共同覆盖十一类 `EngineeringObject`、2 条 `CONSTRUCTION_MACHINERY` 和 1 条 `TUNNEL + HIGHWAY/RAILWAY + TUNNEL_GAS_MONITORING`。
- `.4` 的 case ID、canonical URL 与规范化内容 SHA-256 和 `.1` 的交集均为 0。每案保存原始响应、最终 URL、UTC 获取时间、原始对象 SHA-256、规范化内容 SHA-256、正文证据定位，以及 corpus/rule/model/prompt/schema 版本。
- 冻结器排除导航、页眉页脚、推荐阅读、版权和链接密集块；每个 locator 对应一个可见正文片段。标题中的“通知”不自动判负，纯医药与工程医疗设施按中心事实区分。

## `.4` 独立预测与盲包

- 在 `.4` Owner 草稿与正式标注均不存在时，通过当前生产 `deepseek-v4-flash`、`ai01-classify-v1`、`classify-output-v1` 完成 40/40 次独立预测。
- 当前 prediction seal 为 `038145f4f1cd841a41dc4c5e8827c62b3a995bac68b785805f9bf7776f702da7`，已通过服务层幂等写入 PostgreSQL；对应自动授权事实数仍为 0。
- blind pack 使用 seal 派生的确定性随机顺序，只投影正文、来源、双哈希和证据定位；不含预注册槽位、采样层、边界/负例家族、预测、置信度、模型输出或推荐标签。
- 当前不存在 `.4` 的 Owner draft 或 `owner-gold.jsonl`。生产自动通过保持禁用，旧 `.1`/`.2`/`.3` 精确版本均失败关闭。

## 私有路径与标注入口

- 根目录：`D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4`
- 盲包：`D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\blind\blind-pack.json`
- 预测封存：`D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\predictions\prediction-seal.json`

```powershell
.\.venv\Scripts\python.exe scripts\annotate_intelligence_v2_owner_gold.py `
  --pack "D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\blind\blind-pack.json" `
  --draft "D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\annotations\owner-gold-draft.json" `
  --output "D:\SRBGData\private-acceptance\owner-gold-40\owner-gold-2026-07-20.4\annotations\owner-gold.jsonl"
```

CLI 先解释 `BOUNDARY` 是案例范围判断难度，`RELEVANT/IRRELEVANT` 是独立最终结论；每案由 Owner 选择 bucket、相关性、唯一主类型、工程对象、专项/设备域和最强正文证据定位，并记录独立 UTC 时间与 rubric 版本。可随时输入 `q`，之后用同一命令续标；非法组合只重试当前案。

完成 40/40 后先运行 `--review all` 复核，再显式追加 `--finalize`。若最终结果不满足 40、20/10/10、7/7/6、十一对象、交通隧道瓦斯和施工机械覆盖，CLI 只生成私有 NO_GO 封存，不生成生产 Gold；禁止修改 Owner 标签或替换个别样本追逐 GO。

## 范围不变

本阶段没有生成最终校准 `GO`，没有关闭 #36，没有启动 #14、SourceStream 或真实来源观察波次。每源 90 分钟、首十 24 小时、DeepSeek 可用性、Feed 抽检、来源波次和其他 production closeout 门槛均保持原值；本次 Owner Gold 预测不计入这些门槛。

## 验证结果

- 定向 TDD 共 `82 passed`，覆盖 `.1` NO_GO/培训隔离、封存后版本递增、候选 amendment 哈希、40 个新身份与配额、正文对象/主类型/专项/设备门禁、预测先封存、盲包零泄漏、非法组合重试、服务端 seal/fact 与 prediction manifest 重算、四消费者精确版本匹配以及旧版本与篡改失败关闭。
- 全量 Python 为 `1380 passed, 27 skipped`，UI 为 `53 passed`，Web 为 `101 passed`；Ruff、mypy strict（151 个源文件）、ESLint、Vue/Nuxt/TypeScript 均通过。
- contract 生成可重复，契约测试 `109 passed`；fixture replay `358 passed`，Round09 报告明确 `provider=mock`、`cost_microusd=0`。
- pip-audit 与 pnpm production audit 均无已知漏洞；Trivy secret/misconfiguration 的 HIGH/CRITICAL 扫描通过。`git diff --check` 通过，index 为空，未发现正文、Owner 标注、预测、seal 或 blind pack 被 Git 跟踪或作为未跟踪私有资产落入仓库。
- PostgreSQL 实测 `.4` seal 幂等、最小角色权限、append-only UPDATE 拒绝及自动授权事实为 0；当前数据库与 Alembic 脚本均为单一 head `0046_owner_gold_prediction_seal`。
- 验证只证明 Owner Gold 盲标准备切片可交付；Issue #36 仍为 OPEN，最终 HUMAN_OWNER 分布与校准结论尚不存在。
