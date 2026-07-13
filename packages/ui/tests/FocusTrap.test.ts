import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import { FocusTrap } from '../src/index'

describe('FocusTrap', () => {
  it('sets initial focus, loops Tab, emits Escape, and restores focus when deactivated', async () => {
    const returnTarget = document.createElement('button')
    returnTarget.textContent = '打开'
    document.body.append(returnTarget)
    returnTarget.focus()

    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false, initialFocus: '#second-action' },
      slots: {
        default:
          '<button id="first-action" type="button">第一项</button><button id="second-action" type="button">第二项</button>',
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()
    expect(document.activeElement?.id).toBe('second-action')

    await wrapper.get('#second-action').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('first-action')

    await wrapper.get('#first-action').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('second-action')

    await wrapper.get('#second-action').trigger('keydown', { key: 'Escape' })
    expect(wrapper.emitted('escape')).toHaveLength(1)

    await wrapper.setProps({ active: false })
    await nextTick()
    expect(document.activeElement).toBe(returnTarget)

    wrapper.unmount()
    returnTarget.remove()
  })
})
