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

  it('ignores hidden, inert, aria-hidden, and disabled-fieldset descendants when trapping focus', async () => {
    const returnTarget = document.createElement('button')
    document.body.append(returnTarget)
    returnTarget.focus()

    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false, initialFocus: '#hidden-initial' },
      slots: {
        default: `
          <button id="hidden-initial" style="display: none" type="button">隐藏初始项</button>
          <div hidden><button id="hidden-attribute" type="button">hidden</button></div>
          <div style="display: none"><button id="display-none" type="button">display none</button></div>
          <div style="visibility: hidden"><button id="visibility-hidden" type="button">visibility hidden</button></div>
          <div inert><button id="inert-action" type="button">inert</button></div>
          <div aria-hidden="true"><button id="aria-hidden-action" type="button">aria hidden</button></div>
          <fieldset disabled><button id="fieldset-disabled" type="button">fieldset disabled</button></fieldset>
          <button id="direct-disabled" type="button" disabled>disabled</button>
          <button id="visible-first" type="button">第一项</button>
          <button id="visible-last" type="button">最后一项</button>
          <div hidden><button id="hidden-tail" type="button">hidden tail</button></div>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()
    expect(document.activeElement?.id).toBe('visible-first')

    await wrapper.get('#visible-first').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('visible-last')

    await wrapper.get('#visible-last').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('visible-first')

    await wrapper.setProps({ active: false })
    wrapper.unmount()
    returnTarget.remove()
  })
})
