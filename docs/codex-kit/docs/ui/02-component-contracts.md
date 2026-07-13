# UI 02｜组件与数据契约

## 1. 组件树

```text
AppShell
├── AppSidebar
│   ├── BrandLockup
│   ├── PrimaryNav
│   ├── AdminEntry
│   └── UserProfile
└── IntelligenceFeedPage
    ├── FeedHeader
    │   ├── FreshnessIndicator
    │   ├── GlobalSearch
    │   └── FilterTrigger
    ├── FeedModeTabs
    ├── ChannelTabs
    ├── FilterPanel
    └── TimelineFeed
        └── TimelineItem
            └── IntelligenceCard
                ├── SourceLine
                ├── AttributionBadge
                ├── ReviewBadge
                ├── RelevanceReason
                ├── TypeSummary
                ├── ScoreSummary
                ├── SavedAction
                └── EvidenceTrigger
```

详情页复用 `SourceLine`、`ReviewBadge`、`TypeSummary`，并新增 `FactList`、`EvidencePanel`、`VersionTimeline`、`RelatedItems`。

## 2. Feed 查询契约

```http
GET /api/v1/feed
  ?mode=selected|all
  &domain=digital|safety
  &content_type=...
  &sort=latest|relevance|impact|heat
  &cursor=...
  &limit=20
```

API 返回扁平、稳定排序列表。前端按 `Asia/Shanghai` 对 `activity_at` 分组，避免 Cursor 跨日时后端分组产生重复或缺失。

```ts
export interface FeedPage {
  items: ItemSummary[]
  next_cursor: string | null
  fingerprint: string
  generated_at: string
  freshness: "fresh" | "delayed" | "partial"
  notices: FeedNotice[]
}

export interface ItemSummary {
  id: string
  publication_revision_id: string
  domain: "DIGITAL" | "SAFETY"
  content_type: string
  title: string
  one_sentence_fact: string | null
  source_name: string
  source_role: string
  source_published_at: string | null
  first_discovered_at: string
  last_updated_at: string
  activity_at: string
  review_status: string
  publication_status: string
  evidence_status: string
  evidence_count: number
  tags: string[]
  relevance_reason: string | null
  scores?: ScoreSummary
  type_summary: TypeSummary
  is_saved: boolean
  detail_available: boolean
}
```

`ScoreSummary` 在第 08 轮前可以省略；前端不得伪造分数。显示时至少提供相关性、影响、权威、证据、置信和热度中的可用分项及规则版本。

## 3. IntelligenceCard 契约

输入：

- `item: ItemSummary`；
- `density: compact | comfortable`；
- `projection: full | r3_restricted | withdrawn`；
- `showSaveAction: boolean`；
- `busyAction: null | save | evidence`。

输出事件：

- `open(item_id)`；
- `open-evidence(item_id)`；
- `toggle-save(item_id, next_state)`；
- `report-error(item_id)`。

组件规则：

- 不自行请求详情以补齐受限字段；
- 不根据来源名称推导权威等级；
- 不根据分数推导发布、审核或安全状态；
- 不复制六套内容卡，类型差异通过 `type_summary` 判别联合类型渲染；
- 原文失效、撤回、冲突和待复核必须有可读文字。

## 4. 服务端受限投影

R3 内容在人工审核前，普通用户只得到：

- 标题；
- 内容类型；
- 官方来源；
- 原文发布时间；
- 首次发现时间；
- 原文链接；
- “待审核”状态。

摘要、伤亡、原因、责任、法规效力、评分和证据片段不得出现在响应中。R4 不进入普通用户 Feed。该限制必须在服务端序列化/查询层完成。

## 5. 详情与证据

```http
GET /api/v1/items/{id}
GET /api/v1/events/{id}
```

列表统一走 `/feed`，不得新增平行 `/items` 列表。点击事实时，前端用 `claim_id` 关联 `evidence_ids`，高亮对应证据；没有 evidence 的关键事实不能表现为已核验。

## 6. 状态与错误

组件必须支持：

- skeleton loading；
- 首次空态；
- 筛选无结果；
- 来源延迟/数据可能不完整；
- API Problem Details；
- 原文失效；
- 内容已更新待复核；
- 已撤回；
- 来源冲突；
- 无 AI 摘要降级；
- 收藏成功、撤销和冲突恢复。

组件清单的机器可读版本见 `assets/ui/component_inventory.csv`。

