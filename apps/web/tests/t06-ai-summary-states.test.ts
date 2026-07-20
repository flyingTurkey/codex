import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('T06 AI summary state projection', () => {
  it('renders server-projected deterministic state copy', () => {
    const reader = readFileSync(resolve(process.cwd(), 'app/pages/events/[id].vue'), 'utf8')

    expect(reader).toContain('full.ai_summary.status_message')
    expect(reader).not.toContain('AI 总结暂不可用；已通过门禁的原文摘录仍可阅读，系统将在恢复后补齐。')
  })
})
