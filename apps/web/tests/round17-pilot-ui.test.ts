import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('round 17 pilot operations UI', () => {
  it('provides one internal pilot workspace without exposing source bodies', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/pilot.vue'), 'utf8')
    expect(page).toContain('/api/v1/admin/pilot-windows')
    expect(page).toContain('/sources/${sourceCode}/resume')
    expect(page).toContain('/complete')
    expect(page).toContain('/api/v1/admin/operator-work-sessions')
    expect(page).toContain('/api/v1/admin/operator-tasks')
    expect(page).toContain('168')
    expect(page).toContain('BLOCKED')
    expect(page).not.toContain('raw_body')
    expect(page).not.toContain(':disabled="busy || blocked"')
  })

  it('binds operator work to the current running window and renews it every minute', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/pilot.vue'), 'utf8')
    expect(page).toContain("window.state === 'RUNNING'")
    expect(page).toContain('task_id: task.id')
    expect(page).toContain('/heartbeat')
    expect(page).toContain('expected_version: session.version')
    expect(page).toContain('60_000')
    expect(page).toContain('onBeforeUnmount(clearWorkHeartbeat)')
    expect(page).toContain('必须使用非本地企业OIDC')
    expect(page).toContain('/corrections')
    expect(page).toContain('reason_code: correctionReason.value')
    expect(page).not.toContain('workNotes')
  })

  it('separates LEO task control from yinzi task execution', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/pilot.vue'), 'utf8')
    expect(page).toContain('/api/v1/admin/operator-tasks')
    expect(page).toContain('/complete')
    expect(page).toContain("task.status === 'PENDING'")
    expect(page).toContain("task.status === 'IN_PROGRESS'")
    expect(page).toContain('source_id: operatorTaskSourceId.value.trim() || null')
    expect(page).not.toContain('operatorTaskNotes')
    expect(page).not.toContain('sourceUrl')
  })

  it('labels the hardcoded roster as a candidate list pending external LEO approval', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/pilot.vue'), 'utf8')
    expect(page).toContain('candidateSourceCodesPendingLeoApproval')
    expect(page).toContain('候选清单，仍待LEO外部审批')
    expect(page).toContain('候选窗口 168 小时（待LEO确认）')
    expect(page).not.toContain('固定窗口 168 小时')
    expect(page).not.toContain("latestWindow.state !== 'RUNNING'")
    expect(page).not.toContain('approvedSourceCodes')
  })

  it('provides a blind gold task workspace and keeps arbitration separate', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/admin/gold.vue'), 'utf8')
    expect(page).toContain('/api/v1/admin/gold-tasks')
    expect(page).toContain('/annotations')
    expect(page).toContain('/arbitrations')
    expect(page).toContain('option.evidence_ids')
    expect(page).toContain('option.related_sample_refs')
    expect(page).toContain('Evidence 稳定ID')
    expect(page).toContain('关联样本稳定引用')
    expect(page).not.toContain('peer_annotations')
    expect(page).not.toContain('raw_body')
    expect(page).not.toContain('body_text')
  })

  it('makes the two workspaces visible only to their bounded admin roles', () => {
    const navigation = readFileSync(resolve(process.cwd(), 'app/navigation.ts'), 'utf8')
    expect(navigation).toContain("to: '/admin/pilot'")
    expect(navigation).toContain("to: '/admin/gold'")
    expect(navigation).toContain("'gold_annotator'")
    expect(navigation).toContain("'gold_arbitrator'")
  })
})
