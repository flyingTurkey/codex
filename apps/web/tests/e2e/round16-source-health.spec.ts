import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

async function mockRound16(page: Page): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: 'Round 16 operator',
      local_identity: true,
      roles: ['platform_admin'],
      user_id: '019b1600-0000-7000-8000-000000000401',
    }),
  }))
  await page.route('**/api/v1/admin/operations/overview', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      observed_at: '2026-07-16T05:00:00Z',
      metrics: [
        { code: 'UNHEALTHY_SOURCES', value: 1, unit: 'count', status: 'FAIL' },
        { code: 'OPEN_SOURCE_CIRCUITS', value: 1, unit: 'count', status: 'FAIL' },
        { code: 'FETCH_BACKLOG_AGE_SECONDS', value: 90, unit: 'seconds', status: 'PASS' },
        { code: 'SOURCE_SLO_VIOLATIONS', value: 1, unit: 'count', status: 'FAIL' },
      ],
    }),
  }))
  await page.route('**/api/v1/admin/operations/source-health', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{
      source_id: '019b1600-0000-7000-8000-000000000402',
      fetch_run_id: '019b1600-0000-7000-8000-000000000403',
      transport_status: 'SUCCEEDED',
      discovery_status: 'FALSE_SUCCESS',
      parse_status: 'DEGRADED',
      quality_status: 'DEGRADED',
      freshness_status: 'VIOLATED',
      rule_version: 'round16-health-v1',
      observed_at: '2026-07-16T05:00:00Z',
      anomalies: [{
        id: '019b1600-0000-7000-8000-000000000404',
        source_id: '019b1600-0000-7000-8000-000000000402',
        code: 'ZERO_DISCOVERY_STREAK',
        severity: 'WARNING',
        status: 'OPEN',
        detected_at: '2026-07-16T05:00:00Z',
      }],
    }]),
  }))
  await page.route('**/api/v1/admin/operations/replays', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([{
      id: '019b1600-0000-7000-8000-000000000405',
      task_kind: 'PARSER',
      error_code: 'PARSE_FAILED',
      priority: 8,
      reconstruction_status: 'NON_REPLAYABLE',
      blocked_reason: 'EVIDENCE_DELETED_OR_UNAVAILABLE',
      source_id: null,
      run_id: null,
      document_version_id: null,
      event_id: null,
      failed_at: '2026-07-16T05:00:00Z',
      replay_status: 'NON_REPLAYABLE',
    }]),
  }))
}

test('source health renders false success and safe replay state', async ({ page }) => {
  await mockRound16(page)
  await page.goto('/admin/source-health')
  await expect(page.getByText('ZERO_DISCOVERY_STREAK')).toBeVisible()
  await expect(page.getByText('EVIDENCE_DELETED_OR_UNAVAILABLE')).toBeVisible()
  await expect(page.getByText('SOURCE_SLO_VIOLATIONS')).toBeVisible()
})

test('source health has no serious accessibility violations @a11y', async ({ page }) => {
  await mockRound16(page)
  await page.goto('/admin/source-health')
  await expect(page.getByText('ZERO_DISCOVERY_STREAK')).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(violation => (
    violation.impact === 'critical' || violation.impact === 'serious'
  ))).toEqual([])
})
