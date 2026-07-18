# PERS-07 AI 判断、未验证 AI 与自动发布闭环验收

## 范围

本轮实现 SUMMARIZE、VERIFY、PublicationService 自动投影、Feed、统一搜索和个人日报闭环；不实现自动 Event 归并，不删除旧审核代码，也不增加人工 AI 审核。

## 验收映射

- Alembic `0027_ai_judgment_versions` 保存 Event/文档版本、证据集合哈希、Prompt/Schema/模型版本、状态、Token、耗时、微美元成本、VERIFY、失败/失效原因和投影引用。
- SUMMARIZE Schema 仅含关注原因、行业影响、工程场景、局限、待核实问题和 `used_claim_ids`；输入构造器仅接受当前证据事实及每项最多 500 字符的必要摘录。
- `used_claim_ids` 在本地严格校验为当前事实 ID 子集。VERIFY 覆盖无证据陈述、数字/日期冲突、法律/责任/因果过推、企业声明归因、过期/替代证据和提示注入。
- DeepSeek 请求固定模型、禁用 thinking/stream/tools、使用 `json_object`，SUMMARIZE/VERIFY 均为 1500 tokens，并只允许一次受控 JSON/Schema 修复。
- PublicationService 独占 Feed、主要搜索、未验证搜索和日报写权限；文档失效和重跑在事务内清理所有旧可达性。
- 30 个固定样本的离线评估达到 Evidence ID 100%、关键数字/日期无证据数 0、未验证 AI 写入事实索引 0、越权投影写入 0、一次修复成功率 100%。

## 自动化证据

专项命令：`make personal-content-test`、`make ai-content-preparation-test`。全局门禁及 Web E2E/a11y 的最终结果在本轮提交前记录为全部通过。

## 回滚

迁移支持在无 PERS-07 数据时从 0027 降至 0026，并完成 `0026 -> 0027 -> 0026 -> 0027` 回放。存在判断或投影事实时拒绝破坏性降级；应用回滚通过停止新任务并保留版本化记录完成。
