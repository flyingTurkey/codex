import { mount } from '@vue/test-utils'
import type { ItemSummary } from '@srbg/contracts'
import type { Component } from 'vue'
import { describe, expect, it } from 'vitest'

const componentModules = import.meta.glob<{ default: Component }>('../app/components/*.vue', {
  eager: true,
})

const eventId = '019b0000-0000-7000-8000-000000004001'
const caseItem = {
  activity_at: '2025-01-22T04:00:00Z',
  content_type: 'SAFETY_CASE',
  domain: 'SAFETY',
  evidence_count: 6,
  evidence_status: 'VERIFIED',
  first_discovered_at: '2025-01-22T04:05:00Z',
  id: '019b0000-0000-7000-8000-000000004002',
  original_url: 'https://yjgl.gd.gov.cn/example.html',
  publication_revision_id: '019b0000-0000-7000-8000-000000004003',
  publication_status: 'PUBLISHED',
  review_status: 'APPROVED',
  source_name: '广东省应急管理厅',
  source_published_at: '2025-01-22T04:00:00Z',
  source_role: '官方一手来源',
  title: '梅大高速茶阳路段“5·1”塌方灾害调查报告',
  type_summary: {
    conflicted_fields: ['DEATH_COUNT'],
    engineering_type: 'EXPRESSWAY',
    event_id: eventId,
    hazard_type: 'ROADBED_COLLAPSE',
    incident_status: 'UNDER_INVESTIGATION',
    kind: 'SAFETY_CASE',
    occurred_at: '2024-05-01T01:57:00+08:00',
    region: '广东省',
    report_stage: 'FOLLOW_UP_REPORT',
  },
} as unknown as ItemSummary

describe('round 04 safety case UI', () => {
  it('offers an accessible all/regulation/case filter without cloning the feed', async () => {
    const FilterPanel = componentModules['../app/components/FilterPanel.vue']?.default
    expect(FilterPanel).toBeDefined()
    if (!FilterPanel) return

    const wrapper = mount(FilterPanel, {
      props: {
        contentType: 'all',
        contentTypeOptions: [
          { label: '全部', value: 'all' },
          { label: '规定', value: 'SAFETY_REGULATION' },
          { label: '案例', value: 'SAFETY_CASE' },
        ],
        showDomain: false,
      },
    })

    const group = wrapper.get('[role="group"][aria-label="安全内容类型"]')
    expect(group.findAll('button')).toHaveLength(3)
    expect(group.get('[data-content-type="all"]').attributes('aria-pressed')).toBe('true')

    await group.get('[data-content-type="SAFETY_CASE"]').trigger('click')
    expect(wrapper.emitted('update:contentType')).toEqual([['SAFETY_CASE']])
  })

  it('forwards the canonical filter selection from IntelligenceFeedPage', async () => {
    const IntelligenceFeedPage = componentModules['../app/components/IntelligenceFeedPage.vue']?.default
    expect(IntelligenceFeedPage).toBeDefined()
    if (!IntelligenceFeedPage) return

    const wrapper = mount(IntelligenceFeedPage, {
      props: {
        contentType: 'all',
        contentTypeOptions: [
          { label: '全部', value: 'all' },
          { label: '规定', value: 'SAFETY_REGULATION' },
          { label: '案例', value: 'SAFETY_CASE' },
        ],
        emptyTitle: '暂无内容',
        showDomainFilter: false,
        showFilters: true,
        title: '安全情报',
      },
    })

    await wrapper.get('[data-content-type="SAFETY_CASE"]').trigger('click')
    expect(wrapper.emitted('update:contentType')).toEqual([['SAFETY_CASE']])
    expect(wrapper.emitted('content-type-change')).toEqual([['SAFETY_CASE']])
  })

  it('renders the SafetyCase TypeSummary with text-and-icon lifecycle and conflict states', () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const wrapper = mount(IntelligenceCard, { props: { item: caseItem } })

    expect(wrapper.text()).toContain('安全案例')
    expect(wrapper.get('[data-testid="case-status"]').text()).toContain('调查中')
    expect(wrapper.get('[data-testid="case-status"]').find('svg').exists()).toBe(true)
    expect(wrapper.get('[data-testid="case-conflict"]').text()).toContain('冲突待核实')
    expect(wrapper.get('[data-testid="case-conflict"]').find('svg').exists()).toBe(true)
    expect(wrapper.text()).toContain('高速公路')
    expect(wrapper.text()).toContain('路基塌陷')
    expect(wrapper.text()).not.toContain('EXPRESSWAY')
    expect(wrapper.text()).not.toContain('ROADBED_COLLAPSE')
    expect(wrapper.text()).toContain('广东省')
    expect(wrapper.get('[data-testid="event-link"]').attributes('href')).toBe(`/events/${eventId}`)
  })

  it('keeps an R3 case restricted and makes withdrawal explicit without sensitive placeholders', () => {
    const IntelligenceCard = componentModules['../app/components/IntelligenceCard.vue']?.default
    expect(IntelligenceCard).toBeDefined()
    if (!IntelligenceCard) return

    const restricted = mount(IntelligenceCard, {
      props: {
        item: {
          ...caseItem,
          evidence_count: undefined,
          evidence_status: undefined,
          publication_revision_id: null,
          publication_status: 'PENDING_REVIEW',
          review_status: 'PENDING',
          source_role: undefined,
          type_summary: { kind: 'SAFETY_CASE' },
        } as unknown as ItemSummary,
      },
    })
    expect(restricted.text()).toContain('待人工审核')
    expect(restricted.text()).not.toMatch(/死亡人数|受伤人数|直接经济损失|正式原因|责任认定/)
    expect(restricted.find('[data-testid="evidence-trigger"]').exists()).toBe(false)

    const withdrawn = mount(IntelligenceCard, {
      props: {
        item: {
          ...caseItem,
          document_states: ['WITHDRAWN'],
          publication_status: 'WITHDRAWN',
          type_summary: {
            event_id: eventId,
            incident_status: 'WITHDRAWN',
            kind: 'SAFETY_CASE',
            report_stage: 'FOLLOW_UP_REPORT',
          },
        } as unknown as ItemSummary,
      },
    })
    expect(withdrawn.text()).toContain('已撤回')
    expect(withdrawn.get('[data-testid="case-status"]').find('svg').exists()).toBe(true)
    expect(withdrawn.find('.intelligence-card__facts.is-safety-case').exists()).toBe(false)
    expect(withdrawn.text()).toContain('查看历史证据')
  })

  it('keeps confirmed facts evidence-linked and never exposes an unverified raw value', async () => {
    const FactList = componentModules['../app/components/FactList.vue']?.default
    expect(FactList, 'FactList.vue should exist').toBeDefined()
    if (!FactList) return

    const confirmed = mount(FactList, {
      props: {
        facts: [{
          claim_id: '019b0000-0000-7000-8000-000000004010',
          evidence_ids: ['019b0000-0000-7000-8000-000000004011'],
          field: 'DEATH_COUNT',
          label: '死亡人数',
          source_item_id: caseItem.id,
          status: 'CONFIRMED',
          reviewed_at: '2025-01-22T08:00:00Z',
          unit: '人',
          value: 52,
        }],
        title: '已确认事实',
        variant: 'confirmed',
      },
    })

    expect(confirmed.text()).toContain('死亡人数')
    expect(confirmed.text()).toContain('52 人')
    await confirmed.get('[data-testid="fact-evidence-trigger"]').trigger('click')
    expect(confirmed.emitted('evidence')).toEqual([[
      ['019b0000-0000-7000-8000-000000004011'],
    ]])

    const unverified = mount(FactList, {
      props: {
        facts: [{
          claim_id: '019b0000-0000-7000-8000-000000004012',
          conflict_id: '019b0000-0000-7000-8000-000000004013',
          display_value: '待核实',
          evidence_ids: [],
          field: 'LOSS_AMOUNT_MINOR',
          label: '直接经济损失',
          reason: '不同阶段正式通报数值不一致',
          source_item_id: caseItem.id,
          status: 'CONFLICTING',
          unit: null,
          value: null,
        }],
        title: '待核实',
        variant: 'unverified',
      },
    })

    expect(unverified.text()).toContain('待核实')
    expect(unverified.text()).toContain('不同阶段正式通报数值不一致')
    expect(unverified.find('[data-testid="fact-evidence-trigger"]').exists()).toBe(false)
    expect(unverified.text()).not.toContain('9800 万元')
  })

  it('renders only published Event evidence references and their associated claims', () => {
    const EventEvidenceDrawer = componentModules['../app/components/EventEvidenceDrawer.vue']?.default
    expect(EventEvidenceDrawer, 'EventEvidenceDrawer.vue should exist').toBeDefined()
    if (!EventEvidenceDrawer) return

    const wrapper = mount(EventEvidenceDrawer, {
      props: {
        claims: [{
          claim_id: '019b0000-0000-7000-8000-000000004010',
          evidence_ids: ['019b0000-0000-7000-8000-000000004011'],
          field_name: 'OFFICIAL_DIRECT_CAUSES',
          value: '长时间持续性降水与多种因素叠加耦合作用',
        }],
        evidence: [{
          content_sha256: 'a'.repeat(64),
          evidence_id: '019b0000-0000-7000-8000-000000004011',
          locator: 'html-p-0042',
        }],
        open: true,
      },
    })

    expect(wrapper.text()).toContain('html-p-0042')
    expect(wrapper.text()).toContain('a'.repeat(64))
    expect(wrapper.text()).toContain('OFFICIAL_DIRECT_CAUSES')
    expect(wrapper.text()).toContain('长时间持续性降水与多种因素叠加耦合作用')
    expect(wrapper.text()).not.toContain('调查报告认定，')
    expect(wrapper.text()).not.toContain('https://')
  })

  it('preserves every lifecycle stage in order and expresses state with text and icons', () => {
    const EventTimeline = componentModules['../app/components/EventTimeline.vue']?.default
    expect(EventTimeline, 'EventTimeline.vue should exist').toBeDefined()
    if (!EventTimeline) return

    const stages = [
      ['INITIAL_REPORT', 'INITIAL_OFFICIAL_REPORT', null, '初报'],
      ['FOLLOW_UP_REPORT', 'UNDER_INVESTIGATION', 'FOLLOW_UP', '续报'],
      ['FINAL_INVESTIGATION', 'FINAL_INVESTIGATION_REPORT', 'INVESTIGATES', '正式调查'],
      ['ENFORCEMENT', 'ENFORCEMENT_DECISION', 'PENALIZES', '处罚问责'],
      ['RECTIFICATION', 'RECTIFICATION_FOLLOW_UP', 'RECTIFIES', '整改评估'],
    ] as const
    const items = stages.map(([report_stage, incident_status, relation_type, title], index) => ({
      document_states: [],
      evidence_count: index + 1,
      incident_status,
      item_id: `019b0000-0000-7000-8000-00000000410${index}`,
      original_url: `https://example.invalid/stage-${index}`,
      publication_revision_id: `019b0000-0000-7000-8000-00000000420${index}`,
      relation_type,
      report_stage,
      review_status: 'APPROVED',
      source_name: '官方来源',
      source_published_at: `2025-01-${String(index + 1).padStart(2, '0')}T00:00:00Z`,
      title,
    }))
    const wrapper = mount(EventTimeline, { props: { items } })

    expect(wrapper.findAll('[data-testid="event-stage"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('初报')
    expect(wrapper.text()).toContain('续报')
    expect(wrapper.text()).toContain('正式调查')
    expect(wrapper.text()).toContain('处罚问责')
    expect(wrapper.text()).toContain('整改评估')
    expect(wrapper.findAll('[data-testid="event-stage"] svg')).toHaveLength(5)
  })

  it('keeps correction and withdrawal relation audit visible on the shared event timeline', () => {
    const EventTimeline = componentModules['../app/components/EventTimeline.vue']?.default
    expect(EventTimeline).toBeDefined()
    if (!EventTimeline) return

    const wrapper = mount(EventTimeline, {
      props: {
        items: [{
          document_states: ['WITHDRAWN'],
          evidence_count: 1,
          incident_status: 'CORRECTED',
          item_id: '019b0000-0000-7000-8000-000000004300',
          original_url: 'https://example.invalid/correction',
          publication_revision_id: '019b0000-0000-7000-8000-000000004301',
          relation_type: 'CORRECTS',
          report_stage: 'FOLLOW_UP_REPORT',
          review_status: 'APPROVED',
          source_name: '官方来源',
          source_published_at: '2025-01-23T00:00:00Z',
          title: '更正通报',
        }],
      },
    })

    expect(wrapper.text()).toContain('更正前序材料')
    expect(wrapper.text()).toContain('已撤回')
  })

  it('renders every audited event relation separately so a correction cannot be hidden by stage priority', () => {
    const EventRelations = componentModules['../app/components/EventRelations.vue']?.default
    expect(EventRelations, 'EventRelations.vue should exist').toBeDefined()
    if (!EventRelations) return

    const items = [
      {
        incident_status: 'INITIAL_OFFICIAL_REPORT',
        item_id: '019b0000-0000-7000-8000-000000004100',
        original_url: 'https://example.invalid/initial',
        publication_revision_id: null,
        relation_type: null,
        report_stage: 'INITIAL_REPORT',
        review_status: 'APPROVED',
        source_name: '官方来源',
        source_published_at: '2024-05-01T12:00:00Z',
        title: '事故初报',
      },
      {
        incident_status: 'UNDER_INVESTIGATION',
        item_id: '019b0000-0000-7000-8000-000000004101',
        original_url: 'https://example.invalid/follow-up',
        publication_revision_id: null,
        relation_type: 'FOLLOW_UP',
        report_stage: 'FOLLOW_UP_REPORT',
        review_status: 'APPROVED',
        source_name: '官方来源',
        source_published_at: '2024-05-02T04:00:00Z',
        title: '救援续报',
      },
    ]
    const reviewerId = '019b0000-0000-7000-8000-000000004799'
    const relations = ['FOLLOW_UP', 'INVESTIGATES', 'PENALIZES', 'RECTIFIES', 'CORRECTS'].map(
      (relation_type, index) => ({
        event_id: eventId,
        from_item_id: '019b0000-0000-7000-8000-000000004101',
        id: `019b0000-0000-7000-8000-00000000450${index}`,
        relation_type,
        reviewed_at: '2025-01-22T08:00:00Z',
        reviewed_by: reviewerId,
        to_item_id: '019b0000-0000-7000-8000-000000004100',
      }),
    )
    const wrapper = mount(EventRelations, { props: { items, relations } })

    expect(wrapper.findAll('[data-testid="event-relation"]')).toHaveLength(5)
    expect(wrapper.text()).toContain('已审核事件关系与更正记录')
    expect(wrapper.text()).toContain('更正前序材料')
    expect(wrapper.text()).toContain('救援续报')
    expect(wrapper.text()).toContain('事故初报')
    expect(wrapper.text()).toContain('2025年1月22日 16:00')
    expect(wrapper.findAll('[data-testid="event-relation"] svg')).toHaveLength(5)
    expect(wrapper.text()).not.toContain(reviewerId)
    expect(wrapper.text()).not.toContain('019b0000-0000-7000-8000-00000000450')
  })
})
