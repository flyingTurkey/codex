import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('round 16 operations UI', () => {
  it('reuses the operations dashboard and exposes health and replay queues', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/source-health.vue'), 'utf8')
    expect(page).toContain('OperationsDashboard')
    expect(page).toContain('/api/v1/admin/operations/source-health')
    expect(page).toContain('/api/v1/admin/operations/replays')
    expect(page).toContain('异常待办')
    expect(page).toContain('安全重放')
  })

  it('adds scheduling metrics without a parallel palette', () => {
    const dashboard = readFileSync(resolve(process.cwd(), 'app/components/OperationsDashboard.vue'), 'utf8')
    expect(dashboard).toContain('FETCH_BACKLOG_AGE_SECONDS')
    expect(dashboard).not.toMatch(/#[0-9a-f]{3,8}/i)
  })

  it('lets an authorized source administrator create or update the database schedule', () => {
    const detail = readFileSync(resolve(process.cwd(), 'app/pages/admin/sources/[id].vue'), 'utf8')
    expect(detail).toContain('/schedule')
    expect(detail).toContain('expected_version')
    expect(detail).toContain('Idempotency-Key')
    expect(detail).toContain('scheduleForm.status')
    expect(detail).toContain('dailyByteBudget')
  })
})
