# PERS-03 来源运行与健康自愈验收记录

## 范围

本轮把 PERS-02 已安全探测的 `source_stream` 接入受控生产调度。个人流不读取策略人工决定、来源资格包、试运行批准、生产批准或多人职责分离事实；旧事实与旧调度路径均未删除。不包含 DeepSeek 画像、自动画像或全网来源发现。

## 权威与安全边界

个人流可调度的必要条件固定为：来源 `desired_enabled=true`、未手工停用、流为 `READY`、当前 `stream_config_version` 哈希仍匹配、安全访问状态可用、请求和字节预算未耗尽、熔断允许执行。PostgreSQL 的 claim、执行租约、请求预算和 raw/document 登记函数均再次验证这些事实。

统一 HTTP 客户端会在每个物理请求前执行授权回调，并对每次重试和每个重定向目标重新执行允许主机、DNS 公网地址、DNS pin、peer、限速、预算、超时与重试上限检查。探测通过的 robots 边界属于当前流配置的安全准入；登录、验证码和付费墙不会绕过。

原始响应先写入私有对象存储并登记不可变 capture，之后才解析。解析失败、MIME 不符、字段缺失或访问屏障不会覆盖或删除原始对象。

## 调度和自愈

- 新流间隔为一小时；使用最近 20 次有新内容的观察时间中位间隔的四分之一作为基线。
- 最终间隔限制在 15 分钟至 24 小时，附加 ±10% 抖动；无更新按 1.5 倍退避，有新内容按基线 0.8 倍适度加快。
- 连续五次失败打开 30 分钟熔断；到期 claim 将状态改为半开。半开成功关闭熔断，失败重新打开 30 分钟。
- 连续三次零发现只为该流创建异常并幂等排队重新探测，不暂停同一来源的其他流。

## 验证证据

- `make personal-source-test`：迁移执行 `0022 -> 0023 -> 0022 -> 0023`，并覆盖个人 API、探测、HTTP 安全、Worker raw-first、解析失败和页面契约。
- 根级 `make lint`、`make typecheck`、`make test`、`make contract-test`、`make security-check`。
- 采集门禁：`make fixture-replay`、`make quality-gate`。
- 前端门禁：`make web-e2e`、`make web-a11y`。

最终结果：`personal-source-test` 通过（130 个后端/Worker、115 个 Web 测试）；
`quality-gate` 通过（1261 passed、32 skipped，53 个 UI、115 个 Web、97 个契约测试，
Trivy 无 HIGH/CRITICAL）；`fixture-replay` 通过（364 个测试）；`web-e2e` 53 个通过；
`web-a11y` 17 个通过。依赖审计仅报告 1 个 low，未达到门禁失败级别。
