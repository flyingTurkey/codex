import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { mockV2Event, v2Feed } from './v2-fixtures'

const paper = {
  id: '019b0000-0000-7000-8000-000000006201',
  title: '桥梁数字孪生研究',
  source_name: 'OpenAlex',
  source_published_at: '2025-07-01T00:00:00Z',
  first_discovered_at: '2026-07-15T04:05:00Z',
  original_url: 'https://doi.org/10.1000/bridge.2025.1',
  domain: 'DIGITAL',
  content_type: 'JOURNAL_PAPER',
  one_sentence_fact: '论文题录显示研究主题为桥梁数字孪生。',
}

async function mockPaper(page: Page): Promise<void> {
  await page.route('**/api/v2/feed**', route => route.fulfill({ json: v2Feed([paper]) }))
  await mockV2Event(page, paper, { official: false })
  await page.route(`**/api/v1/items/${paper.id}`, route => route.fulfill({ status: 404 }))
  await page.route(`**/api/v1/events/${paper.id}/citation**`, route => route.fulfill({
    contentType: 'text/plain; charset=utf-8',
    body: '桥梁数字孪生研究[J]. 2025.',
  }))
}

test('paper category uses the v2 projection and keeps legacy score regions absent', async ({ page }) => {
  await mockPaper(page)
  await page.goto('/digital')
  await expect(page.locator('.srbg-app-shell[aria-busy]')).toHaveAttribute('aria-busy', 'false', { timeout: 20_000 })
  await page.getByRole('button', { name: '期刊论文' }).click()

  await expect(page.getByRole('heading', { level: 1, name: '期刊论文' })).toBeVisible()
  await expect(page.getByRole('button', { name: '期刊论文' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText(paper.title)).toBeVisible()
  await expect(page.getByText(paper.source_name)).toBeVisible()
  await expect(page.getByTestId('paper-summary')).toHaveCount(0)
  await expect(page.getByText('可信度')).toHaveCount(0)
})

test('@a11y paper reader separates source excerpt from unavailable AI summary', async ({ page }) => {
  await mockPaper(page)
  await page.goto(`/events/${paper.id}`)

  await expect(page.getByRole('heading', { level: 1, name: paper.title })).toBeVisible()
  await expect(page.getByRole('heading', { name: '原文摘录' })).toBeVisible()
  await expect(page.getByText(paper.one_sentence_fact)).toBeVisible()
  await expect(page.getByRole('heading', { name: /AI 总结/ })).toBeVisible()
  await expect(page.getByRole('link', { name: '查看原文' })).toHaveAttribute(
    'href',
    paper.original_url,
  )
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
})
