# 住房和城乡建设部有界 SourceStream 发现（Issue #15）

核验时间：2026-07-20T02:30:56Z。本文只记录公开页面的点时研究事实，不构成 `SourceAdmission`、Owner 意图、运行授权或真实采集证据。

## 结论

住房和城乡建设部仍只计一个 Source（`GOV-005`）。官网公开目录提供三个可重复选择的主题集合：建筑市场监管 `F`、工程质量安全监管 `G`、标准定额（标准科技）`K`。三者共用公开目录入口与同一详情/附件边界，分别作为三个 SourceStream，而不是三个机构。

集合边界已达到 `StreamReadiness=BOUNDED`。点时核验确认站方未发布 `robots.txt`，公开目录、网站地图和官方导航未链接独立自动化访问条款，页脚则明确转载须注明来源；公开集合和详情无需登录、验证码、付费墙或访问控制绕过。根据本仓库既有定义，`ADMISSION_READY` 只表示“有界集合已找到、未发现必须绕过的访问控制，可进入后续 SourceAdmission Probe”，不表示 robots、条款、版权、频率或运行门禁已经通过。因此研究处置为 `SourceResearchDisposition=ADMISSION_READY`，Issue #15 满足研究票关闭条件；Source 仍是停用的 `CANDIDATE`。

## 精确边界

- 集合入口：`https://www.mohurd.gov.cn/gongkai/fdzdgknr/gkml/index.html`
- 主题过滤：`F`（建筑市场监管）、`G`（工程质量安全监管）、`K`（标准定额/标准科技）。每次响应必须核对行级分类；无过滤的综合目录和门户首页不能作为 SourceStream。
- 允许主机：仅 `www.mohurd.gov.cn`。
- 路径：列表 `/gongkai/fdzdgknr/gkml/`，详情 `/gongkai/zc/wjk/art/`，附件网关 `/api-gateway/jpaas-web-server/front/document/download`，同主机最终附件 `/cms_files/filemanager/1150240553/attach/`。
- 候选连接器：`LIST_DETAIL`；预期 MIME 为列表/详情 `text/html`、公开目录动态载荷 `application/json`、附件 `application/pdf`。
- 候选频率策略：`t14-mohurd-candidate-frequency-v1`，24 小时一次、请求间隔至少 15 秒、单次最多 3 个列表页。该配置 `authorized=false`，不能启动采集。

## 点时公网与合规证据

- `http://www.mohurd.gov.cn/` 返回 301 到同主机 HTTPS；HTTPS 首页、公开目录和抽样详情返回 200。
- 抽样附件网关返回 302 到同一允许主机的 `/cms_files/.../attach/`，最终返回 200 与 `application/pdf`。运行时仍须逐跳重新解析 DNS、校验公网地址和重定向路径。
- `https://www.mohurd.gov.cn/robots.txt` 返回 404，记为“已核验未发布”，绝不解释为允许；后续 SourceAdmission 必须重新核验并失败关闭。
- 公开目录、网站地图 `https://www.mohurd.gov.cn/wzpz/wzdt/index.html` 和官方导航中未链接独立自动化访问条款，记为 `VERIFIED_NO_SEPARATE_TERMS`；这项观察不授予自动采集许可，后续 SourceAdmission 仍须独立裁决。
- 页脚显示“住房和城乡建设部 版权所有，如需转载，请注明来源”。这只支持保守的题录、accepted claims、必要短摘录和原文链接候选，不授权全文、附件或图片再分发。
- 公开目录无需登录或验证码即可查看；本票未调用未公开 API、未绕过访问控制，也未对人员或证书查询进行枚举。

机器可校验的完整证据、边界和状态位于 `docs/codex-kit/assets/validation/t14_mohurd_source_stream_research.json`。

## 内容边界与 W2

`GOV-005-G` 是后续 W2 的住建部席位：它覆盖房屋市政工程质量安全规定、指南、通报和事故督办，并明确排除泛民生、房地产市场、党建、人事、荣誉评选及无工程新事实的宣传活动。

它将与既有研究中的国家矿山安全监察局“通知公告”流组成 W2：`https://www.chinamine-safety.gov.cn/zfxxgk/fdzdgknr/tzgg/index.shtml`。该矿山流不在本票重复研究或重新准入。矿井瓦斯归 `MINING`；它不给 `TUNNEL_GAS_MONITORING` 提供覆盖信用，后者仍必须与公路或铁路隧道对象组合。

## 关闭边界与后续门禁

本票只完成 SourceStream 研究，不写 `SourceAdmission`，不改变 `desired_enabled` 或运行状态，也不追加 `PAUSE`。`ADMISSION_READY` 不把 404 robots、未链接独立条款或转载声明提升为采集许可；后续准入必须重新核验逐跳公网安全、robots、条款、版权、限速、预算和运行门禁，任何事实不足均保持停用。Issue #15 可以关闭，但不得据此宣称实际准入、运行窗口、覆盖信用或 GO。
