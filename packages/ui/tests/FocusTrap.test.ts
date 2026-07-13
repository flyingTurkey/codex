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

  it('excludes every negative tabindex value from the Tab loop', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <button id="negative-head" type="button" tabindex="-2">负值开头</button>
          <button id="tabbable-first" type="button">第一项</button>
          <button id="tabbable-last" type="button">最后一项</button>
          <button id="negative-tail" type="button" tabindex="-3">负值结尾</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    wrapper.get<HTMLButtonElement>('#tabbable-last').element.focus()
    await wrapper.get('#tabbable-last').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('tabbable-first')

    wrapper.get<HTMLButtonElement>('#tabbable-first').element.focus()
    await wrapper.get('#tabbable-first').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('tabbable-last')

    wrapper.unmount()
  })

  it('uses only the checked radio as the Tab stop for a checked group', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <input id="checked-before" name="checked-group" type="radio">
          <input id="checked-stop" name="checked-group" type="radio" checked>
          <button id="checked-boundary" type="button">边界</button>
          <input id="checked-after" name="checked-group" type="radio">
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    wrapper.get<HTMLButtonElement>('#checked-boundary').element.focus()
    await wrapper.get('#checked-boundary').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('checked-stop')

    await wrapper.get('#checked-stop').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('checked-boundary')

    wrapper.unmount()
  })

  it('uses the first available radio as the Tab stop when a group has no selection', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <input id="unchecked-disabled" name="unchecked-group" type="radio" disabled>
          <div hidden><input id="unchecked-hidden" name="unchecked-group" type="radio"></div>
          <input id="unchecked-first" name="unchecked-group" type="radio">
          <button id="unchecked-boundary" type="button">边界</button>
          <input id="unchecked-second" name="unchecked-group" type="radio">
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    wrapper.get<HTMLButtonElement>('#unchecked-boundary').element.focus()
    await wrapper.get('#unchecked-boundary').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('unchecked-first')

    wrapper.unmount()
  })

  it('keeps same-name radio groups in different forms as separate Tab stops', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <form><input id="form-a-radio" name="shared-name" type="radio" checked></form>
          <button id="between-forms" type="button">中间项</button>
          <form><input id="form-b-radio" name="shared-name" type="radio"></form>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    await wrapper.get('#form-a-radio').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('form-b-radio')

    wrapper.unmount()
  })

  it('includes summary and contenteditable elements in the Tab loop', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <details open><summary id="native-summary">摘要</summary><p>详情</p></details>
          <button id="semantic-boundary" type="button">边界</button>
          <div id="editable-stop" contenteditable>可编辑内容</div>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    wrapper.get<HTMLElement>('#editable-stop').element.focus()
    await wrapper.get('#editable-stop').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('native-summary')

    await wrapper.get('#native-summary').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('editable-stop')

    wrapper.unmount()
  })

  it('keeps the first direct legend interactive while excluding the rest of a disabled fieldset', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <fieldset disabled>
            <legend><button id="legend-action" type="button">图例操作</button></legend>
            <button id="fieldset-disabled-action" type="button">禁用操作</button>
          </fieldset>
          <button id="fieldset-boundary" type="button">边界</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    wrapper.get<HTMLButtonElement>('#fieldset-boundary').element.focus()
    await wrapper.get('#fieldset-boundary').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('legend-action')

    wrapper.unmount()
  })

  it('keeps a closed details summary tabbable while excluding its collapsed descendants', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <details>
            <summary id="closed-summary">摘要</summary>
            <button id="closed-details-action" type="button">折叠操作</button>
          </details>
          <button id="details-boundary" type="button">边界</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()

    wrapper.get<HTMLButtonElement>('#details-boundary').element.focus()
    await wrapper.get('#details-boundary').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('closed-summary')

    wrapper.unmount()
  })

  it('orders positive tabindex values before ordinary controls in browser Tab order', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <button id="ordinary-first" type="button">普通开头</button>
          <button id="positive-three" type="button" tabindex="3">正值三</button>
          <button id="positive-one" type="button" tabindex="1">正值一</button>
          <button id="ordinary-last" type="button">普通结尾</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()
    expect(document.activeElement?.id).toBe('positive-one')

    await wrapper.get('#positive-one').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('ordinary-last')

    await wrapper.get('#ordinary-last').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('positive-one')

    wrapper.unmount()
  })

  it('keeps equal positive tabindex values in DOM order', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false },
      slots: {
        default: `
          <button id="equal-first" type="button" tabindex="2">同值开头</button>
          <button id="lower-positive" type="button" tabindex="1">较低值</button>
          <button id="equal-last" type="button" tabindex="2">同值结尾</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()
    expect(document.activeElement?.id).toBe('lower-positive')

    await wrapper.get('#lower-positive').trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement?.id).toBe('equal-last')

    await wrapper.get('#equal-last').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement?.id).toBe('lower-positive')

    wrapper.unmount()
  })

  it('accepts an explicit negative tabindex as the programmatic initial focus target', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false, initialFocus: '#programmatic-target' },
      slots: {
        default: `
          <div id="programmatic-target" tabindex="-1">程序焦点</div>
          <button id="programmatic-fallback" type="button">回退</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()
    expect(document.activeElement?.id).toBe('programmatic-target')

    wrapper.unmount()
  })

  it('falls back to the first tabbable when initialFocus points to a plain heading', async () => {
    const wrapper = mount(FocusTrap, {
      attachTo: document.body,
      props: { active: false, initialFocus: '#plain-heading' },
      slots: {
        default: `
          <h2 id="plain-heading">普通标题</h2>
          <button id="heading-fallback" type="button">回退</button>
        `,
      },
    })

    await wrapper.setProps({ active: true })
    await nextTick()
    expect(document.activeElement?.id).toBe('heading-fallback')

    wrapper.unmount()
  })
})
