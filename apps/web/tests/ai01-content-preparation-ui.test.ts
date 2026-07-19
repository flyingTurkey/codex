import { mount } from '@vue/test-utils'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const components = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})
const providers = [
  {
    code: 'deepseek',
    base_url: 'https://api.deepseek.com',
    request_path: '/chat/completions',
    models: ['deepseek-v4-flash'],
    real_call_enabled: true,
    key_configured: false,
    runtime_status: 'MODEL_DISABLED',
    blocking_reasons: ['SECRET_NOT_CONFIGURED'],
  },
  {
    code: 'glm',
    base_url: 'https://open.bigmodel.cn/api/paas/v4',
    request_path: '/chat/completions',
    models: ['glm-5.2'],
    real_call_enabled: false,
    key_configured: false,
    runtime_status: 'MODEL_DISABLED',
    blocking_reasons: ['MOCK_ONLY'],
  },
]

describe('R-AI01 model configuration and claim review UI', () => {
  it('shows pinned endpoints, readiness, and mock-only providers without arbitrary URL input', () => {
    const Panel = components['../app/components/AiConfigurationPanel.vue']?.default
    expect(Panel).toBeDefined()
    if (!Panel) return
    const wrapper = mount(Panel, { props: { providers } })
    expect(wrapper.text()).toContain('https://api.deepseek.com/chat/completions')
    expect(wrapper.text()).toContain('不可用（MODEL_DISABLED）')
    expect(wrapper.text()).toContain('仅 Mock')
    expect(wrapper.find('input[name="base_url"]').exists()).toBe(false)
    expect(wrapper.find('input[type="password"]').attributes('autocomplete')).toBe('new-password')
  })

  it('keeps a failed Secret value and clears it only after a successful save', async () => {
    const Panel = components['../app/components/AiConfigurationPanel.vue']?.default
    expect(Panel).toBeDefined()
    if (!Panel) return
    const wrapper = mount(Panel, {
      props: { providers, secretSavedNonce: 0, savingSecret: false },
    })
    const input = wrapper.get('input[type="password"]')
    await input.setValue('temporary-secret')
    await wrapper.get('[data-testid="save-secret"]').trigger('click')
    expect(wrapper.emitted('saveSecret')?.[0]).toEqual(['deepseek', 'temporary-secret'])
    expect(input.element.value).toBe('temporary-secret')

    await wrapper.setProps({ secretSavedNonce: 1 })
    expect(input.element.value).toBe('')
  })

  it('moves AI configuration to personal settings and retires claim review', () => {
    const settings = readFileSync(resolve(process.cwd(), 'app/pages/settings/ai.vue'), 'utf8')
    expect(settings).toContain('/api/v1/settings/ai/providers')
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/ai.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/review/[id].vue'))).toBe(false)
  })

  it('uses only shared design tokens', () => {
    const panel = readFileSync(resolve(process.cwd(), 'app/components/AiConfigurationPanel.vue'), 'utf8')
    expect(panel).toContain('var(--color-')
    expect(panel).not.toMatch(/#[0-9a-f]{3,8}/i)
  })
})
