# T31 广联达与中国煤炭科工集团 SourceStream 发现验收

> **SUPERSEDED：** Issue #32 因两个原始站点条款与 raw-first 冲突而未通过；替代验收见 T31R。本记录保留失败证据，不代表原票验收成功。

## 范围与前置条件

本记录对应 GitHub Issue #32。已完整读取根 `AGENTS.md`、父 Spec #1、本 Issue、唯一原生 blocker #8、`CONTEXT-MAP.md`、四个相关 CONTEXT 与 ADR-0001/0002/0003；#8 已关闭。工作区存在大量其他票未提交改动，本票只新增独立 T31 Schema、清单、测试和文档，并对 Makefile、README、CHANGELOG 作最小追加。门禁期间共享注册表新增未启用候选 `ENT-010`，因此还将历史迁移测试改为按历史迁移自身的 source IDs 精确核对 42 条不可变种子；完整当前注册表的 `CANDIDATE + disabled` 断言保持不变。

## 纵向行为

- 广联达仍复用既有 `ENT-007`；中国煤炭科工集团仍是第二批 campaign 的单一机构候选，没有伪造已注册的来源代码。每个机构各有一个 SourceStream，子公司和栏目不增加 Source 数。
- 两流保存精确集合、允许主机、路径/查询、详情边界、连接器、MIME、日频、超时、重定向、限速、User-Agent、策略、预过滤、ClaimBasis 和真实合规证据。
- 研究记录固定 `source_status=CANDIDATE`、`desired_enabled=false`、`source_admission=null`、`actual_running=false`、`pause_appended=false`、`coverage_credit_granted=false`。
- 广联达只接受工程对象与生命周期同时成立的数智施工案例；中国煤科只接受矿山工程、安全、监测、装备或数字化事实。矿井瓦斯只归 `MINING`，不授予 `TUNNEL_GAS_MONITORING`。
- 两个官网条款均与 raw-first 自动保存冲突，因此两流是 `BOUNDED + MANUAL_SHADOW`，Schema 拒绝把 disposition 提升为 `ADMISSION_READY`。

## 真实核验

核验时间为 `2026-07-20T03:13:23Z`。仅访问公开页面，不登录、不绕过验证码、WAF、付费墙或访问控制。DNS、公网地址、集合/详情、规范化重定向、robots、条款、版权、响应 MIME 与 SHA-256 均保存在机器记录。公开可达性没有被解释为 SourceAdmission 或运行授权。

广联达 `robots.txt` 为 404；用户协议明确禁止未经书面授权的爬虫、镜像、复制和传播。中国煤科 robots 允许普通路径，但法律声明要求复制网站内容前取得书面许可。robots 与条款冲突时按更严格条款失败关闭。

## TDD 证据

RED：先新增 9 项行为测试并运行，因版本化 Schema 与清单尚不存在得到 9 个预期失败。

GREEN：加入最小 Schema 与机器清单后，定向测试 `9 passed`。测试覆盖研究契约、两个机构计数、精确集合、条款 blocker、正负领域事实、ClaimBasis、矿井瓦斯 facet 以及 Owner 意图/准入/运行升级拒绝。

## 门禁结果

- `make t31-source-discovery-test`：`9 passed`。
- `make fixture-replay`：`357 passed`；评估器明确为 `mock`，成本为 0，不构成 DeepSeek 成功证据。
- `make quality-gate`：最终完整返回 0；其中 Ruff、设计令牌、前后端 lint/typecheck 均通过，Python `1331 passed, 27 skipped`，UI `53 passed`，Web `101 passed`，契约 `109 passed`，pip-audit 与 pnpm audit 无已知漏洞，Trivy 无 HIGH/CRITICAL secret 或 misconfiguration 发现。
- 首次安全串行执行曾因访问 PyPI 出现一次 `SSL: UNEXPECTED_EOF_WHILE_READING`；未吞掉错误，独立重试 `make security-check` 返回 0，随后完整 `make quality-gate` 再次返回 0。
- 本票不涉及正式前端行为，`make web-e2e` 与 `make web-a11y` 不适用。

## 关票判断

Issue #32 的关闭条件要求两个流同时达到 `BOUNDED + ADMISSION_READY`。当前两流均缺少自动访问与 raw-first 私有保存的书面许可，因此 `closure_eligible=false`，Issue 必须保持 OPEN，也不能解除 #33。此阻断直接影响验收语义，不能通过“功能可运行”授权绕过。

本票没有生成或补写 Owner Gold、DeepSeek 成功、SourceAdmission、运行窗口、观察时长、覆盖信用或 closeout GO；没有降低阈值、删除断言、增加 skip，亦未触碰 PublicationService、R3/R4 或削弱 robots、版权和公网安全边界。
