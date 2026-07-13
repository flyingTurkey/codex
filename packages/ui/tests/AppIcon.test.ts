import { mount } from '@vue/test-utils'

import { AppIcon, appIconNames, designTokens } from '../src/index'

describe('AppIcon', () => {
  it('renders only controlled Iconoir names with an accessible label', () => {
    const wrapper = mount(AppIcon, {
      props: { name: 'Star', label: '今日精选' },
    })

    expect(appIconNames).toContain('Star')
    expect(appIconNames).toContain('EmptyPage')
    expect(wrapper.attributes('data-icon')).toBe('Star')
    expect(wrapper.attributes('role')).toBe('img')
    expect(wrapper.attributes('aria-label')).toBe('今日精选')
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('hides decorative icons from assistive technology', () => {
    const wrapper = mount(AppIcon, { props: { name: 'Bookmark' } })

    expect(wrapper.attributes('aria-hidden')).toBe('true')
    expect(wrapper.attributes('role')).toBeUndefined()
  })

  it('derives its default dimensions and stroke from the canonical icon tokens', () => {
    const wrapper = mount(AppIcon, { props: { name: 'Star' } })
    const style = wrapper.attributes('style')

    expect(style ?? '').toContain(`--srbg-app-icon-size: ${designTokens.icon.defaultSize}`)
    expect(style ?? '').toContain(`--srbg-app-icon-stroke: ${designTokens.icon.defaultStroke}`)
  })
})
