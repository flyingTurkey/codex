# 公开资料核验记录

核验日期：2026-07-13。链接可能后续变化，接入生产前必须执行来源准入。

## AI HOT 可借鉴能力

- [Agent 接入](https://aihot.virxact.com/agent)：公开接口包含精选/全量信息流、热点、日报、日期索引、低流量更新指纹和版本接口。
- [AI HOT 首页](https://aihot.virxact.com/)：产品以精选、全部、分类、日报、主题和收藏形成内容消费闭环。

本项目只借鉴“多源采集—筛选—聚类—日报—多端分发”的产品结构，不依赖 AI HOT 的未公开后端，也不复制其行业分类。

## 数字交通与典型案例

- [交通运输部《关于推进公路数字化转型 加快智慧公路建设发展的意见》](https://xxgk.mot.gov.cn/jigou/glj/202309/t20230920_3922478.html)：明确设计、施工、养护、运营全生命周期数字化和智慧公路方向。
- [交通运输部农村公路数字化信息化建设典型案例](https://xxgk.mot.gov.cn/2020/jigou/glj/202310/P020250514394872177319.pdf)：可作为数字化案例字段和成效证据样本。
- [交通运输部低空交通运输应用场景典型案例](https://xxgk.mot.gov.cn/jigou/ysfws/202511/P020251118558935046297.pdf)：包含无人机公路巡检、AI识别和应急场景，可作为低空内容样本。
- [交通强国建设试点典型案例集](https://xxgk.mot.gov.cn/jigou/zhghs/202509/P020250916422010117400.pdf)：包含桥梁智能建造、数字化制造和监控系统案例。

## 安全来源

- [应急管理部事故调查报告栏目](https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/)：首期事故调查权威来源候选。
- [生产安全事故调查报告编制指南](https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202303/t20230316_444990.shtml)：可用于事故报告字段和证据结构设计。
- [生产安全事故应急预案管理办法](https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/201606/t20160603_405633.shtml)：安全规定来源和状态管理样本。

## 学术元数据

- [OpenAlex API](https://developers.openalex.org/api-reference/introduction)：提供 Works、Authors、Sources、Institutions、Topics 等公开学术元数据接口。
- [OpenAlex Works](https://developers.openalex.org/api-reference/works)：适合论文题录、主题和开放状态的自动化接入。
- [中国公路学报官网](https://zgglxb.chd.edu.cn/)：提供在线期刊、最新录用、当期和过刊入口，接入前需核验 RSS 和使用条款。

## 产品与企业来源示例

- [大疆行业应用交通/工程产品](https://enterprise.dji.com/cn)：可作为厂商产品和案例来源，但所有效果只能作为厂商声明，不能推导许可或适用资格。
- [大疆江阴大桥无人机巡检案例](https://enterprise.dji.com/cn/news/detail/drone-inspection-of-jiangyin-bridge)：可用于桥梁巡检产品案例固定样本的字段设计。
- [华为智慧交通](https://e.huawei.com/cn/industries/transportation)：可作为交通行业软件/平台线索源，案例和产品能力需保持发布方归因。

## 技术版本基线

- [Nuxt 4 正式发布](https://nuxt.com/blog/v4)：Nuxt 4 已于 2025 年正式发布；首期采用 Nuxt 4 稳定分支。
- [Nuxt UI 4](https://nuxt.com/blog/nuxt-ui-v4)：作为统一的 Vue/Nuxt 组件库，避免同时引入多套 UI 框架。
- [Node.js 版本状态](https://nodejs.org/en/about/previous-releases)：首期采用 Node.js 24 LTS，并在 lockfile 中固定实际补丁版本。
- [PostgreSQL 版本策略](https://www.postgresql.org/support/versioning/)：使用受支持主版本并跟随安全补丁；首期基线为 PostgreSQL 17。
