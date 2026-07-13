import type { StatusBadgeTone } from '@srbg/ui'

interface EmptyPageConfiguration {
  readonly title: string
  readonly eyebrow: string
  readonly description: string
  readonly statusLabel: string
  readonly statusTone: StatusBadgeTone
  readonly emptyTitle: string
  readonly emptyDescription: string
}

export const emptyFeedPages = {
  selected: {
    title: '今日精选',
    eyebrow: '精选发布',
    description: '通过来源、证据和发布门禁的精选内容将在后续轮次接入。',
    statusLabel: '后续轮次接入',
    statusTone: 'info',
    emptyTitle: '业务数据尚未接入',
    emptyDescription: '精选内容将在发布门禁与真实数据链路就绪后接入。',
  },
  all: {
    title: '全部动态',
    eyebrow: '可见情报投影',
    description: '自动收录与受限投影能力将在后续轮次接入。',
    statusLabel: '后续轮次接入',
    statusTone: 'info',
    emptyTitle: '业务数据尚未接入',
    emptyDescription: '后续轮次将接入带来源与处理状态的真实动态。',
  },
  digital: {
    title: '数字化',
    eyebrow: '数字化情报',
    description: '案例、论文、软件与设备情报将在后续轮次接入。',
    statusLabel: '后续轮次接入',
    statusTone: 'info',
    emptyTitle: '业务数据尚未接入',
    emptyDescription: '数字化内容将在证据与类型化契约就绪后接入。',
  },
  safety: {
    title: '安全情报',
    eyebrow: '安全规定与官方案例',
    description: '安全内容将在服务端受限投影与人工审核能力就绪后接入。',
    statusLabel: '后续轮次接入',
    statusTone: 'pending',
    emptyTitle: '业务数据尚未接入',
    emptyDescription: '后续轮次将接入经过安全门禁处理的规定与官方案例。',
  },
  daily: {
    title: '行业日报',
    eyebrow: '固定日报快照',
    description: '日报生成、审核与发布能力尚未接入。',
    statusLabel: '后续轮次接入',
    statusTone: 'info',
    emptyTitle: '业务数据尚未接入',
    emptyDescription: '行业日报将在真实快照与审核链路就绪后接入。',
  },
  saved: {
    title: '收藏',
    eyebrow: '个人情报清单',
    description: '收藏与集合能力尚未接入。',
    statusLabel: '后续轮次接入',
    statusTone: 'info',
    emptyTitle: '业务数据尚未接入',
    emptyDescription: '收藏能力将在真实内容与用户能力就绪后接入。',
  },
} as const satisfies Record<string, EmptyPageConfiguration>
