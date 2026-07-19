import { expect, test } from '@playwright/test'
import { v2Projection } from './v2-fixtures'

const event = {
  id: '019b0000-0000-7000-8000-000000003001',
  title: '桥梁施工安全规定',
  source_name: '应急管理部',
  source_published_at: '2026-07-01T00:00:00Z',
  first_discovered_at: '2026-07-01T00:05:00Z',
  original_url: 'https://www.mem.gov.cn/test-only/round03.pdf',
  domain: 'SAFETY',
  content_type: 'SAFETY_REGULATION',
}
const mediaId = '019b0000-0000-7000-8000-000000003010'

test('v2 FULL reader renders only server-authorized media preview and download URLs', async ({ page }) => {
  const projection = v2Projection(event) as ReturnType<typeof v2Projection> & {
    media: unknown[]
    attachments: unknown[]
  }
  projection.media = [{
    media_id: mediaId,
    name: '证据图片',
    preview_url: `/api/v2/media/${mediaId}/preview`,
    rights_basis: 'SOURCE_AUTHORIZED',
  }]
  projection.attachments = [{
    media_id: mediaId,
    name: '公开附件.pdf',
    download_url: `/api/v2/media/${mediaId}/download`,
    source_url: 'https://example.com/attachment.pdf',
    redistribution_allowed: true,
  }]
  await page.route(`**/api/v2/events/${event.id}`, route => route.fulfill({ json: projection }))
  await page.route(`**/api/v2/media/${mediaId}/preview`, route => route.fulfill({
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
  }))
  await page.goto(`/events/${event.id}`)

  await expect(page.getByRole('img', { name: '证据图片' })).toHaveAttribute(
    'src',
    `/api/v2/media/${mediaId}/preview`,
  )
  await expect(page.getByRole('link', { name: '公开附件.pdf' })).toHaveAttribute(
    'href',
    `/api/v2/media/${mediaId}/download`,
  )
})

test('R3 projection never exposes media or attachment metadata', async ({ page }) => {
  await page.route(`**/api/v2/events/${event.id}`, route => route.fulfill({
    json: v2Projection(event, { risk: 'R3_METADATA' }),
  }))
  await page.goto(`/events/${event.id}`)

  await expect(page.getByText('待 Owner 审核')).toBeVisible()
  await expect(page.getByRole('img')).toHaveCount(0)
  await expect(page.getByRole('heading', { name: '附件' })).toHaveCount(0)
})

test('version timeline and diff remain v1 but old item detail is retired', async ({ page }) => {
  await page.route(`**/api/v1/items/${event.id}`, route => route.fulfill({ status: 404 }))
  await page.route(`**/api/v1/items/${event.id}/versions`, route => route.fulfill({
    json: { item_id: event.id, versions: [{ version_number: 3, is_current: true }] },
  }))
  await page.route(`**/api/v1/items/${event.id}/diff**`, route => route.fulfill({
    json: { item_id: event.id, material: true, change_type: 'CONTENT_UPDATE' },
  }))
  await page.goto('/')

  const responses = await page.evaluate(async id => Promise.all([
    fetch(`/api/v1/items/${id}`).then(response => response.status),
    fetch(`/api/v1/items/${id}/versions`).then(response => response.json()),
    fetch(`/api/v1/items/${id}/diff?from=1&to=3`).then(response => response.json()),
  ]), event.id)
  expect(responses[0]).toBe(404)
  expect(responses[1].versions[0].version_number).toBe(3)
  expect(responses[2].material).toBe(true)
})
