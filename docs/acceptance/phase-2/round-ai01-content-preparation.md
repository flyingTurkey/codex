# R-AI01：单一真实来源的 AI 内容准备闭环验收记录

## 范围

- 规范来源：`GOV-003`（交通运输部）。
- 原冻结 URL：`https://zizhan.mot.gov.cn/sj2019/gongluj/sihaoncl/dianxingal/202311/P020250627753815314372.pdf`（已因运行网络不可达而被 2026-07-17 端点恢复取代）。
- 当前唯一 URL：`https://xxgk.mot.gov.cn/2020/jigou/glj/202311/P020250514396309964949.pdf`。
- `xxgk.mot.gov.cn` 与 `www.mot.gov.cn` 分别审核；无通配域、无自动扩展 URL。
- 目标终态：`WAITING_CLAIM_REVIEW`；排除摘要、自动接受、发布、Feed、检索投影和日报。

## 已实现的权威边界

- Alembic 单一 head：`0020_ai_content_preparation`，`down_revision=0019_source_content_bridge`；没有修改或重做 0018/0019。
- 状态机：`QUEUED → PREPARING → CLASSIFYING → EXTRACTING → WAITING_CLAIM_REVIEW`，分类失败为 `FAILED`，抽取或候选物化失败为 `DEGRADED`。
- 通用 Worker 读取私有 raw object、校验 SHA-256、解析 PDF 页块、去除重复页眉页脚、签发页码/坐标 Evidence Anchor，并执行提示注入扫描。
- 隔离 AI Worker 仅接收最小文本、Anchor 和固定配置，不具备数据库、对象存储、Shell 或工具能力；API key 不进入数据库、日志、消息或快照。
- DeepSeek 固定 `https://api.deepseek.com/chat/completions`、`deepseek-v4-flash`、thinking disabled、`json_object`、温度 0、分类 1200 Token、抽取 4000 Token；拒绝任意 URL、tools、stream 和 strict `json_schema`。
- 每次物理调用前由 PostgreSQL 行锁账本预留 12 分；最多 8 次物理调用，因此单文档保守上界 96 分。月度上限 20,000 分、16,000 分单次告警、汇率 1 USD=800 分；未知账单保守占用，未发出请求释放。
- 模型输出先写不可变 `ai_step_run`，再经 JSON Schema、Pydantic、Anchor、摘录存在性、定位和 Claim/Evidence 双向引用复验。物化结果为 `CANDIDATE`，逐条决定复用 `PublicationService` 的职责分离和审核入口；`CLAIM_REVIEW` 拒绝整单批准/发布。
- `GOV-ROUND05-MOT` 作为历史别名映射到 `GOV-003`，历史外键不删除，新试点只认规范身份。

## 离线验证证据

截至 2026-07-17：

- `0020` 隔离数据库回放通过：`0019 → 0020 → 0019 → 0020`。
- PostgreSQL 并发预算预留验证通过：分类/抽取各四次并发物理请求共预留 96 分；重复投递返回同一预留，不增加账本。
- Python API/Worker/契约全量测试：1215 passed、30 skipped；UI 53 passed；Web 109 passed。
- Web 单元测试：109 passed。
- `make contract-test`：86 passed。
- `make fixture-replay`：363 passed，Round09 mock evaluation 通过。
- `make security-check`：Python 已扫描依赖无已知漏洞；pnpm audit 仅 1 个 low；Trivy 高危/严重漏洞、Secret 和错误配置均为 0。
- `make web-e2e`：48 passed；`make web-a11y`：16 passed。
- `make ai-content-preparation-test`：迁移正反向回放、31 个定向 API/Worker/预算/安全测试、109 个 Web 测试及无发布副作用断言全部通过。
- `make lint`、`make typecheck`、`make test`、`make contract-test`、`make security-check`、`make fixture-replay`、`make quality-gate`、`make web-e2e`、`make web-a11y`、`make ai-content-preparation-test` 均已执行并通过。

## 真实调用资格与结果

状态：`BLOCKED`（2026-07-17）。

离线门禁已全部通过，但真实资格检查未通过：

- PostgreSQL 权威来源事实为：`GOV-003 / CANDIDATE / enabled=false / COMPLIANCE_REVIEW`，不存在当前 `source_policy_version`、`connector_config_version`、`source_trial_run` 或生产治理决定。因此来源准入和生产运行授权均不成立。
- 历史 `GOV-ROUND05-MOT` 同样为 `CANDIDATE / enabled=false`；`source_registry_alias` 已把它唯一映射到规范 `GOV-003`，没有创建重复规范来源。
- `www.mot.gov.cn` 与 `zizhan.mot.gov.cn` 按不同主机处理。交通运输部《政府网站管理办法》说明主站域名是 `www.mot.gov.cn`，子站采用独立二级域名；不能用主站审核替代 `zizhan` 审核：<https://xxgk.mot.gov.cn/jigou/kjs/202006/t20200623_3317283.html>。
- `zizhan.mot.gov.cn/robots.txt` 和该主机根地址均未能通过审查通道成功取得（根地址返回 502）；因此 robots、DNS/SSRF 可达性和目标重定向链不能判定为通过。未为此改用不受控网络请求，也未请求目标 PDF。
- 交通运输部免责声明禁止商业性的原版原式转载，并要求转载其他单位提供的内容时另行取得合法授权：<https://www.mot.gov.cn/wangzhangongneng/202512/t20251216_4181727.html>。本实现虽仅保存私有原始证据并物化事实候选、不公开再分发全文，但在来源管理员完成版权范围审核前不判定通过。
- 因前置资格已失败，按短路门禁未检查 `SRBG_AI_API_KEY` 或本地 Secret 是否存在，未读取、打印或探测任何密钥；也未调用 DeepSeek。
- `SIGNED_LOCAL_PILOT` 和 `runtime_authority=false` 未被视作生产授权。

因此本轮没有采集目标 PDF，没有形成真实当前 `READY` 文档，没有发出 DeepSeek shadow 请求，也没有形成真实 `WAITING_CLAIM_REVIEW`、候选事实或预算结算。上述业务验收保持未完成，不能以 Fixture/Mock 结果代替。

## 最终门禁清单

```text
make lint
make typecheck
make test
make contract-test
make security-check
make fixture-replay
make quality-gate
make web-e2e
make web-a11y
make ai-content-preparation-test
```

## 2026-07-17 端点恢复复核

- 原冻结 `zizhan.mot.gov.cn` 附件在应用运行网络中持续连接失败；交通运输部政府信息公开站的[原始通知](https://xxgk.mot.gov.cn/2020/jigou/glj/202311/t20231102_3938969.html)及其当前“农村公路数字化信息化建设典型案例”附件可达。
- 运行时代码现仅允许 `GOV-003` 与 `https://xxgk.mot.gov.cn/2020/jigou/glj/202311/P020250514396309964949.pdf` 的精确组合，旧地址和其他来源均 fail-closed。此修复没有修改已提交的 `0020` 历史迁移；Worker 通过同一事务内的权威来源、文档、任务和 Outbox 条件执行 SHADOW 提升。
- `xxgk.mot.gov.cn/robots.txt` 返回 404，不能由系统自动解释为允许；版权范围还需来源管理员依据交通运输部免责声明逐项审核。因此 `source_policy_version`、连接器、真实试运行和生产治理决定仍不得由本修复代填。
- DeepSeek provider 的 test 激活事实已存在，但运行 Secret 未配置，管理接口继续返回 `SECRET_NOT_CONFIGURED / MODEL_DISABLED`。密钥必须通过 `/admin/ai` 或 Git 忽略的 Secret 文件安全注入，不得写入仓库、日志或验收记录。
- 端点恢复后的 `make ai-content-preparation-test` 通过：隔离迁移回放 32 项、Web 109 项及无发布副作用检查均通过。真实 `WAITING_CLAIM_REVIEW` 仍以完成人工来源审批、真实采集和安全配置为前提，当前验收结论保持 `BLOCKED`，不得用 Fixture/Mock 替代。

## 无发布副作用

代码路径和定向断言要求 Publication、Feed、检索投影、日报、publication revision 均无新增；候选的 `verification_status` 保持 `CANDIDATE`，直到不同审核人逐条作出决定。
