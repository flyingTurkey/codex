import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('PERS-08 reversible automatic relationships', () => {
  it('offers owner corrections on the event detail page', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/events/[id].vue'), 'utf8')
    const component = readFileSync(resolve(process.cwd(), 'app/components/AutomaticRelationships.vue'), 'utf8')
    expect(page).toContain('AutomaticRelationships')
    expect(component).toContain('撤销关系')
    expect(component).toContain('拆分事件')
    expect(component).toContain('保持独立')
    expect(component).toContain('修正型号关系')
    expect(component).toContain('/relationship-corrections')
  })

  it('removes relationship and model decisions from review workbenches', () => {
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/review/index.vue'))).toBe(false)
    expect(existsSync(resolve(process.cwd(), 'app/pages/admin/clusters.vue'))).toBe(false)
  })
})
