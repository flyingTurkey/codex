# 第 01 轮：来源注册与原始文档库

```text
执行第01轮：完成来源准入、人工导入、不可变原始对象和文档版本的纵向闭环。

读取：docs/codex-kit/docs/04-data-source-compliance.md、docs/codex-kit/docs/08-security-threat-model.md、docs/codex-kit/docs/06-ui-ux-spec.md、docs/codex-kit/docs/ui/全部文件、docs/codex-kit/assets/source_registry.csv、docs/codex-kit/assets/content.schema.json、docs/codex-kit/assets/schemas/source-policy.schema.json、docs/codex-kit/assets/schemas/source-onboarding-record.schema.json、docs/codex-kit/assets/validation/source_onboarding_checklist.json。

目标：来源管理员可以登记候选来源、执行合规门禁、上传一个HTML或PDF固定样本，系统保存不可变原始对象、建立文档和版本，并在管理端预览元数据。

必须交付：
- source、source_policy、source_connector、raw_object、document、document_version、document_attachment、audit_log 的 Alembic 迁移；
- 来源状态机 CANDIDATE→COMPLIANCE_REVIEW→FIXTURE_TEST→APPROVED→ACTIVE；
- 所有种子来源导入为 disabled/CANDIDATE；
- 来源准入策略和准入记录必须分别通过 `source-policy.schema.json` 和 `source-onboarding-record.schema.json`，检查项以 `source_onboarding_checklist.json` 为准；
- 默认拒绝：`CANDIDATE` 与 `enabled=false` 是所有来源的初始值，任一准入证据缺失、过期或不通过时都不得启用、抓取或发布；
- SHA-256内容寻址对象存储，相同字节只存一份；
- 人工上传仅允许HTML/PDF，执行大小、MIME、恶意文件和文件名校验；
- POST/GET /api/v1/admin/sources、POST /sources/{id}/fixture、GET /documents/{id}；
- 来源列表、来源表单、样本上传和文档预览页；
- 来源启停和策略修改审计；
- 固定HTML/PDF样本、单元、集成、权限和端到端测试；
- 指标：上传数、拒绝数、去重数、对象存储错误。

方案1 UI增量：复用第00A轮 AppShell、PageHeader、StatusBadge、ResponsiveDrawer；完成 /admin/sources 来源列表、表单、样本上传、文档元数据预览和真实空态。不得另建管理端主题或导航。开发预览不要求人工预先计算证据摘要哈希，但生产对象仍由服务端计算SHA-256。

测试重点：
- 同一文件上传两次只有一个raw_object；
- 同URL内容变化产生新document_version；
- 未通过合规门禁的来源不能ACTIVE；
- 仅修改数据库状态、CSV 或请求参数，不能绕过准入证据校验将 `CANDIDATE/enabled=false` 激活；
- viewer不能上传或启用来源；
-伪装扩展名、超大文件和恶意PDF被拒绝；
-原始对象不能覆盖更新。

验收命令：make lint typecheck test contract-test security-check web-e2e web-a11y；新增 make source-fixture-test。

不做：定时抓取、OCR、AI、发布、搜索。

完成后提交并提供迁移、回滚、API样例、页面截图、测试结果和提交哈希。
```
