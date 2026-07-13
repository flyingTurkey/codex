import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import { ResponsiveDrawer } from '../src/index'

describe('ResponsiveDrawer', () => {
  it('closes on Escape and backdrop, locks scrolling, and returns focus after parent closes it', async () => {
    const trigger = document.createElement('button')
    trigger.textContent = '打开证据'
    document.body.append(trigger)
    trigger.focus()

    const wrapper = mount(ResponsiveDrawer, {
      attachTo: document.body,
      props: { modelValue: false, title: '证据' },
      slots: { default: '<button type="button" data-test="inside">抽屉操作</button>' },
    })

    await wrapper.setProps({ modelValue: true })
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')
    expect(wrapper.get('[role="dialog"]').attributes('aria-modal')).toBe('true')

    await wrapper.get('[role="dialog"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])

    await wrapper.setProps({ modelValue: false })
    await nextTick()
    expect(document.body.style.overflow).toBe('')
    expect(document.activeElement).toBe(trigger)

    await wrapper.setProps({ modelValue: true })
    await wrapper.get('.srbg-drawer__backdrop').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])

    await wrapper.setProps({ modelValue: false })
    wrapper.unmount()
    trigger.remove()
  })
})
