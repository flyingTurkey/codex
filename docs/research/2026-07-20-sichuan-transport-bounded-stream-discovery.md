# 四川省交通运输厅有界 SourceStream 发现

- GitHub Issue：#24（v2 T23）
- Parent Spec：#1
- 原生 blocker：#8，核验时已 `CLOSED/completed`
- 规则版本：`t23-sichuan-transport-stream-discovery-v1`
- 点时核验：2026-07-20 11:10:48（Asia/Shanghai）
- 机器记录：`docs/codex-kit/assets/validation/t23_sichuan_transport_source_stream_discovery.json`

## 结论

四川省交通运输厅仍只计一个机构级 Source（`GOV-015`）。本票从候选栏目中锁定四个稳定分页集合，均为 `StreamReadiness=BOUNDED`、`SourceResearchDisposition=ADMISSION_READY`：

| Stream | 精确入口 | 内容边界 |
| --- | --- | --- |
| `SCJTT_TECH_INFORMATION` | `https://jtt.sc.gov.cn/jtt/c101567/zfxxgk_list.shtml` | 科技与信息化；仅保留具有公路、桥梁、隧道、港航工程对象和建设/运营/养护/安全/监测事实的材料 |
| `SCJTT_CONSTRUCTION_UPDATES` | `https://jtt.sc.gov.cn/jtt/c101544/zfxxgk_list.shtml` | 建设动态；直接覆盖交通工程建设节点、验收和运营转换 |
| `SCJTT_QUALITY_SUPERVISION` | `https://jtt.sc.gov.cn/jtt/c102110/zhijian_list.shtml` | 公路、水运、桥隧和地方铁路质量监督、检测与交验 |
| `SCJTT_SAFETY_SUPERVISION` | `https://jtt.sc.gov.cn/jtt/c102111/zhijian_list.shtml` | 公路水运工程施工安全、隧道专项治理、检查与整改 |

建设管理 `c101541` 是含招标、资质和动态的聚合页，不作为 SourceStream；综合门户、站内搜索和任一详情页也不构成持续集合。四条流的分页和详情都必须留在各自栏目路径及 `jtt.sc.gov.cn`，预期 MIME 仅为 `text/html`。研究候选频率统一为每日一次、每分钟最多一次请求、10 秒超时、最多 5 次同边界重定向；这不是运行授权。

## 合规和访问事实

- 当前解析只得到 `28.0.0.69`，未观察到回环、私网、链路本地或云元数据目标；SourceAdmission 仍须在每次 Probe/运行前重新解析并失败关闭。
- 四个 HTTPS 列表与四个样本详情均为零跳 `200 text/html`。对应 HTTP URL 返回内容但不升级 HTTPS，因此清单明确拒绝 HTTP，只保存 HTTPS 入口。
- `https://jtt.sc.gov.cn/robots.txt` 返回 404，响应 SHA-256 为 `55f7d9e99b8e2d4e0e193b2f0275501e6d9c1ebd29cadbea6a0da48a8587e3e0`。404 只表示未发布，不解释为许可。
- 官网公开的《网站声明》要求转载或引用注明来源和网址，且限制商业性原版原式转载；响应 SHA-256 为 `ba2a78656b58ef499d827056c651690e62dc6244c309ef1696cb6acd8ad2dd16`。
- 因此公开投影只允许题录、必要短摘、来源标注和原文链接，`fulltext_redistribution_allowed=false`。列表和样本详情无需登录、验证码、付费墙或访问控制绕过。

精确列表、样本详情、状态、重定向数和响应 SHA-256 全部保存在机器记录中。`ADMISSION_READY` 只表示边界与点时研究证据足以提交后续 SourceAdmission Probe，不表示 robots、条款、版权、限速、预算、质量、熔断或运行门禁已经授予。

## 内容与法域门禁

科技流噪声较高，必须同时出现工程对象和生命周期实质事实；培训、办公 AI、客运票务、物流促销和无工程事实的获奖活动排除。建设动态排除招标采购、资质和经营宣传；质量/安全流排除党建、人事、一般会议、道路运输经营及无工程对象的安全宣传。

第二批 W1 的另一来源沿用既有应急管理部事故调查报告流 `GOV-007`：`https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/index.shtml`。本票不重复研究该机构。四川厅流提供四川地方工程建设、科技与监督事实；应急管理部流提供全国有权机关事故调查事实。两者不得跨法域合并事实，事故原因、责任、处罚和最终整改只能引用相应有权机关原文。

## 控制状态

本票只新增版本化 `SourceResearchDisposition` 研究输入。`desired_enabled` 未改变，未写 SourceAdmission，未改变运行状态，未追加 `PAUSE`，未执行第二批 W1 准入波次，也未授予覆盖信用。Issue #24 满足研究票关闭条件，但 Issue #25 的真实双源准入和 72 小时观察仍保持阻断，直到其自身所有门禁通过。
