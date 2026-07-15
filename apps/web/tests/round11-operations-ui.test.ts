import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const overview = {
  observed_at: '2026-07-15T05:00:00Z',
  metrics: [
    { code: 'UNHEALTHY_SOURCES', value: 0, unit: 'count', status: 'PASS' },
    { code: 'FAILED_TASKS', value: 2, unit: 'count', status: 'FAIL' },
  ],
}

describe('round 11 operations UI', () => {
  it('renders metric status as text and exposes the evidence timestamp', () => {
    const OperationsDashboard = componentModules['../app/components/OperationsDashboard.vue']?.default
    expect(OperationsDashboard).toBeDefined()
    if (!OperationsDashboard) return
    const wrapper = mount(OperationsDashboard, {
      props: { overview, title: '来源健康', description: '采集来源与熔断状态' },
    })
    expect(wrapper.get('h1').text()).toBe('来源健康')
    expect(wrapper.text()).toContain('通过')
    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('2026年7月15日')
  })

  it('keeps all three admin views on one shared dashboard component', () => {
    for (const path of ['source-health', 'operations', 'quality']) {
      const page = readFileSync(resolve(process.cwd(), `app/pages/admin/${path}.vue`), 'utf8')
      expect(page).toContain('OperationsDashboard')
      expect(page).toContain('/api/v1/admin/operations/overview')
    }
  })

  it('uses design tokens instead of a parallel palette', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'app/components/OperationsDashboard.vue'),
      'utf8',
    )
    expect(source).toContain('var(--color-')
    expect(source).not.toMatch(/#[0-9a-f]{3,8}/i)
  })

  it('extends the shared IntelligenceCard with bounded pilot feedback', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'app/components/IntelligenceCard.vue'),
      'utf8',
    )
    expect(source).toContain("$fetch('/api/v1/feedback'")
    expect(source).toContain('data-testid="feedback-useful"')
    expect(source).toContain('data-testid="feedback-not-useful"')
  })
})
