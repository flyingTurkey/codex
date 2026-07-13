# 02｜内容模型、证据与发布规则

## 1. 建模原则

平台的基础对象不是网页，而是经过版本化处理的“原始文档”；面向用户的基础对象不是新闻，而是“情报条目”；法规修订、事故续报等跨时间变化通过“事件”关联。

```text
来源 Source
→ 原始对象 RawObject
→ 文档 Document
→ 文档版本 DocumentVersion
→ 事实 Claim + 证据 Evidence
→ 情报条目 IntelligenceItem
→ 事件 Event / 热点 Topic
→ 发布快照 PublicationRevision
```

## 2. 首期固定内容类型

模型不得自由创建类型，首期只允许：

| 代码 | 中文名称 | 典型内容 |
|---|---|---|
| `DIGITAL_CASE` | 数字化案例 | 智慧高速、数字孪生、智能建造示范 |
| `JOURNAL_PAPER` | 期刊论文 | 题录、摘要、DOI、研究结论 |
| `SOFTWARE_PRODUCT` | 软件/平台 | BIM、CIM、项目管理、数字底座 |
| `IOT_PRODUCT` | 物联网产品 | 传感器、监测终端、边缘网关 |
| `LOW_ALTITUDE_EQUIPMENT` | 低空装备 | 无人机巡检、测绘、吊运、机场 |
| `AI_EQUIPMENT` | AI设备/机器人 | AI视觉、巡检机器人、智能施工装备 |
| `SAFETY_REGULATION` | 安全规定 | 法规、规章、标准、指南、监管通知 |
| `SAFETY_CASE` | 安全案例 | 通报、调查报告、处罚、整改案例 |

## 3. 通用情报条目

所有内容共有：

- 标题、内容类型、内容域；
- 一句话事实、结构化摘要、推荐理由；
- 主文档版本及补充文档；
- 发布机关/作者/厂商/应用单位等实体；
- 行业、专业、工程阶段、应用场景、地区和技术标签；
- 相关性、权威性、影响、新颖性、时效、证据、置信和热度分；
- 核验状态、发布状态、风险等级；
- AI生成标识、提示词/模型版本；
- 发布时间、撤回时间、当前发布修订号。

## 4. 类型化字段

### 4.1 数字化案例

- 技术类别；
- 工程领域与场景；
- 实施单位、供应商、项目；
- 解决的问题与核心能力；
- 部署方式和应用规模；
- 成熟度：`CONCEPT`、`LAB_PROTOTYPE`、`ENGINEERING_PROTOTYPE`、`PILOT`、`SINGLE_PROJECT_PRODUCTION`、`MULTI_PROJECT_REPLICATION`、`ENTERPRISE_SCALE`、`UNKNOWN`；
- 厂商宣称效果；
- 被独立证据支持的效果；
- 四川路桥适用性；
- 复制条件、限制和风险。

### 4.2 期刊论文

- DOI、期刊、ISSN、卷期、年份；
- 作者、机构、摘要、关键词；
- 研究对象、方法、样本/试验条件；
- 主要结论及限制；
- 开放获取状态和原文入口。

平台默认不保存和再分发未授权全文。

### 4.3 软件、物联网和设备

- 产品类别、厂商、产品名和型号；
- 能力、接口、部署方式和应用场景；
- 工程案例和当前部署状态；
- 证据等级；
- 厂商声明与验证能力分栏；
- 已知限制、供应条件和合规要求。

### 4.4 安全规定

- 文号、发布机关、司法/行政辖区；
- 效力层级；
- 发布、实施、失效时间；
- 状态：`DRAFT`、`NOT_EFFECTIVE`、`EFFECTIVE`、`AMENDED`、`REPEALED`、`SUPERSEDED`、`EXPIRED`、`UNKNOWN`；
- 适用地区、行业、工程和作业场景；
- 强制性要求；
- 修订、替代、废止和配套文件关系；
- 对四川路桥可能影响的初步归纳。

效力状态必须由官方文件或审核员确认，不允许模型独立认定。

### 4.5 安全案例

- 发生时间、地区、工程类型、项目阶段、作业环节；
- 事故类型和严重程度；
- 死亡、受伤和直接经济损失；
- 调查状态：`UNVERIFIED_LEAD`、`INITIAL_OFFICIAL_REPORT`、`UNDER_INVESTIGATION`、`FINAL_INVESTIGATION_REPORT`、`ENFORCEMENT_DECISION`、`RECTIFICATION_FOLLOW_UP`、`CLOSED`、`CORRECTED`、`WITHDRAWN`；
- 已确认事实；
- 直接原因、间接/根本原因；
- 责任认定；
- 整改和防范措施；
- 相似风险场景和检查要点。

伤亡、原因和责任必须以有权机关证据为依据。非必要个人信息不得采集和展示。

## 5. 事实与证据

### 5.1 原子事实

重要字段先表示为 `Claim`：

```json
{
  "claim_type": "effective_date",
  "subject": "某安全规定",
  "predicate": "takes_effect_on",
  "literal_value": {"date": "2026-09-01"},
  "verification_status": "verified",
  "confidence": 0.99
}
```

### 5.2 证据定位

每个重要事实至少有一条 `ClaimEvidence`，定位方式支持：

- HTML 段落序号和字符区间；
- PDF 页码、文本区间和坐标框；
- OCR 页码和边界框；
- 表格页码、表号、行和列；
- 原始 URL、文档版本，以及可用时的内容哈希。

开发、演示与候选输出允许不预先填写证据摘要哈希，缺失哈希不得阻塞素材打开或非生产联调。进入生产发布门禁时，由服务端从规范化原始字节和证据片段计算并验证 SHA-256；客户端或模型上送的哈希仅作候选，不是权威依据。

前端不得只展示一个“有来源”图标，必须能够展开到证据片段。

### 5.3 证据角色

- `PRIMARY_OFFICIAL`：一手官方；
- `PRIMARY_AUTHOR`：论文作者/发布主体；
- `VENDOR_CLAIM`：厂商声明；
- `INDEPENDENT_CONFIRMATION`：独立验证；
- `SECONDARY_REPORT`：二手报道；
- `CONTRADICTING`：冲突证据。

## 6. 文档版本与关系

文档变化类型：

- `INITIAL`；
- `METADATA_ONLY`；
- `CONTENT_UPDATE`；
- `CORRECTION`；
- `AMENDMENT`；
- `REPLACEMENT`；
- `WITHDRAWAL`。

事件/条目关系：

- `AMENDS` 修订；
- `CLARIFIES` 澄清；
- `SUPERSEDES` 替代；
- `CANCELS` 撤销；
- `CORRECTS` 更正；
- `FOLLOW_UP` 后续；
- `INVESTIGATES` 调查；
- `PENALIZES` 处罚；
- `RECTIFIES` 整改；
- `RELATED_TO` 相关；
- `SAME_PRODUCT` 同一产品；
- `APPLIED_IN` 应用于。

同一事故、法规或产品的不同阶段不得被近似去重删除。

## 7. 状态机

### 7.1 处理状态

```text
DISCOVERED → FETCHED → PARSED → ENRICHED → GATE_PENDING
```

门禁分流：

- `OUT_OF_SCOPE`：不在首期范围；
- `DUPLICATE_LINKED`：作为既有条目的补充来源；
- `QUARANTINED`：异常、冲突或疑似攻击；
- `REVIEW_PENDING`：等待审核；
- `AUTO_PUBLISHED`：通过自动发布策略；
- `REJECTED`：人工驳回。

审核与发布：

```text
REVIEW_PENDING → APPROVED → PUBLISHED
PUBLISHED → UPDATE_DETECTED → RE_REVIEW_PENDING → CORRECTED / REPUBLISHED
PUBLISHED → ARCHIVED / RETRACTED / SUPERSEDED
```

### 7.2 发布不可变性

发布内容以 `PublicationRevision` 快照保存。任何编辑、证据变化、模型重跑、纠错和撤回都生成新修订，不覆盖历史快照。

## 8. 风险分级与门禁

| 等级 | 示例 | 首期策略 |
|---|---|---|
| R1 | 论文题录、政府数字化案例 | 高置信、证据齐全可自动收录；精选规则可配置 |
| R2 | 厂商软件、设备、产品案例 | 可自动收录，精选必审，声明需醒目标注 |
| R3 | 安全规定、事故通报、调查报告 | 自动收录题录，精选和解读必须人工审核 |
| R4 | 事故线索、来源冲突、重大伤亡、效力不明 | 仅进入隔离/核实工作台 |

R3 在人工审核前只能向普通用户投影：标题、内容类型、官方来源、原文发布时间、首次发现时间、原文链接和“待审核”状态。AI 摘要、伤亡、损失、事故原因、责任、法规效力和适用性仅在审核后台可见。R4 无论人工按钮如何操作都不能直接发布，必须先解除问题、形成审计记录并重新定级。

### 强制拒绝发布条件

- 无主来源或主来源不可追溯；
- 关键事实无证据；
- 生产发布时文档版本不明确，或服务端无法计算、绑定并验证内容哈希；
- 安全内容的原因、责任或法规效力仅由模型推断；
- 厂商量化效果被改写为平台确认事实；
- 原文已撤回而未标记；
- 疑似提示词注入或恶意文档未解除隔离；
- 存在未解决的关键字段冲突。

## 9. 热点、影响和可信度分离

热点只表示近期关注，不表示可信。独立来源数量需去除转载链和同一机构镜像。

```text
heat = log(1 + independent_source_count) × time_decay(type)
```

置信度是发布门槛；影响与相关性决定精选排序；热度只用于热点页和趋势提示。

## 10. 数据生命周期

- 原始对象：合法取得后不可变保存，按来源政策设置保留期；
- 解析文本：随文档版本保存；
- AI候选：保留输入哈希、模型和提示词版本；
- 发布快照：长期保留；
- 审计日志：只追加；
- 撤回内容：对普通用户显示撤回状态，不物理删除；
- 删除请求：由合规管理员执行，保留最小审计记录。
