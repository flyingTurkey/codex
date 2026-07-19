import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  actionableSourceCount,
  healthSignature,
  shouldNotifyTransition,
} from '../app/composables/usePersonalHealthNotifications'

describe('PERS-09 personal workspace convergence', () => {
  it('removes legacy management navigation and redirects old routes', () => {
    const navigation = readFileSync(resolve(process.cwd(), 'app/navigation.ts'), 'utf8')
    const middleware = readFileSync(
      resolve(process.cwd(), 'app/middleware/legacy-personal-workspace.global.ts'),
      'utf8',
    )
    for (const label of ['来源健康', '覆盖缺口', '审核工作台', '聚类工作台', 'R17观察门禁']) {
      expect(navigation).not.toContain(label)
    }
    expect(middleware).toContain("'/sources'")
    expect(middleware).toContain('/admin/sources')
    expect(middleware).toContain('/admin/review')
    expect(middleware).toContain('/admin/pilot')
  })

  it('shows every personal runtime state without governance vocabulary', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/sources.vue'), 'utf8')
    for (const label of [
      '用户已启用', '实际运行中', '熔断中', '配置失败', '模型画像部分完成', '预算暂停',
      '活动历史', '运行摘要',
    ]) expect(page).toContain(label)
    for (const term of ['候选审批', '策略版本', '连接器配置', '试运行批准']) {
      expect(page).not.toContain(term)
    }
  })

  it('counts distinct actionable sources and ignores manually disabled sources', () => {
    const sources = [
      {
        id: 'a', desired_enabled: true, streams: [{
          id: 'a1', status: 'READY', health_status: 'UNHEALTHY', health_reason: 'TIMEOUT',
          runtime_state: 'CIRCUIT_OPEN',
        }, {
          id: 'a2', status: 'READY', health_status: 'DEGRADED', health_reason: 'CONTENT_STALE',
          runtime_state: 'SCHEDULED',
        }],
      },
      {
        id: 'b', desired_enabled: false, streams: [{
          id: 'b1', status: 'PROBE_FAILED', health_status: 'UNHEALTHY', health_reason: 'TIMEOUT',
          runtime_state: 'INACCESSIBLE',
        }],
      },
    ]
    expect(actionableSourceCount(sources as never)).toBe(1)
  })

  it('notifies only a changed health signature and supports one recovery', () => {
    const healthy = healthSignature({
      id: 'stream', status: 'READY', health_status: 'HEALTHY', health_reason: null,
      runtime_state: 'SCHEDULED',
    } as never)
    const failed = healthSignature({
      id: 'stream', status: 'READY', health_status: 'UNHEALTHY', health_reason: 'TIMEOUT',
      runtime_state: 'INACCESSIBLE',
    } as never)
    expect(shouldNotifyTransition(healthy, failed)).toBe(true)
    expect(shouldNotifyTransition(failed, failed)).toBe(false)
    expect(shouldNotifyTransition(failed, healthy)).toBe(true)
    expect(shouldNotifyTransition(null, failed)).toBe(false)
  })

  it('keeps evidence facts and AI interpretation semantically separate on v2 reading surfaces', () => {
    const card = readFileSync(resolve(process.cwd(), 'app/components/IntelligenceCard.vue'), 'utf8')
    const detail = readFileSync(resolve(process.cwd(), 'app/pages/events/[id].vue'), 'utf8')
    const search = readFileSync(resolve(process.cwd(), 'app/pages/search.vue'), 'utf8')
    expect(card).toContain('原文摘录')
    expect(card).toContain('AI 总结')
    expect(detail).toContain('原文摘录')
    expect(detail).toContain('AI 总结')
    expect(search).toContain('accepted claims')
  })
})
