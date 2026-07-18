# 个人研究平台最终验收

## 产品边界

交互身份只保留绑定回环地址的固定 `owner`；请求头、Bearer Token 和旧角色名不能改变身份。旧 `/api/v1/admin/**` 不再挂载，来源、Feed、搜索、日报、关系和 AI 设置均使用个人链路。自动内容投影只能经过 `PublicationService`。

## 2026-07-18 真实联网验收

以下 ID、HTTP 结果和状态来自本轮 Compose 环境，不引用 Fixture、Mock 或旧日志。

- 手工添加交通运输部政府信息公开来源，来源 ID `019b0000-0000-7000-8000-000000000004`；系统自动识别公开 PDF 流 `019f7448-bd0b-718a-bba3-67fce7426de2`：`https://xxgk.mot.gov.cn/jigou/glj/202602/P020260212527499751863.pdf`。
- 真实抓取运行 `019f7448-e681-7556-9779-26dd5c974b46` 成功，HTTP 200，发现并抓取 1 个对象；来源健康为 `HEALTHY` 且原因可见。系统自动生成 `PARTIAL` 来源画像，并在无企业审批的情况下进入 `PERSONAL_STREAM` 受控调度。
- 原始 PDF 为 2,161,641 字节，SHA-256 `9e960b99d05efc8265bfa343e29998710cf3555bd4a08bdcaebab2e28fc8fd6b`；再次从官方 URL 获取的字节哈希一致。对象存储版本 ID 为 `1105c730-aceb-4dfb-8b4e-42fcf6739d1b`。
- 文档 `019f7449-620a-736e-890d-fe176e9f7207`、版本 `019f7449-620a-7b24-ad81-36e91276ba0b` 被解析为 57 页、20,308 个块。真实内容形成题录 `019f7458-6e25-7571-823e-dac0af34ce67`、accepted claim `019f7458-6e2b-7043-ba49-53e5406d228f` 和证据 `019f7458-6e2b-7dcf-8432-8ec77ffe55db`；证据事实为 `published_at=2026-01-26`，定位类型 `PDF_TEXT`，excerpt SHA-256 以数据库记录为权威。
- personal content outbox `019f7458-6e34-7fca-9163-b9c92bf66d5d` 于 `2026-07-18T08:41:35.669743Z` 成功，由 `PublicationService` 形成 generation 1 的 Feed、搜索和证据事实投影。没有其他直接投影写入路径。
- AI pipeline `019f7449-6f49-796d-8868-f8b7a5f9e719` 因证据定位不匹配明确标记为 `DEGRADED`；基础题录、accepted fact、证据和原文链接仍可用。`unverified_ai_search_projection` 写入数为 0，没有伪摘要。
- 第一次手工停用后全部调度暂停；35 秒观察窗内没有新增联网运行。

## 受控原文变化验收

远端官网不会为验收按需改变原文。为验证生产链路而不伪称远端事件，本轮停止 scheduler，在真实官方 PDF 字节末尾追加明确的验收标记，并通过生产 `PostgresSchedulingService` 与 runtime gateway 写入一个“受控原文变化”版本；未调用 Fixture、Mock 或直接修改投影。

- 变化运行 `019f7467-d8ed-743e-97de-9af54b4944cb` 成功，新版本 `019f7467-dc76-7811-9ef3-f0c2f3056d55`，2,161,689 字节，SHA-256 `29a597b66245f8ce53a6571ade200475a0f7af7f6e1ceeb466023835fd5f1195`。
- 数据库在同一链路立即把旧 accepted claim 标记为 `INVALIDATED`，原因 `DOCUMENT_VERSION_CHANGED`，并产生失效 outbox `ce67430d-51a9-767b-8f47-31a6094dc626`。
- `PublicationService` 于 `2026-07-18T08:51:24.997057Z` 成功消费该事件：内容投影变为 `visible=false`、generation 2，visible signal 数为 0，Feed 与搜索均不再返回旧 item。
- 最终再次手工停用后，来源为 `STOPPED`，活动调度数为 0；调度器正常运行的 36 秒观察窗内抓取运行数保持 `5 → 5`，证明停用后不再联网。

## 固定评估

`scripts/evaluate_pers10.py` 使用 30 个来源和 30 个内容固定样本。主题相关准确率 83.33%，健康原因命中率 100%，Evidence ID 有效率 100%，关键数字/日期无证据数 0，未验证 AI 写入事实索引数 0，人工审核任务新增数 0。固定样本仅用于确定性评估，不冒充真实联网证据。

## 归档与角色

开发库迁移头为 `0030_pers10_role_archive_repair`，归档 53 类、原始 69 行、归档 69 行，manifest 清单汇总 SHA-256 `780f6fd212970588e84d29f9fba169dc5ee5ef4903264cb46f9c831cbb75825c`；其中三个数据库角色的分类哈希为 `a1e0a36ca4bdd7a0cacebb997bd26a19110d4672b6695cad7a0e4f12f9def1d4`。正常业务角色无归档 Schema 使用权。降级会先验证逐行及逐类计数和哈希，损坏即拒绝；验证通过才按 `0030 → 0029 → 0028` 恢复角色、表、数据、约束、触发器、授权和旧函数。

旧产品角色与旧 NOLOGIN 企业角色 `srbg_admin_role`、`srbg_model_role`、`srbg_source_governance_writer` 已删除；只保留 owner 语义及 API、Worker、Publisher、投影读取等必要内部服务主体。

## 遗留风险

- AI 专项本次为明确降级而非完整成功；这不影响基础采集、证据事实和 PublicationService 链路验收。
- 原文变化证据是使用真实官方字节走生产服务的受控变化，不是交通运输部远端内容自然变化；报告明确区分二者。
- 归档回滚会短暂恢复企业结构，只能在完整备份、停机窗口和 Runbook 校验下执行。
- 用户可见界面没有在无人值守阶段修改；任何后续可见改版仍须先提供候选截图并取得确认。
