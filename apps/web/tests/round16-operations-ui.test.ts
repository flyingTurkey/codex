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

  it('offers only authorized, step-up protected circuit repair with no automatic retry', () => {
    const detail = readFileSync(resolve(process.cwd(), 'app/pages/admin/sources/[id].vue'), 'utf8')

    expect(detail).toContain('/schedule/repair')
    expect(detail).toContain('async function repairSchedule')
    expect(detail).toContain("method: 'POST'")
    expect(detail).toContain("'Idempotency-Key': crypto.randomUUID()")
    expect(detail).toContain("'X-SRBG-Local-Step-Up': 'true'")
    expect(detail).toContain('retry: 0')
    expect(detail).toContain("role === 'source_admin' || role === 'platform_admin'")
    expect(detail).toContain('body: { reason }')
    expect(detail).toContain('scheduleForm.reason.trim().length < 10')
    expect(detail).toContain('v-if="canRepairSchedule"')
    expect(detail).toContain('await refreshSchedule()')
    expect(detail).toContain('熔断修复失败：')
    expect(detail).toContain('v-if="scheduleCommandError"')
    expect(detail).not.toContain('data-action="REVOKE"')
  })
})
