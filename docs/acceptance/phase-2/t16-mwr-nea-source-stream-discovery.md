# T16 水利部与国家能源局 SourceStream 发现验收

## 范围与前置条件

- 父 Spec：GitHub Issue #1；本票：Issue #17。
- GitHub 原生 `Blocked by` 只有 Issue #8，已于 2026-07-19 关闭。
- 本轮只形成两家机构的精确流及研究 disposition，不执行 Owner 启用、SourceAdmission、真实采集、内容发布、PAUSE 或覆盖授予。
- 水利部与国家能源局分别只计一个机构 Source；单篇材料和一次性汇编不计持续流。

## 最终机器清单

清单：`docs/codex-kit/assets/validation/t16_mwr_nea_source_stream_discovery.json`，Schema 版本 `t16-source-stream-discovery-v2`。

| Source | SourceStream | 集合边界 | 研究结论 |
| --- | --- | --- | --- |
| `GOV-MWR` 水利部 | `mwr-engineering-service-notices` | `https://spjc.mwr.gov.cn/spjc/hallg/notices.jsp`，仅列表题录 | `BOUNDED + ADMISSION_READY` |
| `GOV-NEA` 国家能源局 | `nea-coal-department-updates` | `https://www.nea.gov.cn/sjzz/mts/index.htm` 及白名单分页/详情 | `BOUNDED + ADMISSION_READY` |

两流均为 HTTPS、`text/html`、1440 分钟候选频率、10 秒超时、零重定向、每分钟一次请求；固定 `desired_enabled=false`、`source_admission=null`、`actual_running=false`、`public_redistribution=false`。

水利部原 HTTP 建设/运行栏目因 TLS 与 robots 不可验证而被替换。新流是水利部行政审批受理中心主办的官方政务服务平台集合，页面持续发布水利工程监理、质量检测、科技成果推广及相关工程公告。连接器为 `HTML_LIST_METADATA_LINK`：只把列表标题、日期和原链作为候选证据，不跟随页面内指向 HTTP 主站的详情链接，不把未读取正文冒充详情证据。

国家能源局保留煤炭司持续栏目；单篇煤矿智能化试点通知只作为该集合下的详情样本。

## 2026-07-20 点时证据

核验时间 `2026-07-20T03:30:00Z`。机器清单保存所有响应 SHA-256：

- 水利部集合：GET 200、`text/html;charset=UTF-8`、零重定向、公网 `28.0.0.95`。
- 国家能源局集合与煤矿智能化样例详情：均 GET 200、`text/html`、零重定向、公网 `28.0.0.49`。
- 两站 `/robots.txt` 均返回 404。RFC 9309 §2.3.1.3 把 400–499 定义为 unavailable，并规定 crawler MAY access；RFC 同时明确 robots 不是访问授权，因此没有用 robots 结论替代条款、版权或运行门禁：https://www.rfc-editor.org/rfc/rfc9309.html
- 《政府信息公开条例》第一条保障依法获取政府信息，第二十四条要求政府信息公开平台具备检索、查阅和下载功能。本票据此把访问限制在主动公开政府信息、日频与单分钟一次：https://www.audit.gov.cn/n11/n1765/c140380/content.html
- 现行《著作权法》第二十四条允许为个人学习、研究使用已发表作品，但要求署名、不影响正常使用、不不合理损害权利人。本票据此只允许单一 Owner 私有非商业研究、题录/必要短摘与原链，禁止公开再分发：https://www.ncac.gov.cn/xxfb/flfg/flfg_532/202103/t20210309_50530.html

上述法律适用是对本产品“单一 Owner 个人研究”既定范围的保守实现，不扩展到企业、多用户、商业利用、全文公开传播或绕过访问控制；产品范围变化时必须重新评估。

## 领域与失败关闭

- 水利流要求“水利工程对象 + 规划/设计/施工/监理/质量/验收/运行/安全/监测/数字化/科技成果”，排除节水宣传、党建、人事、培训、预算采购、工资、举报和统计督察。
- 能源流要求“能源工程/煤矿/矿山/工程装备 + 规划、建设、运行、安全、监测、智能化等生命周期事实”，排除提案答复、培训、价格产量、会议与机关内容。
- 两流只能形成 `PROJECT_FIRST_PARTY_RECORD` 候选，不提升为独立验证。
- metadata-only 连接器必须没有详情观察；改称 `HTML_LIST_DETAIL` 时必须提供详情 GET。任何 robots、条款或版权状态改回 UNKNOWN/BLOCKED，`ADMISSION_READY` 校验立即失败。

## TDD 与门禁

- 第一轮 RED：旧 HTTP 边界测试首次 `9 failed, 1 passed`；第一轮 GREEN：T16/T20 `21 passed`。
- 替代流 RED：将水利流改成诚实的 metadata-only 清单后首次 `9 failed, 1 passed`，准确暴露模型强制伪造详情观察的问题。
- 替代流 GREEN：最小实现允许 `detail_get=null`，但只对 `HTML_LIST_METADATA_LINK` 生效；T16/T20 `21 passed`，定向 Ruff 与 strict mypy 通过。

最终门禁：

- `lint`：Ruff、design tokens、UI ESLint、Web ESLint 全部通过。
- `typecheck`：全仓 strict mypy、UI/Web TypeScript、生成契约类型检查全部通过。
- `test`：Python `1331 passed, 27 skipped`；UI `53 passed`；Web `101 passed`。27 个 skip 均为仓库既有环境型跳过，本票没有新增 skip。
- `contract-test`：生成结果可复现，`109 passed`。
- `security-check`：pip-audit 与 pnpm production audit 无已知漏洞；冻结 1186 文件的 Trivy 快照完整识别 3 个依赖清单和 3 个 Dockerfile，HIGH/CRITICAL secret/misconfiguration 扫描通过。
- `fixture-replay`：`357 passed`，Round09 mock 离线评估通过，费用为 0，未调用真实模型或公网采集。
- `quality-gate` 的 lint/typecheck/test/contract/security 全部组成项已按 Makefile 等价展开并通过；本机没有全局 `make` 可执行文件。

未删除断言、增加 skip、降低阈值或吞掉异常。

## 关闭条件

水利部与国家能源局现均有 `BOUNDED + ADMISSION_READY` 精确 SourceStream，满足 Issue #17 的研究票关闭条件。`ADMISSION_READY` 只允许进入未来 SourceAdmission Probe，不等于真实准入或运行授权；本票仍未产生 Owner Gold、DeepSeek 成功、SourceAdmission、运行窗口、PAUSE、覆盖信用或 GO，也未触碰 PublicationService、R3/R4、安全扫描或发布路径。

GitHub Issue #17 已于 `2026-07-20T03:38:36Z` 正常关闭：https://github.com/flyingTurkey/codex/issues/17
