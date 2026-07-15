import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const lowAltitudeItem = {
  activity_at: '2026-07-15T04:00:00Z',
  content_type: 'LOW_ALTITUDE_EQUIPMENT',
  domain: 'DIGITAL',
  evidence_count: 2,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2026-07-15T04:05:00Z',
  id: '019b0000-0000-7000-8000-000000007201',
  original_url: 'https://enterprise.dji.com/example',
  publication_revision_id: '019b0000-0000-7000-8000-000000007202',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: '大疆行业应用',
  source_published_at: '2026-05-01T00:00:00Z',
  source_role: '厂商一手来源',
  title: '经纬 M350 RTK 无人机平台',
  type_summary: {
    evidence_level: 'VENDOR_CLAIM_ONLY',
    kind: 'LOW_ALTITUDE_EQUIPMENT',
    model_no: 'M350 RTK',
    payload_types: ['可见光相机'],
    permit_status: 'UNKNOWN',
    platform_type: '多旋翼无人机',
    product_kind: 'LOW_ALTITUDE_EQUIPMENT',
    product_name: '经纬 350 RTK',
    promotional_claim_count: 3,
    vendor_name: '深圳市大疆创新科技有限公司',
    verified_capability_count: 0,
    version: 'V1.0',
  },
} as unknown as ItemSummary

describe('round 07 technology product UI', () => {
  it('renders a low-altitude product through the shared card with neutral claims and permit status', () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const wrapper = mount(IntelligenceCard, { props: { item: lowAltitudeItem } })

    expect(wrapper.text()).toContain('低空设备')
    expect(wrapper.text()).toContain('深圳市大疆创新科技有限公司')
    expect(wrapper.text()).toContain('经纬 350 RTK')
    expect(wrapper.text()).toContain('M350 RTK / V1.0')
    expect(wrapper.text()).toContain('厂商声明 3 项')
    expect(wrapper.text()).toContain('独立验证 0 项')
    expect(wrapper.text()).toContain('许可状态未知')
    expect(wrapper.get('[data-testid="product-vendor-claims"]').classes()).toContain('intelligence-card__publisher-claim')
    expect(wrapper.text()).not.toContain('适用于四川路桥采购')
  })

  it('adds four product types and shared filters to the existing digital page', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/digital.vue'), 'utf8')
    const panel = readFileSync(resolve(process.cwd(), 'app/components/FilterPanel.vue'), 'utf8')

    for (const kind of ['SOFTWARE_PRODUCT', 'IOT_PRODUCT', 'LOW_ALTITUDE_EQUIPMENT', 'AI_EQUIPMENT']) {
      expect(page).toContain(`value: '${kind}'`)
    }
    expect(page).toContain('show-product-filters')
    expect(panel).toContain('产品类型')
    expect(panel).toContain('证据等级')
    expect(panel).toContain('部署方式')
  })

  it('shows the three required product detail regions and fixed low-altitude boundary', () => {
    const page = readFileSync(resolve(process.cwd(), 'app/pages/events/[id].vue'), 'utf8')

    expect(page).toContain('<h2>产品能力</h2>')
    expect(page).toContain('<h2>工程证据</h2>')
    expect(page).toContain('<h2>许可与限制</h2>')
    expect(page).toContain('产品发布不代表空域、适航、飞手和项目许可。')
    expect(page).toContain('仅供技术调研，不构成采购建议')
    expect(page).not.toContain('适用于四川路桥采购')
  })

  it('provides a reviewer-only manual normalization entry through the existing review workbench', () => {
    const review = readFileSync(resolve(process.cwd(), 'app/pages/admin/review/index.vue'), 'utf8')

    expect(review).toContain('/api/v1/admin/product-normalization-candidates')
    expect(review).toContain('MERGE_ALIAS')
    expect(review).toContain('LINK_AS_NEW_VERSION')
    expect(review).toContain('KEEP_DISTINCT')
    expect(review).toContain('型号与版本归一候选')
  })
})
