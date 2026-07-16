# 第17轮离线评估证据契约

`phase2-round17-test` 只运行确定性契约、Fixture、TEST故障与安全测试，不访问真实来源。
`phase2-round17-eval` 只读取本地、只读导出的真实试运行证据快照和真人金标；脚本没有网络客户端。

默认输入为：

- `docs/acceptance/assets/round17/round17-evidence.json`
- `tests/gold/round17/manifest.json`

这两个文件故意不提供种子或Fixture。缺失任一输入、20源审批不完整、OIDC身份未绑定、窗口不足168小时、运行来源不是 `PILOT + SCHEDULED + REAL_RESPONSE`、金标数量或双标仲裁不完整、哈希不一致、门禁未达标时，eval 必须返回非零并输出 `BLOCKED`。

`round17_metrics_definition.json` 中的20来源组合、样本量和阶段阈值只是待确认候选契约，文件本身不代表 LEO 已批准。真实 evidence 必须额外包含 `preflight_authorization`，由 LEO 的非本地 OIDC UUIDv7 主体在 T0 之前或 T0 当时通过 MFA 明确绑定：

- `roster_version` 及该版本20来源清单的规范化 SHA-256；
- `metrics_definition_version` 及被引用指标定义文件的 SHA-256；
- 精确的 `window_seconds = 604800`；
- UUIDv7 决策号、确认时间、MFA 时间和上述字段的规范化确认哈希；
- 指向不可变审计导出的仓库内相对引用及其 SHA-256。审计导出必须逐字段等于确认记录，不能只是一个无关文件。

确认或 MFA 晚于 T0、MFA 晚于确认、MFA 与确认相差超过5分钟、任一版本/哈希/时长不匹配、审计引用缺失或内容不相符，均必须 `BLOCKED`。测试中构造的合成确认只验证确定性契约，不是第17轮真实审批证据，也不得复制为真实 manifest。

## 来源准入清单与逐源审批

schema `1.3.0` 要求 `source_admission_manifest` 恰好包含20条完整准入身份。规范化清单哈希必须覆盖每个来源的 UUIDv7、来源代码、展示名、规范入口、接入方式、允许域与 URL scope、yinzi 治理责任人、轮询频率、发现 SLO，以及 policy、connector、config 各自的版本和制品 SHA-256。LEO 的 preflight `roster_sha256` 必须等于该完整 manifest 的哈希；只对20个来源代码和频率做哈希不再有效。

每个来源的 `COMPLIANCE`、`LIVE_TRIAL`、`PRODUCTION` 审批均是独立的结构化审计记录。记录必须逐字段重复并精确绑定上述来源身份和版本、完整 admission manifest 哈希、唯一 UUIDv7 决策号、LEO OIDC subject、有效期、决定时间和 MFA 时间。MFA 必须先于或等于决定且相差不超过5分钟，审批在 T0 前完成并覆盖整个窗口。`audit_record_sha256` 由审计字段规范化重算，引用文件必须逐字段等于审计记录；同一来源的无关健康文件、只含来源代码的 JSON 或自报 `approved` 均不能作为审批证据。

## 不可变窗口、运行全集与无更新语义

`window` 必须绑定 `COMPLETED` 的数据库导出、数据库 revision、非未来 server time、完整 admission manifest 哈希，以及全部来源分段和 pause/resume 事件。每个来源分段携带 policy/connector/config 版本和哈希；分段号必须连续，时间不可重叠或留白，暂停和恢复事实必须双向对账。窗口启动 MFA 必须在启动决定之前或同时发生且不超过5分钟。内联窗口事实与 `database_export_ref` 的 JSON 必须完全相同。

每个 included run 必须逐字段绑定 window UUIDv7、source segment UUIDv7、source UUID/代码和该分段冻结的 policy/connector/config 版本与哈希，且 slot、启动、结束时间落在同一分段内。`run_universe` 是一次事务一致的 PostgreSQL 导出：它必须包含窗口、PILOT 环境、yinzi exporter、数据库集群/库/角色身份、数据库 revision、事务 snapshot/txid 水位、固定查询 ID/SQL 哈希、固定污染排除谓词、included/excluded 全量 ID 和计数。eval 会重跑集合对账；Fixture、Replay、Backfill、Drill 或未知 ID 不能混入指标输入。

`NO_UPDATE` 不是“没有报错”或仅有 `{run:id}`。每次运行仍必须保存原始响应引用及哈希，并提供与运行结束时间一致的响应元数据精确导出。无更新只接受两种可复核语义：带条件请求的 HTTP 304；或成功解析公开发现列表且 `new_item_count=0`。后者还必须给出响应字节数、HTTP 状态、解析条目数、探测器版本/哈希及响应头哈希。`SUCCEEDED` 则必须证明解析得到至少一条新条目。

至少一条 `failure_drill` 必须引用 LEO 事先批准的 UUIDv7 决策，并在真实窗口内使用 TEST 环境和测试端点执行，明确证明未联系或破坏真实来源。审批 MFA 同样必须先于决定且不超过5分钟；结果导出必须证明告警、暂停和无网重放均成功。该 drill run 必须出现在 excluded universe 中且不得进入任何真实指标。

## 外部签名信任锚

同一个 evidence 内的 OIDC、MFA、确认和哈希字段不能自行构成信任根。schema `1.3.0` 因此要求顶层 `trust_signature`，其中只保存 `Ed25519`、签名公钥指纹和 detached signature；eval 还必须由调用方独立提供：

- PEM SubjectPublicKeyInfo 格式的可信 Ed25519 公钥文件；
- 该公钥32字节 Raw 编码的 SHA-256 小写十六进制指纹。

CLI 参数为 `--trusted-public-key` 和 `--trusted-public-key-sha256`；等价环境变量为 `ROUND17_TRUSTED_PUBLIC_KEY` 和 `ROUND17_TRUSTED_PUBLIC_KEY_SHA256`。Make target 只透传同名 Make 变量，不包含默认生产公钥或默认指纹。公钥文件、预期指纹、evidence 内指纹三者必须一致；缺少信任锚、错误算法、错误公钥、错误指纹、无效 Base64 或坏签名均返回非零 `BLOCKED`。如果真实 evidence 本身缺失，`REQUIRED_EVIDENCE_MISSING` 仍优先报告。

签名字节按下列唯一方式生成：将 evidence 顶层 `trust_signature` 排除后，使用 UTF-8 JSON、键名排序、无空白分隔符、禁止 NaN 的规范化字节进行 Ed25519 签名。`manifest_sha256` 则排除顶层 `manifest_sha256` 和 `trust_signature` 后计算，以避免循环依赖；签名本身包含并保护最终 `manifest_sha256`。私钥只能存在于获授权的外部签名系统，禁止写入仓库、evidence、环境示例或测试Fixture。测试使用运行时临时生成的密钥且不落盘私钥。

证据引用只允许仓库根目录内的相对文件路径，并逐项校验 SHA-256；不得引用URL、目录、越界路径或缓存日志。实际正文不应进入证据快照，引用文件只保存经人工准入的查询结果、标识符、时间、计数和哈希。

## 金标发布与北极星集合绑定

第一阶段金标不是五组无结构对象。每个样本必须携带稳定 `id`、集合专属 `sample_kind`、来源、内容哈希、授权引用、`gold_release_id` 和结构化 `annotation`：Document 必须有 `document_id`；重复/关系对必须有两个不同且存在于 Document 集合的成员；Event cluster 必须列出存在于 Document 集合的成员并标记为高价值；Claim/Evidence 必须分别绑定 Claim 与 Evidence UUIDv7；检索题必须绑定存在于同一 release 的预期 Event cluster。

金标顶层必须绑定数据库 `round17_gold_release.id`（UUIDv7）、该行的 `db_manifest_sha256`，以及哈希校验后的冻结审计导出。审计导出必须逐字段绑定 release ID、版本、来源 roster、数据库 manifest hash、`FROZEN` 状态、LEO OIDC subject 和冻结时间；仅有同名版本或自报哈希不能作为 release 证据。签名后的 pilot evidence 再通过 `gold_manifest.version + gold_manifest.sha256` 绑定整个金标导出，从而形成“签名 evidence → 金标导出哈希 → DB release/audit export”的可复核链。

`event_evaluations` 的 `gold_event_id` 集合必须精确等于该冻结 release 的 100 个高价值 `event_clusters.id`：不允许遗漏、增加、重复或用窗口内临时枚举 ID 替代。因此北极星分母固定为同一组 100 个应发现高价值事件，不接受任意非空分母或分母为 1 的自选样本。

所有主标、复标和仲裁标签哈希必须是非空小写 64 位 SHA-256。关键安全样本不得少于 20 个，必须由 yinzi 主标、baixuejiao 盲复标，分歧由 LEO 仲裁。数字样本集合不得为零，yinzi 对数字样本的盲复标数必须达到总体 20%（向上取整且至少 1 条）。`raw_agreement` 与所声明的 `COHEN_KAPPA` 或 `GWET_AC1` 均由逐条 annotation 的 `label_code` 重算，并与 manifest 中统计值逐值一致；eval 不信任预先填写的 coefficient。

## 北极星五谓词不得自报

`event_evaluations` 不接受五个裸布尔字段。每个金标事件必须同时提供哈希绑定的 `predicate_facts`、由这些事实推导的 `predicate_results` 和逐字段完全一致的 `predicate_evidence_ref`。eval 独立重算：

- `within_slo`：原文发布时间、首次发现时间与该来源已冻结的发现 SLO；
- `correct_eventization`：权威 Raw→Document→accepted Claim/Evidence→Event→Publication Projection 链、冻结 gold cluster 及两边的 Document ID 集合；
- `nonduplicate`：同一 gold cluster 对应的生产 Event ID 集合必须恰好只有当前 Event；
- `critical_evidence_current`：trace 中 accepted Claim ID、当前 Evidence ID 与逐 Claim/Evidence current 关联必须双向一致且非空；
- `searchable_readable`：已发布 projection revision、Event ID、检索结果 Event ID 和可读回取状态必须一致。

事件的 `source_key`、`high_value` 和 cluster member IDs 必须与冻结金标逐项相同。任一自报结果与重算结果不同、查询导出哈希不匹配，或只提供布尔而没有上述事实时，本轮必须 `BLOCKED`。

## 分项指标与绝对门禁

每个比例指标必须声明固定 `population_kind`，并列出完整、排序且无重复的 `eligible_ids` 和其中的 `passing_ids`。eval 将 eligible 集合精确绑定到同一批100个 event clusters、全部窗口 scheduled runs 或对应的完整金标集合，再由 ID 数量重算 numerator/denominator；不接受任意非空样本、分母1、抽样子集或只填比例。每项还必须绑定窗口结束时的 snapshot、低敏 watermark 和哈希校验后的 ID-only 查询导出。

每个绝对门禁必须是结构化数据库查询结果，包含固定 `query_id`、`query_version`、数据库 revision、window ID、窗口结束 snapshot、watermark、完整 row IDs、count 和哈希引用。count 必须等于 row IDs 数量。R3绕过、R4/未发布泄露、PublicationService旁路、最终超期积压和外部模型/通知费用必须为0。已发布关键 Claim 总集合必须非空，且其 row ID 集合必须与“拥有当前有效 Evidence”的集合完全相等；`0/0` 不构成100%覆盖。

## 运营与来源健康

运营证据只接受 actor 为 yinzi、固定 query ID/version、数据库 revision 和 window ID 的权威数据库导出。导出必须列出四类工作的 task、session、版权/纠错记录、active seconds、最终超期 task IDs 和外部费用账本。task 与 session 双向完备；只有实际存在版权/纠错 task 时才要求对应 correction，诚实的零纠错窗口必须使用空数组，禁止为了过门禁制造纠错。每日四类分钟数和任务数由 session 的 active seconds 与 task IDs 重算。观察窗口按 `[started_at, ended_at)` 处理，并覆盖其实际触及的全部 `Asia/Shanghai` 自然日：168小时窗口会根据 T0 时刻触及7或8天，不能把结束边界午夜所属日期多算一天。至少存在一个真实 task/session 且总 active seconds 大于0；全零记录不能证明1名兼职管理员可运营。最终积压和费用同时与绝对门禁查询重算对账。

Scheduled run 必须在 slot 后15分钟内启动，并逐条引用固定查询版本的权威数据库 run export；该导出至少绑定窗口/segment/版本、slot 与执行时间、outcome、response state、物理 request count、response bytes 或 `null`、失败代码和恢复关系。收到响应的运行使用 `REAL_RESPONSE + RECEIVED`，保留私有 raw hash/ref 和响应元数据。DNS 在网络 I/O 前失败或连接/读取超时时，必须使用 `REAL_ATTEMPT + NO_RESPONSE + FAILED`：DNS 的 request count 为0，timeout 至少为1，final URL、raw response 和 response metadata 均为 `null`，同时保存 ID-only 失败代码、检测器版本、时间和哈希导出；不得伪造一个空响应。

`fake_success_detected=true` 只能对应已转为 `FAILED` 的运行，并绑定检测规则、原因、检测时间和精确导出；假成功和无响应传输失败都必须被同一来源中时间更晚的成功/无更新运行通过 `recovery_of_run_id` 和恢复导出闭环。裸 `recovered=true`、跨来源恢复、先恢复后失败或无证据标志均必须 `BLOCKED`。当前应用数据库若尚未权威持久化 operator task/task_id/correction 或 per-run request_count/response_bytes/no-response failure 字段，则真实 eval 必须保持 `BLOCKED`，外部手工 JSON 不得替代数据库事实。
