# 第17轮验收：首批20来源真实试运行与第一阶段金标门禁

## 结论

验收日期：2026-07-16（Asia/Shanghai）。进入本轮的代码基线为
`b08513965e931f363283384037fc1c1f068a1b1c`；观察窗口状态为
`NOT_STARTED`，不可变起点和终点均不存在，连续观察天数为 0。

本轮没有激活候选来源，没有用 Fixture、回填、重放、演练或测试环境数据替代真实
观察证据，也没有生成真实来源内容。候选来源、候选指标和候选金标定义均明确保持
`PENDING_LEO_CONFIRMATION`，不构成运行授权或验收事实。

**第17轮未完成/BLOCKED**。

## 已确认人员事实与建议职责

| 人员 | 用户已确认 | 建议职责（尚待身份绑定/职责确认） |
|---|---|---|
| LEO | 唯一批准人 | `SOURCE_APPROVER`、`GOLD_ARBITRATOR`、`WINDOW_STARTER` |
| yinzi | 运营管理员 | `SOURCE_OPERATOR`、安全标注 A、数字化复标 |
| baixuejiao | 业务标准人 B | 安全标注 B、数字化主标 |

显示名不是身份授权。真实启动仍要求三人的受信任非本地 OIDC `issuer/subject` 与
UUIDv7 actor 绑定；LEO 的来源批准和窗口启动还必须满足近期 MFA。仓库没有代填这些
外部身份事实。

## 20来源诚实状态

以下仅是版本 `r17-sources-v0.1` 的覆盖建议，不是 LEO 已批准来源清单。20个候选均为
`PENDING_HUMAN_ADMISSION`，真实链路证据均为 `ABSENT`；因此不存在可声称的“窗口内无
更新”健康证据。

| 候选来源代码 | 当前状态 | 真实链路/无更新证据 |
|---|---|---|
| GOV-002 | 待人工准入 | 无 |
| GOV-003 | 待人工准入 | 无 |
| GOV-004 | 待人工准入 | 无 |
| GOV-005 | 待人工准入 | 无 |
| GOV-006 | 待人工准入 | 无 |
| GOV-007 | 待人工准入 | 无 |
| GOV-014 | 待人工准入 | 无 |
| GOV-015 | 待人工准入 | 无 |
| GOV-016 | 待人工准入 | 无 |
| GOV-017 | 待人工准入 | 无 |
| GOV-020 | 待人工准入 | 无 |
| NRA-001 | 待人工准入；权威注册表中缺失 | 无 |
| GOV-010 | 待人工准入 | 无 |
| RES-004 | 待人工准入 | 无 |
| GOV-008 | 待人工准入 | 无 |
| RES-001 | 待人工准入 | 无 |
| ENT-005 | 待人工准入 | 无 |
| ENT-006 | 待人工准入 | 无 |
| ENT-007 | 待人工准入 | 无 |
| ENT-008 | 待人工准入 | 无 |

机器可读的同一状态见 `round-17-readiness.json`。该文件的记录类型是
`ENGINEERING_READINESS_NOT_PILOT_EVIDENCE`，不能作为 `phase2-round17-eval` 输入。

## 需求—实现—测试—证据矩阵

| 需求 | 工程实现 | 本轮测试 | 真实外部证据/结论 |
|---|---|---|---|
| 仅20个批准且未过期来源可调度 | PostgreSQL 权威来源快照、来源/策略/配置/计划/审批/频率/域名/租约复核；窗口精确绑定20源 | R17 治理、迁移、Worker 与对抗测试 | 缺20源人工准入；BLOCKED |
| 来源级 SLO、频率和允许域 | 来源段固定版本；实际 HTTP 请求前原子预留预算；重试/重定向也计入 | 调度预算、HTTP 安全、运行时测试 | 候选频率/SLO 尚未批准；BLOCKED |
| Event 身份、归并与 R3/R4 边界 | 复用既有 Event、PublicationService、发布投影和 Feed；R3 普通用户仅 metadata，R4 不投影 | 全局发布/权限对抗、Event 与投影回归 | 新来源特定解析/事件化配置未获准；不能开始真实窗口 |
| 变更告警、暂停、分段和重放 | DB 触发器暂停来源段；恢复创建新不可变段；重放只读原始对象并在 Fixture execution domain 离线执行 | 规则/配置/计划变化、重放来源污染和失败测试 | 无经批准真实来源故障演练；BLOCKED |
| raw→Document→Claim/Evidence→Event→Projection→Feed 双向追踪 | raw-first、文档引用、既有 accepted-claim/evidence/event/publication 模型；eval 校验生产引用与当前证据 | 迁移、契约、内容回放、发布路径审计 | 无真实20源链路导出；BLOCKED |
| 管理员任务量与实际耗时 | 受控四类计时、60秒心跳、15分钟上限、异人/LEO修正与审计；不记录正文/URL | 工作会话、越权修正、时间边界测试 | yinzi 未开始真实窗口记录；BLOCKED |
| Fixture/回填/测试不得污染窗口 | `PILOT + SCHEDULED + REAL_RESPONSE` 严格分类；eval 拒绝 replay/backfill/drill/test/fixture；外部 Ed25519 信任锚 | eval 污染、签名、引用哈希和缺件失败测试 | 真实签名 evidence 与公钥指纹缺失；BLOCKED |
| 第一阶段人工金标 | 任务、盲标、关键安全双标、仲裁、冻结版本与证据约束 | gold 领域/服务/API/契约测试 | 无真人标注、仲裁和冻结 manifest；BLOCKED |
| 北极星及分项指标 | 同一金标事件集合直接计数；Wilson 95% CI；分项不相乘；绝对安全门禁 fail-closed | 离线 eval 确定性测试 | 指标定义和样本方案未获 LEO 确认；不可计算 |
| 7天连续窗口与20源诚实状态 | 168小时不可变时间边界、暂停/恢复分段、到期后完成检查 | 窗口状态机、数据库约束与迁移回放 | LEO已确认168小时；窗口未创建/启动，已证明0天；BLOCKED |

## 工程安全边界

- 正式调度只使用服务端计算为 ACTIVE 且满足当前权威治理事实的来源；候选 JSON 永不
  提供运行授权。
- 重放不再把失败的 `SOURCE_FETCH` 转回实时调度；它读取已存在、哈希一致的原始对象，
  在 `FIXTURE/REPLAY` 域内无网络执行，成功后也不能进入真实窗口分子。
- 来源批准、窗口生命周期、金标仲裁/冻结和工时纠正均 fail-closed：必须配置唯一
  LEO 的 UUIDv7 actor，并与受信任 OIDC `issuer/subject`、显示名、近期 MFA 和
  append-only staff binding 精确匹配；第二个同名或同角色主体不能代行批准。
- evidence 不能自签自证；离线评估要求调用方单独提供可信 Ed25519 公钥和预期指纹。
- AI观察、付费模型、语义搜索、邮件和企业微信保持关闭。

## 本次实际命令与退出结果

最终独立复跑完成后在此记录；任何历史缓存日志不计入本表。

| 命令 | 本次退出结果 |
|---|---|
| `make phase2-round17-test` | 退出 0；迁移往返通过，285 passed；Web 93 passed；发布路径审计通过 |
| `make phase2-round17-eval` | 退出 1；批准的真实 evidence/gold manifest 缺失，按设计 BLOCKED |
| `make phase2-round16-test` | 退出 0；迁移往返通过，25 passed；Web 93 passed |
| `make lint` | 退出 0 |
| `make typecheck` | 退出 0；mypy 111 个源文件无问题，Vue/Nuxt/契约类型通过 |
| `make test` | 退出 0；Python 1048 passed/29 skipped，UI 53 passed，Web 93 passed |
| `make contract-test` | 退出 0；81 passed |
| `make security-check` | 退出 0；高危/严重漏洞门禁通过（pnpm 仍报告 1 个 low） |
| `make fixture-replay` | 退出 0 |
| `make quality-gate` | 退出 0 |
| `make web-e2e` | 退出 0 |
| `make web-a11y` | 退出 0；15 passed |
| `make golden-replay` | 退出 2；真实第一阶段金标样本全部缺失，按设计 BLOCKED |
| `python scripts/audit_publication_paths.py` | 退出 0（由专项 target 本次调用） |

## 真实阻断

1. LEO 尚未确认首批20来源及逐源治理责任人；`NRA-001` 甚至尚不在权威来源注册表。
2. 逐源 robots、条款、版权、允许频率、存储和展示策略的人工准入记录不存在。
3. 逐源接入方式、发现 SLO 和来源特定解析/事件化配置未获批准。
4. LEO、yinzi、baixuejiao 的真实 OIDC actor/issuer/subject 与职责绑定缺失。
5. 第一阶段样本量、目标误差、95%置信区间和候选阈值未获 LEO 确认；真人金标、关键
   安全双标和仲裁不存在。`SEARCH_QUESTION` 还缺业务权威事实来源决策。
6. LEO已确认连续观察窗口为168小时（连续7天）；因其他前置门禁仍缺失，不可变观察窗口尚未创建或启动。
7. 真实 evidence 导出、外部签名信任锚、逐源健康时间序列、假成功/恢复、真实故障演练、
   管理员实际耗时和费用证据均不存在。
8. 因无真实窗口和金标，北极星、分项指标、置信区间及绝对安全门禁不能作为真实验收结果。

## 迁移、版本与工作区

- Alembic 目标版本：`0017b_round17_pilot`；要求实测正向升级、带事实降级拒绝和空事实
  回滚/再升级。
- 规则、连接器、策略、计划和 DOM 变化必须产生新版本或新观察段，禁止静默覆盖运行段。
- 本轮开始时工作树 clean；只允许逐路径显式暂存本轮文件，禁止 `git add .`、
  `git add -A`、stash、reset、checkout 或 clean。
- 实现与验收提交哈希、最终显式暂存清单将在全部工程门禁复跑后补录。

不开始第18轮。
