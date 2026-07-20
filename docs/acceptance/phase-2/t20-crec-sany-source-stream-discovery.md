# T20 中国中铁与三一集团 SourceStream 发现验收

> **SUPERSEDED：** Owner 于 2026-07-20 决定绕过中国中铁与三一集团，改由 Issue #37 的中国建筑与徐工集团替代。本文保留原研究和 blocker 证据，不得把 #21 的关闭解释为两条原流均已 `ADMISSION_READY`。

## 范围与前置结论

本记录对应 GitHub Issue #21，只补齐既有来源研究未锁定的中国中铁与三一集团有界集合。父 Spec #1、根 `AGENTS.md`、`CONTEXT-MAP.md`、Acquisition CONTEXT、ADR-0001/0002/0003 均已读取；Issue #21 唯一原生 blocker #8 为 `CLOSED`。Issue #19/#20 仍开放，但不是本票原生依赖。

发现工作没有执行准入或采集。清单中的两个机构继续分别只计一个 Source；`desired_enabled=false`、`source_admission=null`、`actual_running=false`。研究写入接口只暴露 `record_research_disposition`，不能写 Owner 意图、SourceAdmission、runtime 或发布状态。

## 真实核验记录

核验时间固定为 `2026-07-20T02:31:00Z`。联网仅访问公开官网，使用 10 秒连接/30 秒总超时、最多 5 次重定向和 `SRBG-SourceResearch/1.0 (+personal noncommercial research)`；没有登录、绕过 WAF/验证码或调用未公开接口。确定性测试不依赖公网。

### 中国中铁（ENT-003）

- 精确集合：`https://www.crecg.com/web/xwzx61/zfgsdt39/index.html`
- 边界：仅 `www.crecg.com`；列表 `/web/xwzx61/zfgsdt39/index(?:_[1-9][0-9]*)?.html`；详情 `/web/xwzx61/zfgsdt39/[0-9]{19}/index.html`。
- 连接器与频率：`HTML_LIST_DETAIL`、预期 `text/html`、每 1440 分钟一次、每分钟最多一次。
- 公网与可达：Google DNS-over-HTTPS 返回 `220.194.14.118`；集合 GET 200、0 次重定向，响应 SHA-256 `e2b4f6e93417dcbab0655e5faa2cc447a7444d966207dc0789173184e2d55203`；详情样本 GET 200、0 次重定向，SHA-256 `47197b08cf178cecfe729711d32e3f5d66947075b9f901d45b420283ff56af4f`。站点 HEAD 返回 403，因此不得用 HEAD 失败否认 GET 可达，也不得把 GET 可达冒充运行授权。
- robots：[`robots.txt`](https://www.crecg.com/robots.txt) GET 200，`User-agent: *` 下明示 `Allow: /`，SHA-256 `376be689b7be40e01a5c2b72a160fc11d454669b82ca10f450e9655aeb53363b`。
- 条款/版权：[`版权声明`](https://www.crecg.com/web/fzlm6/bqsm70/index.html) 禁止未经书面许可复制、传播、镜像或存入信息检索系统，响应 SHA-256 `b13b96c1de42710d59da5ae31f8232299e633e06e7ebf9e68d603a2211d1facd`。这与平台“raw-first 保存”不可分割的基本事实冲突。
- 相关性：集合稳定且以子分公司项目动态为主，但仍含经营、党建、救援和品牌内容，只能是 `FILTERED`。正向门禁要求既定工程对象与规划/设计/施工/运营/养护/安全/监测/数字化等生命周期事实同时出现；党建、党委会议、品牌、经营会、人事、招聘、利润分配、股东会和房地产销售明确排除。通过者也只标 `PROJECT_FIRST_PARTY_RECORD`。
- 研究结论：`BOUNDED + MANUAL_SHADOW + DISABLED`，blocker 为 `TERMS_PROHIBIT_AUTOMATED_STORAGE`。未取得书面许可前不标 `ADMISSION_READY`、不追加 `PAUSE`、不授予覆盖信用。

### 三一集团（ENT-009）

- 精确集合：`https://www.sanygroup.com/case/`
- 边界：仅 `www.sanygroup.com`；集合 `/case/`，筛选路径 `/case/dlid-*/gongclx-*/year-*/`，详情 `/case/[0-9]+.html`。
- 连接器与频率：`HTML_LIST_DETAIL`、预期 `text/html`、每 1440 分钟一次、每分钟最多一次。
- 公网与可达：Google DNS-over-HTTPS 返回 CDN 公网地址 `155.102.209.201`–`155.102.209.208`；集合 GET 200、0 次重定向，响应 SHA-256 `046c4949d00f9f750b6f1250704811f854b8dad9567ef981f2dd09635c6fb64b`；详情样本 GET 200、0 次重定向，SHA-256 `3271504fc1271baaa232fe9ffd269bbec87192a6c532472986b4c12398b6f697`。
- robots：[`robots.txt`](https://www.sanygroup.com/robots.txt) GET 200，未禁止 `/case/` 或 `/case/{id}.html`，只列出 `/case/null?imageMogr2/` 等异常资源路径，SHA-256 `d8f0f8a9eb1ee2b789001e716ecb34eb68ac87b1914a31ee5455ea1858dc6afc`。
- 条款/版权：[`法律声明`](https://www.sanygroup.com/law/) 允许个人非商业使用，但禁止公开展示、公布或分发，响应 SHA-256 `54ebe7835455b20d52c057e20fb082148fe27f809ca664d2338ec3bbcbf5fbcc`。研究策略固定为单一 Owner 私有题录、必要短摘和原链，`public_redistribution=false`；运行前仍须由 SourceAdmission 重新核验。
- 相关性：只接受施工机械同时直接服务既定工程对象与规划、施工、运营、养护、安全或监测的案例；制造 ERP、灯塔工厂、产线改造、智能制造、招聘、股价、订单金额和仅签约仪式明确排除。产品参数与应用效果只允许 `MANUFACTURER_CLAIM`，`INDEPENDENT_VERIFICATION` 被流策略拒绝。
- 研究结论：`BOUNDED + ADMISSION_READY + DISABLED`。这只表示可进入后续准入核验，不是 SourceAdmission、运行授权或覆盖信用。

## TDD 证据

RED 1：首次运行因 `srbg_api.source_registry.source_stream_discovery` 不存在，在测试收集阶段失败。

RED 2：补充公网 IP、重定向逃逸与连接器安全参数测试后，因模型尚未验证公网地址且没有超时/限速字段而出现 2 个预期失败。

GREEN：`make t20-source-discovery-test` 覆盖两个既有 Source、精确集合边界、研究/运行隔离、未知合规事实失败关闭、私网与重定向逃逸拒绝、四个正负例、ClaimBasis 和只写 disposition。

## 门禁结果

- T20 定向：11 passed；定向 Ruff 与 `mypy --strict` 通过。
- `make lint`：通过。
- `make typecheck`：通过。
- `make test`：Python 1264 passed、27 skipped（仓库既有条件型跳过）；UI 53 passed；Web 101 passed。
- `make contract-test`：109 passed。
- `make security-check`：通过；pip-audit、pnpm audit 与 Trivy 未发现已知高危问题、秘密或高危配置错误。
- `make fixture-replay`：357 passed；离线 mock 评估通过，未调用或冒充真实模型成功。
- `make quality-gate`：最终重跑通过。首次尝试曾被并发出现且不属于本票的未跟踪 T16 测试文件 import-order 错误阻断；该文件随后由其所属工作流移除，本票没有修改 T16/T18，也没有删除断言、增加 skip 或降低门槛。

本票不涉及正式前端变更，`make web-e2e` 与 `make web-a11y` 不适用。

## Ticket 关闭判断与诚实边界

Issue #21 要求两个流都达到 `BOUNDED + ADMISSION_READY` 才能关闭。三一满足研究态条件；中国中铁因官网条款与 raw-first 存储直接冲突，只能保持 `MANUAL_SHADOW`。因此本轮交付代码、清单、证据与测试，但 **Issue #21 必须保持 OPEN，且不能解除 Issue #22 的中国中铁准入波次**。可解除该阻断的外部事实只有中国中铁对单一 Owner 研究平台自动访问和 raw-first 私有保存的明确书面许可，或同一机构另有经核验且条款允许的官方有界集合。

本票没有生成或补写 Owner Gold、DeepSeek RealSchemaSuccess、SourceAdmission、desired-enabled 意图、真实运行窗口、观察时长、覆盖信用或 closeout GO。未降低阈值、删除断言、增加 skip、绕过 PublicationService/R3/R4，也未弱化 robots、版权、重定向或公网地址安全边界。
