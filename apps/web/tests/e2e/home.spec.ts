import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

function collectBrowserErrors(page: Page): string[] {
  const errors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`)
    if (message.type() === 'warning' && /hydration|mismatch/i.test(message.text())) {
      errors.push(`console warning: ${message.text()}`)
    }
  })
  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`))
  return errors
}

async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => ({
    body: document.body.scrollWidth - document.body.clientWidth,
    document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }))
  expect(overflow).toEqual({ body: 0, document: 0 })
}

async function expectHydratedApp(page: Page): Promise<void> {
  await expect(page.locator('.srbg-app-shell[aria-busy]')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
}

function durationInMilliseconds(duration: string): number {
  return Math.max(
    ...duration.split(',').map((value) => {
      const part = value.trim()
      return part.endsWith('ms') ? Number.parseFloat(part) : Number.parseFloat(part) * 1_000
    }),
  )
}

test('root renders the selected-feed gate and honest no-score empty state', async ({
  page,
}) => {
  const browserErrors = collectBrowserErrors(page)

  await page.goto('/')
  await expectHydratedApp(page)

  await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
  await expect(page.getByText('真实评分待接入', { exact: true })).toBeVisible()
  await expect(page.getByText('API v1 · Schema 1.0.0', { exact: true })).toBeVisible()
  const updatedAt = page.getByTestId('page-updated-at')
  await expect(updatedAt).toBeVisible()
  await expect(page.getByRole('group', { name: '页面状态与更新时间' })).toContainText('更新时间：')
  const updatedAtIso = await updatedAt.getAttribute('datetime')
  expect(updatedAtIso).not.toBeNull()
  expect(Number.isNaN(Date.parse(updatedAtIso ?? ''))).toBe(false)
  await expect(page.getByRole('heading', { level: 2, name: '暂无精选内容' })).toBeVisible()
  await expect(page.getByTestId('metric')).toHaveCount(0)
  await expect(page.locator('article')).toHaveCount(0)
  await expect(page.getByText(/相关性评分|影响评分|权威评分/)).toHaveCount(0)
  await expectNoHorizontalOverflow(page)
  expect(browserErrors).toEqual([])
})

test('/ and /selected both mark 今日精选 as the current page', async ({ page }) => {
  for (const path of ['/', '/selected']) {
    await page.goto(path)
    await expect(page.getByRole('link', { name: '今日精选', exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
  }
})

test('primary navigation uses SPA routing and returns without a document navigation', async ({ page }) => {
  await page.goto('/')
  await expectHydratedApp(page)
  const navigationEntries = await page.evaluate(
    () => performance.getEntriesByType('navigation').length,
  )
  await page.evaluate(() => {
    document.documentElement.dataset.spaNavigationMarker = 'retained'
  })

  await page.getByRole('link', { name: '全部动态', exact: true }).click()

  await expect(page).toHaveURL(/\/all$/)
  await expect(page.getByRole('link', { name: '全部动态', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page.getByRole('heading', { level: 1, name: '全部动态' })).toBeVisible()
  expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(
    navigationEntries,
  )
  expect(await page.evaluate(() => document.documentElement.dataset.spaNavigationMarker)).toBe(
    'retained',
  )

  await page.getByRole('link', { name: '今日精选', exact: true }).click()

  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('link', { name: '今日精选', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  )
  await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
  expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(
    navigationEntries,
  )
  expect(await page.evaluate(() => document.documentElement.dataset.spaNavigationMarker)).toBe(
    'retained',
  )
})

test('skip link is first, moves focus to main, and desktop navigation remains tabbable', async ({
  page,
}) => {
  await page.goto('/')

  await page.keyboard.press('Tab')
  const skipLink = page.getByRole('link', { name: '跳到主内容' })
  await expect(skipLink).toBeVisible()
  await expect(skipLink).toBeFocused()

  await page.keyboard.press('Enter')
  await expect(page.getByRole('main')).toBeFocused()

  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('link', { name: '审核工作台', exact: true })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('link', { name: '管理入口', exact: true })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('link', { name: '收藏', exact: true })).toBeFocused()
  await page.keyboard.press('Shift+Tab')
  await expect(page.getByRole('link', { name: '行业日报', exact: true })).toBeFocused()
})

test('mobile drawer has keyboard focus containment, Escape close, and scroll restoration', async ({
  page,
}) => {
  const browserErrors = collectBrowserErrors(page)
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto('/')
  const initialOverflow = await page.evaluate(() => document.body.style.overflow)
  const trigger = page.getByRole('button', { name: '打开导航' })

  await expect(trigger).toBeEnabled({ timeout: 20_000 })
  await trigger.focus()
  await page.keyboard.press('Enter')

  await expect(trigger).toHaveAttribute('aria-expanded', 'true')
  const dialog = page.getByRole('dialog', { name: '四川路桥·智安情报' })
  await expect(dialog).toBeVisible()
  const closeButton = dialog.getByRole('button', { name: '关闭抽屉' })
  await expect(closeButton).toBeFocused()
  expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden')

  await page.keyboard.press('Shift+Tab')
  await expect(dialog.getByRole('link', { name: '审核工作台', exact: true })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(closeButton).toBeFocused()

  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
  await expect(trigger).toBeFocused()
  expect(await page.evaluate(() => document.body.style.overflow)).toBe(initialOverflow)
  expect(browserErrors).toEqual([])
})

const desktopWidths = [
  { width: 1920, sidebar: 216 },
  { width: 1440, sidebar: 216 },
  { width: 1439, sidebar: 200 },
  { width: 1280, sidebar: 200 },
  { width: 1279, sidebar: 72 },
  { width: 1024, sidebar: 72 },
] as const

for (const { width, sidebar } of desktopWidths) {
  test(`${width}px uses a ${sidebar}px computed desktop sidebar without horizontal overflow`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 768 })
    await page.goto('/')

    const navigation = page.getByRole('navigation', { name: '主导航' })
    await expect(navigation).toBeVisible()
    await expect(page.getByRole('button', { name: '打开导航' })).toBeHidden()
    expect((await navigation.locator('..').boundingBox())?.width).toBe(sidebar)
    await expectNoHorizontalOverflow(page)
  })
}

for (const viewport of [
  { width: 1023, height: 768 },
  { width: 768, height: 1024 },
] as const) {
  test(`${viewport.width}px hides desktop navigation and exposes the mobile header`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')

    await expect(page.getByRole('navigation', { name: '主导航' })).toBeHidden()
    await expect(page.getByRole('banner')).toBeVisible()
    await expect(page.getByRole('button', { name: '打开导航' })).toBeVisible()
    await expectNoHorizontalOverflow(page)
  })
}

test('720px equivalent 200% reading viewport keeps the primary task reachable', async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 450 })
  await page.goto('/')

  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')

  await expect(page.getByRole('main')).toBeFocused()
  await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()
  await expect(page.getByRole('button', { name: '打开导航' })).toBeVisible()
  await expectNoHorizontalOverflow(page)
})

test('reduced motion disables nonessential navigation and drawer motion', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  const trigger = page.getByRole('button', { name: '打开导航' })
  await expect(trigger).toBeEnabled({ timeout: 20_000 })
  await trigger.click()

  const motion = await page
    .getByRole('dialog', { name: '四川路桥·智安情报' })
    .evaluate((dialog) => {
      const linkStyle = getComputedStyle(dialog.querySelector('a')!)
      const drawerStyle = getComputedStyle(dialog.parentElement!)
      return {
        animationDuration: drawerStyle.animationDuration,
        animationName: drawerStyle.animationName,
        transitionDuration: linkStyle.transitionDuration,
      }
    })

  expect(durationInMilliseconds(motion.animationDuration)).toBeLessThanOrEqual(1)
  expect(motion.animationName).toBe('none')
  expect(durationInMilliseconds(motion.transitionDuration)).toBeLessThanOrEqual(1)
})

test('forced colors preserves a visible focus indicator and text-plus-icon status', async ({ page }) => {
  await page.emulateMedia({ forcedColors: 'active' })
  await page.goto('/')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')

  const currentLink = page.getByRole('link', { name: '今日精选', exact: true })
  await expect(currentLink).toBeFocused()
  const outline = await currentLink.evaluate((element) => {
    const style = getComputedStyle(element)
    return { style: style.outlineStyle, width: Number.parseFloat(style.outlineWidth) }
  })
  expect(outline.style).not.toBe('none')
  expect(outline.width).toBeGreaterThanOrEqual(2)

  const status = page.getByText('真实评分待接入', { exact: true }).locator('..')
  await expect(status).toBeVisible()
  const statusIcon = status.locator('svg')
  await expect(statusIcon).toBeVisible()
  const iconBox = await statusIcon.boundingBox()
  expect(iconBox).not.toBeNull()
  expect(iconBox!.width).toBeGreaterThan(0)
  expect(iconBox!.height).toBeGreaterThan(0)

  const iconStyle = await statusIcon.evaluate((element) => {
    const style = getComputedStyle(element)
    return { display: style.display, visibility: style.visibility }
  })
  expect(iconStyle.display).not.toBe('none')
  expect(iconStyle.visibility).toBe('visible')

  const pathStrokes = await statusIcon.locator('path').evaluateAll((paths) =>
    paths.map((path) => getComputedStyle(path).stroke),
  )
  expect(pathStrokes.length).toBeGreaterThan(0)
  expect(pathStrokes.every((stroke) => stroke !== 'none')).toBe(true)
})

test('@a11y root has an entirely empty axe violations array', async ({ page }) => {
  await page.goto('/')
  await expectHydratedApp(page)
  await expect(page.getByRole('heading', { level: 1, name: '今日精选' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})

test('@a11y opened mobile navigation drawer has an entirely empty axe violations array', async ({
  page,
}) => {
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto('/')
  const trigger = page.getByRole('button', { name: '打开导航' })
  await expect(trigger).toBeEnabled({ timeout: 20_000 })
  await trigger.click()
  await expect(page.getByRole('dialog', { name: '四川路桥·智安情报' })).toBeVisible()

  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
})
