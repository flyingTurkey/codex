# Issue #32 法律阻断替代信源研究

## 结论

Issue #32 的广联达用户协议禁止未经书面授权的爬虫、复制与镜像，中国煤炭科工集团法律声明要求复制网站内容前取得书面许可；两者均与平台 raw-first 强制保存冲突。原始证据不改写，原票以 `SUPERSEDED` 收口。Issue #38 以四川省住房和城乡建设厅和贵州省能源局补足第二批 W5 两个独立机构席位。

替代选择从目标与约束推导：需要持续公开集合、直接覆盖工程对象与生命周期、无需登录/验证码/付费墙、HTTPS 和公网边界清晰，并且不出现明确禁止自动访问或保存的条款。山东省能源局因证书名称不匹配排除；四川省发改委煤炭管理栏目仅有少量陈旧记录，不构成持续流。

## 精确流边界

- `GOV-017` 四川省住房和城乡建设厅：`https://jst.sc.gov.cn/scjst/c101428/article_list.shtml`，仅允许该科技栏目分页和 `c101428` / `otherDocument` HTML 详情。必须同时命中房屋建筑、市政、城市生命线或基础设施对象与智能建造、BIM/CIM、数字监测等生命周期词；资质、注册、房地产交易、党建、人事、采购等排除。
- `GOV-023` 贵州省能源局：`https://nyj.guizhou.gov.cn/zwgk/xxgkml/zdlyxx/nykjgl/`，仅允许同路径分页和 HTML 详情。只接受智能煤矿、智能采掘、矿山安全监测、矿山装备/机器人或煤矸石工程技术；党务、风光电、电价、油气、节能报告采购等排除。

两个政府来源只可在机关正式发布、评定或资金安排的法定边界内形成 `AUTHORITY_FINDING`；不得据此确认厂商效果或独立验证。贵州矿业内容固定为 `MINING`，没有公路或铁路隧道证据时不得授予 `TUNNEL_GAS_MONITORING`。

## 点时核验与合规边界

核验时间为 `2026-07-20T03:55:15Z`。集合与详情样本均 HTTPS 200、零重定向并解析到公网地址；各自 `robots.txt` 为 404，严格记录为 `VERIFIED_NOT_PUBLISHED`，不解释为许可。公开导航未发现单独自动化条款，严格记录为 `VERIFIED_NO_SEPARATE_TERMS`，同样不构成授权。

清单保存四类请求的 raw SHA-256。只允许单 Owner 私有原始证据保存；普通读者投影限题录、accepted claims、必要短摘与原文链接，图片、附件和全文不得公开再分发。`ADMISSION_READY` 仅表示可提交后续 SourceAdmission Probe；Source 仍 disabled，后续探针必须重新检查公网安全、robots、条款、版权、限速、预算和熔断。

机器证据见 `docs/codex-kit/assets/validation/t31r_sichuan_housing_guizhou_energy_source_stream_discovery.json`。
