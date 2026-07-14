import { mount } from '@vue/test-utils'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const conflict = {
  candidate_claim_id: '019b0000-0000-7000-8000-000000004502',
  candidate_value: 52,
  current_claim_id: '019b0000-0000-7000-8000-000000004501',
  current_value: 48,
  detected_at: '2025-01-22T08:00:00Z',
  event_id: '019b0000-0000-7000-8000-000000004001',
  field: 'DEATH_COUNT',
  id: '019b0000-0000-7000-8000-000000004500',
  resolution_reason: null,
  resolved_at: null,
  resolved_by: null,
  resolved_claim_id: null,
  status: 'PENDING_REVIEW',
} as const

describe('round 04 claim conflict panel', () => {
  it('renders reviewer-only facts, status, and the separation-of-duties warning', () => {
    const ClaimConflictPanel = componentModules['../app/components/ClaimConflictPanel.vue']?.default
    expect(ClaimConflictPanel, 'ClaimConflictPanel.vue should exist').toBeDefined()
    if (!ClaimConflictPanel) return

    const wrapper = mount(ClaimConflictPanel, {
      props: { busyConflictId: null, conflicts: [conflict], loading: false },
    })

    expect(wrapper.text()).toContain('关键字段冲突')
    expect(wrapper.text()).toContain('死亡人数')
    expect(wrapper.text()).toContain('当前已确认事实')
    expect(wrapper.text()).toContain('48')
    expect(wrapper.text()).toContain('候选事实')
    expect(wrapper.text()).toContain('52')
    expect(wrapper.text()).toContain('提交人不得审批自己提交的安全案例')
    expect(wrapper.findAll('[data-testid="conflict-action"]')).toHaveLength(3)
  })

  it('requires a reason before emitting one of the three explicit decisions', async () => {
    const ClaimConflictPanel = componentModules['../app/components/ClaimConflictPanel.vue']?.default
    expect(ClaimConflictPanel).toBeDefined()
    if (!ClaimConflictPanel) return

    const wrapper = mount(ClaimConflictPanel, {
      props: { busyConflictId: null, conflicts: [conflict], loading: false },
    })
    const candidateButton = wrapper.get('[data-action="ACCEPT_CANDIDATE"]')
    expect(candidateButton.attributes('disabled')).toBeDefined()

    await wrapper.get('textarea').setValue('正式调查报告是更新且经逐字段审核的官方证据')
    expect(candidateButton.attributes('disabled')).toBeUndefined()
    await candidateButton.trigger('click')

    expect(wrapper.emitted('decide')).toEqual([[
      conflict.id,
      {
        action: 'ACCEPT_CANDIDATE',
        reason: '正式调查报告是更新且经逐字段审核的官方证据',
      },
    ]])
  })

  it('keeps resolved conflicts auditable without rendering decision controls', () => {
    const ClaimConflictPanel = componentModules['../app/components/ClaimConflictPanel.vue']?.default
    expect(ClaimConflictPanel).toBeDefined()
    if (!ClaimConflictPanel) return

    const wrapper = mount(ClaimConflictPanel, {
      props: {
        busyConflictId: null,
        conflicts: [{
          ...conflict,
          resolution_reason: '采用正式调查报告最终数字',
          resolved_at: '2025-01-22T09:00:00Z',
          resolved_by: '019b0000-0000-7000-8000-000000004599',
          resolved_claim_id: conflict.candidate_claim_id,
          status: 'RESOLVED',
        }],
        loading: false,
      },
    })

    expect(wrapper.text()).toContain('已处理')
    expect(wrapper.text()).toContain('采用正式调查报告最终数字')
    expect(wrapper.find('[data-testid="conflict-actions"]').exists()).toBe(false)
  })
})
