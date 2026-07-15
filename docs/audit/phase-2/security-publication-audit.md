# 第12轮安全、权限与发布审计

## 身份与普通用户API

Feed、Item/Event详情、热点、搜索、收藏、专题、日报、导出、指纹和证据页路由均声明 `CurrentPrincipal`。管理接口使用角色依赖。未发现公开的 `include_draft` 查询参数。

但当前读边界为 PARTIAL：

- TEST 环境默认本地身份，无请求头访问 `/me`、Feed和搜索仍返回200；这符合开发模式，但不能作为生产匿名访问。
- 日报服务内部通过 reviewer/platform_admin/auditor 角色计算 `include_draft`（`discovery/service.py:257-269`）；普通用户不可传参，但仍是同一业务表查询，而非专用发布投影。
- 审核详情内部使用 `include_unpublished=True`；普通详情固定 false。静态和角色测试未发现普通用户直接控制该值。
- 普通读连接 `srbg_api_login` 可直接 SELECT source、document、claim、publication 等业务表；不存在二阶段要求的专用只读发布投影登录。

## 实际数据库登录与授权

以下结果通过各容器中的实际连接建立，查询同时输出 `session_user/current_user`，不是 owner `SET ROLE` 模拟：

| 登录 | 继承 | 关键权限 |
|---|---|---|
| `srbg_api_login` | `srbg_api_role -> srbg_runtime` | 可读写 source/document/intelligence_item/saved_item/audit_log；可写 event和claim；publication/revision只读 |
| `srbg_worker_login` | `srbg_worker_role -> srbg_runtime` | 与API相近，可读写业务表和audit_log；publication/revision只读 |
| `srbg_publisher_login` | publication writer | publication和revision可写；可维护projection/search/daily；audit_log可插入但不可更新/删除 |
| `srbg` | owner/superuser | 本地迁移与管理；能够重写数据库对象和关闭触发器 |

API/Worker对 `alembic_version` 无 SELECT，使用 API 连接执行 `alembic current` 会得到 permission denied；owner实测版本为0012。不存在普通用户专用只读投影登录。

`has_table_privilege` 还显示 API/Worker 对 `audit_log` 有 INSERT/UPDATE/DELETE GRANT。回滚事务实测：

- API登录可直接 INSERT 任意 `AUDIT_PROBE`、任意 actor/target 和自造 entry_hash，成功后已回滚；
- UPDATE/DELETE 被 immutable trigger 拒绝；
- 未发现数据库外 hash root、每日独立锚定、WORM或独立备份清单。

因此 audit_log 是 append-only/tamper-evident 的应用哈希链，但写入主体不受控、根未独立锚定，owner可改写；状态为 PARTIAL，不能宣称绝对不可篡改。

## 发布服务与直写路径

- 代码仅定义一个 `PublicationService`（`publication/service.py:190`），API和Worker均注入它。
- `scripts/audit_publication_paths.py` 和 `round09-test`/`round11-test` 通过，未发现 repository 之外的 application publication SQL。
- API/Worker登录对 publication/revision INSERT/UPDATE/DELETE均为 false；publisher登录有必要写权限。
- publisher登录仍可绕过应用直接写 publication；这是专用连接的固有能力，必须由凭据隔离、仅服务持有和审计控制。当前API进程同时配置 publisher连接，故“普通API进程完全不持有发布凭据”不成立。
- projection失效使用 Outbox 与 SEARCH/CACHE/DAILY_DIGEST generation；确定性测试通过，但当前运行库 projection state/search projection 均为空，未形成真实一致性证据。

## R3/R4一致性

| 表面 | R3 | R4 | 结论 |
|---|---|---|---|
| Feed/Item API | viewer实测只返回标题、类型、来源、时间、URL、待审核提示；关键事实为空 | 查询排除R4 | R3 IMPLEMENTED，R4 E2/E3通过 |
| Selected | R3不进入selected，viewer实测selected仅发布项 | 排除 | 通过测试环境验证 |
| Search | projection构建只处理发布revision；当前运行投影为空 | 不进入 | 机制有测试，真实运行证据缺失 |
| Daily/Export | 固定发布revision；当前无日报 | R3/R4不进入 | FIXTURE_ONLY/未有运行数据 |
| Cache | generation/visible worker有测试 | R4不可见 | FIXTURE_ONLY |
| Page | R3 UI测试通过、无分数/关键事实 | 无R4页面 | E2通过 |

TEST数据库向viewer展示了测试Fixture发布内容，这是环境数据污染，不是R4泄露；生产必须使用隔离数据库并禁止测试来源进入普通投影。

## `risk_level`语义混用

`intelligence_item.risk_level` 同时承担发布门禁R1—R4、R3/R4投影范围和搜索筛选/字段；文件安全扫描另有 `risk_level`/安全事实语义，产品/内容严重度又通过类型字段表达。当前没有独立 `publication_risk_tier`、`content_severity`、`projection_level`，状态为 PARTIAL且存在明确语义冲突。

## 用户行为与隐私

- 当前代码把 SEARCH、VIEW_EVIDENCE、SAVE_ITEM、EXPORT、READ_DAILY 写入 `usage_metric_bucket`，只有 event_type、小时和计数，不含actor/target。
- 旧 `usage_event` 表仍存在，首次观察有250条 SEARCH，全部 `actor_id` 非空、`target_id` 为空。
- 未发现旧行为数据的同意、保留期限、删除作业或管理员访问专门边界；API/Worker可读该表。
- 收藏、反馈为实现功能保存用户ID，符合最小功能数据方向；具体保留/删除期限仍未确认。

因此“新被动行为不再个人化”已实现，但历史数据治理和数据库最小权限未完成，整体为 PARTIAL。

## 结论与优先级

P0：第13轮建立 event-keyed专用发布投影和只读登录；收回普通读服务对业务表的读取。P0：受控 audit writer 与独立hash根锚定。P1：拆分三类风险字段并统一R3/R4消费者。P1：处理旧 usage_event 的保留、删除和管理员访问政策。
