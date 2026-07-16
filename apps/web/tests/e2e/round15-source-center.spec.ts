import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

const sourceId = '019b0000-0000-7000-8000-000000001501'
const policyId = '019b0000-0000-7000-8000-000000001503'
const connectorConfigId = '019b0000-0000-7000-8000-000000001504'
const fixtureTrialId = '019b0000-0000-7000-8000-000000001505'
const liveTrialId = '019b0000-0000-7000-8000-000000001506'
const pendingFixtureTrialId = '019b0000-0000-7000-8000-000000001517'

const sourceSummary = {
  authority_level: 'A1',
  // Client-only ACTIVE projection after a LIVE_TRIAL; it approves no real source in round 15.
  // V1 state/enabled deliberately remain non-authoritative compatibility facts.
  available_actions: ['PAUSE'],
  base_url: 'https://bridge.example.test',
  channel: 'BOTH',
  content_domains: ['SAFETY_REGULATION', 'DIGITAL_TRANSFORMATION_CASE'],
  country_codes: ['CN'],
  created_at: '2026-07-16T01:00:00Z',
  declared_roles: ['OFFICIAL_PRIMARY'],
  effective_active: true,
  enabled: false,
  fixture_count: 6,
  governance_owner_id: '019b0000-0000-7000-8000-000000001599',
  id: sourceId,
  industries: ['BRIDGE'],
  language_tags: ['zh-CN'],
  lifecycle_state: 'ACTIVE',
  name: '[TEST/PROJECTION] 桥梁安全状态样本',
  priority: 'P1',
  region_codes: ['CN-SC'],
  registry_code: 'SRC-015',
  runtime_authorization: 'PRODUCTION',
  source_independence: {
    assessed_at: '2026-07-16T00:30:00Z',
    evidence_refs: ['fixture://independence-assessment'],
    level: 'EDITORIALLY_INDEPENDENT',
    reason_codes: ['TEST_PROJECTION'],
    rule_version: '1.0.0',
  },
  source_type: 'government',
  state: 'CANDIDATE',
}

const sourceDetail = {
  ...sourceSummary,
  collection_method: 'declarative_connector',
  current_connector_config_version_id: connectorConfigId,
  current_policy_version_id: policyId,
  current_trial_run_id: liveTrialId,
  eligibility: {
    effective_active: true,
    fixture_count: 6,
    missing_reasons: [],
    onboarding_policy_matches: true,
    onboarding_valid: true,
    policy_valid: true,
    required_checks_complete: true,
    required_fixture_count: 0,
  },
  owner: 'legacy-owner-preserved',
  poll_interval_minutes: 30,
  source_authority: {
    assessed_at: '2026-07-16T00:30:00Z',
    evidence_refs: ['fixture://authority-assessment'],
    level: 'A1',
    reason_codes: ['TEST_PROJECTION'],
    rule_version: '2.0.0',
  },
}

const pausedSourceDetail = {
  ...sourceDetail,
  available_actions: ['RESUME', 'RETIRE'],
  effective_active: false,
  lifecycle_state: 'PAUSED',
  runtime_authorization: 'DENIED',
}

const trialSource = {
  ...sourceSummary,
  available_actions: ['RETIRE'],
  effective_active: false,
  enabled: false,
  id: '019b0000-0000-7000-8000-000000001502',
  lifecycle_state: 'TRIAL',
  name: '[TEST/PROJECTION] 隧道事故调查候选来源',
  runtime_authorization: 'TRIAL_ONLY',
  state: 'FIXTURE_TEST',
}

const pendingFixtureSourceDetail = {
  ...sourceDetail,
  ...trialSource,
  available_actions: ['START_FIXTURE_TRIAL', 'START_LIVE_TRIAL', 'RETIRE'],
  current_connector_config_version_id: connectorConfigId,
  current_policy_version_id: policyId,
  current_trial_run_id: pendingFixtureTrialId,
  effective_active: false,
  runtime_authorization: 'TRIAL_ONLY',
}

const pendingFixtureTrial = {
  completed_at: null,
  connector_config_version_id: connectorConfigId,
  created_at: '2026-07-16T06:10:00Z',
  id: pendingFixtureTrialId,
  kind: 'FIXTURE_REPLAY',
  policy_version_id: policyId,
  quality_summary: null,
  requested_by: '019b0000-0000-7000-8000-000000009015',
  source_id: trialSource.id,
  started_at: '2026-07-16T06:10:00Z',
  status: 'PENDING',
}

async function mockIdentity(page: Page, roles: string[] = ['source_admin']): Promise<void> {
  await page.route('**/api/v1/me', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      display_name: roles.includes('auditor') ? '只读审计员' : '来源管理员',
      local_identity: true,
      roles,
      user_id: '019b0000-0000-7000-8000-000000009015',
    }),
  }))
}

async function openSourceCenter(page: Page): Promise<void> {
  await page.goto('/')
  await expect(page.locator('.srbg-app-shell')).toHaveAttribute('aria-busy', 'false', {
    timeout: 20_000,
  })
  const mobileNavigation = page.getByRole('button', { name: '打开导航' })
  if (await mobileNavigation.isVisible()) await mobileNavigation.click()
  await page.getByRole('link', { name: '管理入口', exact: true }).click()
  await expect(page.getByRole('heading', { level: 1, name: '来源中心 V2' })).toBeVisible()
}

async function mockSourceCenter(page: Page): Promise<void> {
  await mockIdentity(page)
  await page.route('**/api/v1/feed**', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      fingerprint: 'sha256:round15-source-center',
      freshness: 'fresh',
      generated_at: '2026-07-16T06:00:00Z',
      items: [],
      next_cursor: null,
      notices: [],
    }),
  }))
  await page.route('**/api/v1/admin/sources', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify([sourceSummary, trialSource]),
      })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(sourceDetail), status: 201 })
  })
  await page.route(`**/api/v1/admin/sources/${sourceId}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(sourceDetail),
  }))
  await page.route(`**/api/v1/admin/sources/${sourceId}/policy-versions`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      {
        created_at: '2026-07-16T02:00:00Z',
        decided_by: '019b0000-0000-7000-8000-000000001598',
        document: {
          automatic_publication: 'DISABLED',
          copyright_review: {
            checked_at: '2026-07-15T10:00:00Z',
            evidence_sha256: 'c'.repeat(64),
            evidence_url: 'https://bridge.example.test/copyright',
            result: 'ALLOWED',
          },
          display_policy: 'METADATA_EXCERPT_LINK',
          download_policy: 'ORIGINAL_LINK_ONLY',
          fetch: {
            allowed_domains: ['bridge.example.test'],
            minimum_interval_seconds: 900,
            rate_limit_per_minute: 4,
            user_agent: 'SRBG-Source-Governance/1.0',
          },
          legal_hold_policy: 'SUPPORTED',
          policy_version: '2.0.0',
          reason: 'E2E 固定投影的合规策略，不代表真实来源获批',
          retention: { delete_after_retention: false, retention_days: 3650 },
          robots_review: {
            checked_at: '2026-07-15T10:00:00Z',
            evidence_sha256: 'a'.repeat(64),
            evidence_url: 'https://bridge.example.test/robots.txt',
            result: 'ALLOWED',
          },
          slo: {
            applicability: 'APPLICABLE',
            authorization_confirmed: true,
            target_minutes: 15,
            technical_conditions_confirmed: true,
          },
          schema_version: '2.0.0',
          storage_policy: 'RAW_EVIDENCE_ALLOWED',
          terms_review: {
            checked_at: '2026-07-15T10:00:00Z',
            evidence_sha256: 'b'.repeat(64),
            evidence_url: 'https://bridge.example.test/terms',
            result: 'ALLOWED',
          },
          valid_from: '2026-07-16T02:00:00Z',
          valid_until: '2026-10-16T02:00:00Z',
        },
        document_sha256: 'd'.repeat(64),
        id: policyId,
        policy_version: '2.0.0',
        schema_version: '2.0.0',
        source_id: sourceId,
        status: 'APPROVED',
        submitted_by: '019b0000-0000-7000-8000-000000001597',
        valid_from: '2026-07-16T02:00:00Z',
        valid_until: '2026-10-16T02:00:00Z',
      },
    ]),
  }))
  await page.route(`**/api/v1/admin/sources/${sourceId}/connector-config-versions`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      {
        allowed_hosts: ['bridge.example.test'],
        config: {
          allowed_hosts: ['bridge.example.test'],
          feed_url: 'https://bridge.example.test/feed.xml',
        },
        config_sha256: 'e'.repeat(64),
        connector_type: 'RSS_ATOM',
        created_at: '2026-07-16T02:10:00Z',
        created_by: '019b0000-0000-7000-8000-000000001596',
        credential_configured: true,
        definition_version: '1.0.0',
        id: connectorConfigId,
        policy_version_id: policyId,
        source_id: sourceId,
        validation_status: 'VALID',
        version_number: 2,
      },
    ]),
  }))
  await page.route('**/api/v1/admin/connector-definitions', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      { capabilities: ['DISCOVERY', 'FETCH'], connector_type: 'RSS_ATOM', definition_version: '1.0.0', executor_key: 'builtin:rss_atom:v1', id: '019b0000-0000-7000-8000-000000001510', schema_document: {}, schema_sha256: '4691b104889eeb16f6cb006d8284b6a8f5bb4b0c58ea2fd331ddf63f7eb2830d', schema_version: '2020-12' },
      { capabilities: ['DISCOVERY', 'FETCH'], connector_type: 'JSON_API', definition_version: '1.0.0', executor_key: 'builtin:json_api:v1', id: '019b0000-0000-7000-8000-000000001511', schema_document: {}, schema_sha256: '73b72a68d11b0da0698871e34f80534b1386d6ce7500a27b57f3c3792ed38447', schema_version: '2020-12' },
      { capabilities: ['DISCOVERY', 'FETCH'], connector_type: 'SITEMAP', definition_version: '1.0.0', executor_key: 'builtin:sitemap:v1', id: '019b0000-0000-7000-8000-000000001512', schema_document: {}, schema_sha256: '7965a06972afb19af66f82ccbb5f21b7f4e88be33d64cc3548cff9cb62921ae5', schema_version: '2020-12' },
      { capabilities: ['DISCOVERY', 'FETCH'], connector_type: 'LIST_DETAIL', definition_version: '1.0.0', executor_key: 'builtin:list_detail:v1', id: '019b0000-0000-7000-8000-000000001513', schema_document: {}, schema_sha256: 'd6c892a10eb61d372e44f1156f48676fdd549027dcd91b20aaff4e1f01938ef6', schema_version: '2020-12' },
      { capabilities: ['DIRECT_FETCH', 'PDF'], connector_type: 'DIRECT_PDF', definition_version: '1.0.0', executor_key: 'builtin:direct_pdf:v1', id: '019b0000-0000-7000-8000-000000001514', schema_document: {}, schema_sha256: 'daa3e6ded77fd467da20f21961b84177eb6b84a2bd5e60adf45ab110012883b8', schema_version: '2020-12' },
      { capabilities: ['MANUAL_URL', 'MANUAL_FILE'], connector_type: 'MANUAL_IMPORT', definition_version: '1.0.0', executor_key: 'builtin:manual_import:v1', id: '019b0000-0000-7000-8000-000000001515', schema_document: {}, schema_sha256: '2abc649e1f15fbb452e27f452fca1eb27e5538bac2e7c07eaab42bd6345c860d', schema_version: '2020-12' },
    ]),
  }))
  await page.route(`**/api/v1/admin/sources/${sourceId}/trial-runs`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      {
        completed_at: '2026-07-16T03:05:00Z',
        connector_config_version_id: connectorConfigId,
        created_at: '2026-07-16T03:00:00Z',
        id: fixtureTrialId,
        kind: 'FIXTURE_REPLAY',
        policy_version_id: policyId,
        quality_summary: {
          parse_failed_count: 0,
          raw_count: 6,
          ready_count: 6,
          ready_ratio_bps: 10_000,
          security_failed_count: 0,
          rejected_raw_attempt_count: 0,
        },
        requested_by: '019b0000-0000-7000-8000-000000001596',
        source_id: sourceId,
        started_at: '2026-07-16T03:00:00Z',
        status: 'SUCCEEDED',
      },
      {
        completed_at: '2026-07-16T04:05:00Z',
        connector_config_version_id: connectorConfigId,
        created_at: '2026-07-16T04:00:00Z',
        id: liveTrialId,
        kind: 'LIVE_TRIAL',
        policy_version_id: policyId,
        quality_summary: {
          parse_failed_count: 1,
          raw_count: 2,
          ready_count: 1,
          ready_ratio_bps: 5_000,
          security_failed_count: 1,
          rejected_raw_attempt_count: 1,
        },
        requested_by: '019b0000-0000-7000-8000-000000001599',
        source_id: sourceId,
        started_at: '2026-07-16T04:00:00Z',
        status: 'SUCCEEDED',
      },
    ]),
  }))
  await page.route(`**/api/v1/admin/sources/${sourceId}/lifecycle-events`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      {
        actor_id: '019b0000-0000-7000-8000-000000001599',
        created_at: '2026-07-16T05:00:00Z',
        action: 'APPROVE_PRODUCTION',
        from_state: 'TRIAL',
        governance_decision_id: '019b0000-0000-7000-8000-000000001507',
        id: '019b0000-0000-7000-8000-000000001508',
        policy_version_id: policyId,
        reason_code: 'PRODUCTION_APPROVED',
        reason: '审批、策略与真实试运行均有效',
        source_id: sourceId,
        to_state: 'ACTIVE',
      },
    ]),
  }))
  await page.route(`**/api/v1/admin/sources/${sourceId}/audit-events`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([
      {
        actor_id: '019b0000-0000-7000-8000-000000009015',
        created_at: '2026-07-16T05:10:00Z',
        event_type: 'SOURCE_CONNECTOR_CONFIG_SAVED',
        id: '019b0000-0000-7000-8000-000000001509',
        reason: '保存经严格 Schema 校验的连接器配置版本',
        request_id: 'req-round15-config-save',
      },
    ]),
  }))
  await page.route('**/api/v1/admin/source-coverage', route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({
      cells: [
        {
          active_count: 1,
          candidate_count: 2,
          content_domain: 'SAFETY_REGULATION',
          gap: false,
          industry: 'BRIDGE',
          language: 'zh-CN',
          region: 'CN-SC',
          source_type: 'government',
          trial_count: 1,
        },
        {
          active_count: 0,
          candidate_count: 1,
          content_domain: 'ACCIDENT_INVESTIGATION',
          gap: true,
          industry: 'TUNNEL',
          language: 'zh-CN',
          region: 'CN-SC',
          source_type: 'government',
          trial_count: 0,
        },
      ],
      gap_cell_count: 1,
      generated_at: '2026-07-16T06:00:00Z',
    }),
  }))
}

test('source center shows server-authoritative lifecycle and five-dimensional gaps', async ({ page }) => {
  await mockSourceCenter(page)
  await openSourceCenter(page)

  await expect(page.getByRole('heading', { level: 1, name: '来源中心 V2' })).toBeVisible()
  await expect(page.getByText('生产已授权', { exact: true })).toBeVisible()
  await expect(page.getByText('仅试运行', { exact: true })).toBeVisible()
  await expect(page.getByLabel('生命周期')).toBeVisible()
  await expect(page.getByLabel('工程行业')).toBeVisible()
  await expect(page.getByRole('link', { name: '查看覆盖缺口' })).toHaveAttribute(
    'href',
    '/admin/sources/coverage',
  )

  await page.getByRole('link', { name: '查看覆盖缺口' }).click()
  await expect(page.getByRole('heading', { level: 1, name: '来源覆盖缺口' })).toBeVisible()
  await expect(page.getByRole('table', { name: '来源覆盖矩阵' })).toContainText('桥梁')
  await expect(page.getByRole('table', { name: '来源覆盖矩阵' })).toContainText('事故调查')
  await expect(page.getByText('缺口', { exact: true })).toBeVisible()
  await expect(page.getByText('网址总数')).toHaveCount(0)
})

test('source admin previews declarative config and executes only an available lifecycle command', async ({ page }) => {
  await mockSourceCenter(page)
  let assessmentBody: Record<string, unknown> | undefined
  let assessmentMethod: string | undefined
  let connectorSaveBody: Record<string, unknown> | undefined
  let governanceBody: Record<string, unknown> | undefined
  let governanceMethod: string | undefined
  let previewBody: Record<string, unknown> | undefined
  let pauseBody: Record<string, unknown> | undefined
  await page.route(`**/api/v1/admin/sources/${sourceId}/governance-metadata`, async (route) => {
    governanceMethod = route.request().method()
    governanceBody = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(sourceDetail) })
  })
  await page.route(`**/api/v1/admin/sources/${sourceId}/assessments`, async (route) => {
    assessmentMethod = route.request().method()
    assessmentBody = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(sourceDetail) })
  })
  await page.route(`**/api/v1/admin/sources/${sourceId}/connector-config-versions`, async (route) => {
    if (route.request().method() === 'POST') {
      connectorSaveBody = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          allowed_hosts: ['bridge.example.test'],
          config: {
            allowed_hosts: ['bridge.example.test'],
            feed_url: 'https://bridge.example.test/feed.xml',
          },
          config_sha256: '9'.repeat(64),
          connector_type: 'RSS_ATOM',
          created_at: '2026-07-16T05:20:00Z',
          created_by: '019b0000-0000-7000-8000-000000009015',
          credential_configured: true,
          definition_version: '1.0.0',
          id: '019b0000-0000-7000-8000-000000001516',
          policy_version_id: policyId,
          source_id: sourceId,
          validation_status: 'VALID',
          version_number: 3,
        }),
        status: 201,
      })
      return
    }
    await route.fallback()
  })
  await page.route(
    `**/api/v1/admin/sources/${sourceId}/connector-config-versions/preview`,
    async (route) => {
      previewBody = route.request().postDataJSON() as Record<string, unknown>
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          config: {
            allowed_hosts: ['bridge.example.test'],
            credential_ref: '[configured]',
            feed_url: 'https://bridge.example.test/feed.xml',
          },
          connector_type: 'RSS_ATOM',
          definition_version: '1.0.0',
          network_io_performed: false,
          schema_sha256: '4691b104889eeb16f6cb006d8284b6a8f5bb4b0c58ea2fd331ddf63f7eb2830d',
          schema_version: '2020-12',
        }),
      })
    },
  )
  await page.route(`**/api/v1/admin/sources/${sourceId}/pause`, async (route) => {
    pauseBody = route.request().postDataJSON() as Record<string, unknown>
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(pausedSourceDetail) })
  })

  await openSourceCenter(page)
  await page.getByRole('link', { name: sourceDetail.name }).click()
  await expect(page.getByRole('heading', { level: 1, name: sourceDetail.name })).toBeVisible()
  await expect(page.getByText('生产已授权', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '暂停来源' })).toBeVisible()
  await expect(page.getByRole('button', { name: '恢复来源' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '批准生产' })).toHaveCount(0)

  await page.getByRole('button', { name: '更新治理元数据' }).click()
  const governanceDrawer = page.getByRole('dialog', { name: '更新治理元数据' })
  await governanceDrawer.getByLabel('更新原因').fill('补齐公路桥梁来源覆盖维度')
  await governanceDrawer.getByRole('button', { name: '保存治理元数据' }).click()
  expect(governanceBody).toMatchObject({
    content_domains: ['SAFETY_REGULATION', 'DIGITAL_TRANSFORMATION_CASE'],
    country_codes: ['CN'],
    declared_roles: ['OFFICIAL_PRIMARY'],
    governance_owner_id: '019b0000-0000-7000-8000-000000001599',
    industries: ['BRIDGE'],
    language_tags: ['zh-CN'],
    reason: '补齐公路桥梁来源覆盖维度',
    region_codes: ['CN-SC'],
  })
  expect(governanceMethod).toBe('PUT')

  await page.getByRole('button', { name: '追加双维评估' }).click()
  const assessmentDrawer = page.getByRole('dialog', { name: '追加来源双维评估' })
  await assessmentDrawer.getByLabel('评估时间').fill('2026-07-16T12:00')
  await assessmentDrawer.getByLabel('权威等级').selectOption('A1')
  await assessmentDrawer.getByLabel('权威规则版本').fill('2.0.0')
  await assessmentDrawer.getByLabel('权威理由代码（逗号分隔）').fill('OFFICIAL_PRIMARY')
  await assessmentDrawer.getByLabel('权威证据引用（逗号分隔）').fill('evidence://authority/1')
  await assessmentDrawer.getByLabel('独立性等级').selectOption('EDITORIALLY_INDEPENDENT')
  await assessmentDrawer.getByLabel('独立性规则版本').fill('1.0.0')
  await assessmentDrawer.getByLabel('独立性理由代码（逗号分隔）').fill('EDITORIAL_SEPARATION')
  await assessmentDrawer.getByLabel('独立性证据引用（逗号分隔）').fill('evidence://independence/1')
  await assessmentDrawer.getByLabel('追加原因').fill('分别记录权威与独立性证据')
  await assessmentDrawer.getByRole('button', { name: '追加评估' }).click()
  expect(assessmentBody).toMatchObject({
    authority: {
      evidence_refs: ['evidence://authority/1'],
      level: 'A1',
      reason_codes: ['OFFICIAL_PRIMARY'],
      rule_version: '2.0.0',
    },
    independence: {
      evidence_refs: ['evidence://independence/1'],
      level: 'EDITORIALLY_INDEPENDENT',
      reason_codes: ['EDITORIAL_SEPARATION'],
      rule_version: '1.0.0',
    },
    reason: '分别记录权威与独立性证据',
  })
  expect(assessmentMethod).toBe('POST')

  await page.getByRole('tab', { name: '策略版本' }).click()
  await expect(page.getByRole('heading', { name: '2.0.0 · Schema 2.0.0' })).toBeVisible()
  await expect(page.getByText('a'.repeat(64), { exact: true })).toBeVisible()
  await expect(page.getByText('RAW_EVIDENCE_ALLOWED', { exact: true })).toBeVisible()
  await expect(page.getByText('授权已确认 · 技术条件已确认', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '新建策略版本' }).click()
  const policyDrawer = page.getByRole('dialog', { name: '新建策略版本' })
  await expect(policyDrawer.getByLabel('robots 结论')).toHaveValue('')
  await expect(policyDrawer.getByLabel('条款结论')).toHaveValue('')
  await expect(policyDrawer.getByText('提交策略不会自动批准。', { exact: true })).toBeVisible()
  await policyDrawer.getByLabel('来源 SLO').selectOption('APPLICABLE')
  await policyDrawer.getByLabel('SLO 分钟').fill('15')
  await expect(policyDrawer.getByLabel('已确认来源授权允许该 SLO')).not.toBeChecked()
  await expect(policyDrawer.getByLabel('已确认技术条件支持该 SLO')).not.toBeChecked()
  await expect(policyDrawer.getByRole('button', { name: '提交策略版本' })).toBeDisabled()
  await policyDrawer.getByLabel('已确认来源授权允许该 SLO').check()
  await expect(policyDrawer.getByRole('button', { name: '提交策略版本' })).toBeDisabled()
  await policyDrawer.getByLabel('已确认技术条件支持该 SLO').check()
  await expect(policyDrawer.getByRole('button', { name: '提交策略版本' })).toBeEnabled()
  await expect(policyDrawer.getByLabel('人工审批单号')).toHaveCount(0)
  await expect(policyDrawer.locator('textarea')).toHaveCount(0)
  await policyDrawer.getByRole('button', { name: '关闭抽屉' }).click()

  await page.getByRole('tab', { name: '连接器配置' }).click()
  await expect(page.getByText('已配置（引用不显示）', { exact: true })).toBeVisible()
  await expect(page.getByText('credential_ref')).toHaveCount(0)
  await expect(page.getByText('vault://')).toHaveCount(0)
  await page.getByRole('button', { name: '新建连接器配置' }).click()
  const connectorDrawer = page.getByRole('dialog', { name: '新建连接器配置' })
  await expect(connectorDrawer.getByRole('note')).toContainText('不会发起网络采集')
  await connectorDrawer.getByLabel('连接器定义').selectOption('RSS_ATOM')
  await connectorDrawer.getByLabel('Feed URL').fill('https://bridge.example.test/feed.xml')
  await connectorDrawer.getByLabel('允许主机').fill('bridge.example.test')
  await connectorDrawer.getByLabel('密钥系统引用（非明文，可选）').fill('vault://source-connectors/rss-token')
  await connectorDrawer.getByRole('button', { name: '仅校验配置' }).click()

  await expect(page.getByText('未发起网络采集', { exact: true })).toBeVisible()
  expect(previewBody).toMatchObject({
    config: {
      allowed_hosts: ['bridge.example.test'],
      credential_ref: 'vault://source-connectors/rss-token',
      feed_url: 'https://bridge.example.test/feed.xml',
    },
    connector_type: 'RSS_ATOM',
    definition_version: '1.0.0',
  })
  expect(previewBody).not.toHaveProperty('reason')
  await expect(page.getByText('vault://source-connectors/rss-token')).toHaveCount(0)
  await connectorDrawer.getByLabel('保存原因').fill('保存经预览验证的声明式 RSS 配置')
  await connectorDrawer.getByRole('button', { name: '保存为新版本' }).click()
  expect(connectorSaveBody).toMatchObject({
    config: {
      allowed_hosts: ['bridge.example.test'],
      credential_ref: 'vault://source-connectors/rss-token',
      feed_url: 'https://bridge.example.test/feed.xml',
    },
    connector_type: 'RSS_ATOM',
    definition_version: '1.0.0',
    reason: '保存经预览验证的声明式 RSS 配置',
  })

  await page.getByRole('tab', { name: '试运行' }).click()
  await expect(page.getByText('Fixture 回放', { exact: true })).toBeVisible()
  await expect(page.getByText('真实试运行', { exact: true })).toBeVisible()
  await expect(page.getByText('与生产数据隔离', { exact: true })).toBeVisible()
  await expect(page.getByText('100.00% READY', { exact: true })).toBeVisible()
  await expect(page.getByText('50.00% READY', { exact: true })).toBeVisible()
  await expect(page.getByText('6 / 6', { exact: true })).toBeVisible()
  await expect(page.getByText('2 / 1', { exact: true })).toBeVisible()
  await expect(page.getByText('1 / 1', { exact: true })).toBeVisible()
  const liveTrialCard = page.getByRole('article').filter({
    has: page.getByRole('heading', { name: '真实试运行', exact: true }),
  })
  await expect(liveTrialCard.getByText('拒绝的原始尝试', { exact: true }).locator('..')).toContainText('1')

  await page.getByRole('tab', { name: '审计与状态事件' }).click()
  await expect(page.getByText('APPROVE_PRODUCTION', { exact: true })).toBeVisible()
  await expect(page.getByText(/保存经严格 Schema 校验的连接器配置版本/)).toBeVisible()
  await expect(page.getByText(/req-round15-config-save/)).toBeVisible()

  await page.getByRole('button', { name: '暂停来源' }).click()
  const commandDrawer = page.getByRole('dialog', { name: '暂停来源' })
  await commandDrawer.getByLabel('操作原因').fill('条款证据需要重新复核')
  await commandDrawer.getByRole('button', { name: '确认暂停' }).click()
  expect(pauseBody).toEqual({ reason: '条款证据需要重新复核' })
})

test('source admin uploads and completes an isolated pending Fixture replay', async ({ page }) => {
  await mockSourceCenter(page)
  let completed = false
  let completionBody: Record<string, unknown> | undefined
  const uploads: { body: string, headers: Record<string, string> }[] = []

  await page.route(`**/api/v1/admin/sources/${trialSource.id}`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify(pendingFixtureSourceDetail),
  }))
  await page.route(`**/api/v1/admin/sources/${trialSource.id}/policy-versions`, route => route.fulfill({
    contentType: 'application/json',
    body: '[]',
  }))
  await page.route(`**/api/v1/admin/sources/${trialSource.id}/connector-config-versions`, route => route.fulfill({
    contentType: 'application/json',
    body: '[]',
  }))
  await page.route(`**/api/v1/admin/sources/${trialSource.id}/lifecycle-events`, route => route.fulfill({
    contentType: 'application/json',
    body: '[]',
  }))
  await page.route(`**/api/v1/admin/sources/${trialSource.id}/audit-events`, route => route.fulfill({
    contentType: 'application/json',
    body: '[]',
  }))
  await page.route(`**/api/v1/admin/sources/${trialSource.id}/trial-runs`, route => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify([completed
      ? {
          ...pendingFixtureTrial,
          completed_at: '2026-07-16T06:20:00Z',
          quality_summary: {
            parse_failed_count: 0,
            raw_count: 2,
            ready_count: 2,
            ready_ratio_bps: 10_000,
            rejected_raw_attempt_count: 0,
            security_failed_count: 0,
          },
          status: 'SUCCEEDED',
        }
      : pendingFixtureTrial]),
  }))
  await page.route(`**/api/v1/admin/sources/${trialSource.id}/fixture`, async (route) => {
    uploads.push({
      body: route.request().postData() ?? '',
      headers: route.request().headers(),
    })
    await route.fulfill({ contentType: 'application/json', body: '{}', status: 201 })
  })
  await page.route(
    `**/api/v1/admin/sources/${trialSource.id}/trial-runs/${pendingFixtureTrialId}/complete-fixture`,
    async (route) => {
      completionBody = route.request().postDataJSON() as Record<string, unknown>
      completed = true
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          ...pendingFixtureTrial,
          completed_at: '2026-07-16T06:20:00Z',
          quality_summary: {
            parse_failed_count: 0,
            raw_count: 2,
            ready_count: 2,
            ready_ratio_bps: 10_000,
            rejected_raw_attempt_count: 0,
            security_failed_count: 0,
          },
          status: 'SUCCEEDED',
        }),
      })
    },
  )

  await openSourceCenter(page)
  await page.getByRole('link', { name: trialSource.name }).click()
  await page.getByRole('tab', { name: '试运行' }).click()
  const pendingCard = page.getByRole('article').filter({
    has: page.getByRole('heading', { name: 'Fixture 回放', exact: true }),
  })
  await expect(pendingCard.getByText('PENDING', { exact: true })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  await pendingCard.getByLabel('Fixture 文件').setInputFiles({
    name: 'fixture.html',
    mimeType: 'text/html',
    buffer: Buffer.from('<html><body>fixed replay</body></html>'),
  })
  await pendingCard.getByLabel('Fixture 原文 URL').fill(
    'https://example.test/notices/fixed-replay',
  )
  await pendingCard.getByRole('button', { name: '上传 Fixture' }).click()

  expect(uploads[0]?.headers['x-filename']).toBe('fixture.html')
  expect(uploads[0]?.headers['x-document-url']).toBe('https://example.test/notices/fixed-replay')
  expect(uploads[0]?.headers['content-type']).toContain('text/html')
  expect(uploads[0]?.body).toContain('fixed replay')

  await pendingCard.getByLabel('Fixture 文件').setInputFiles({
    name: 'detail.html',
    mimeType: 'text/html',
    buffer: Buffer.from('<html><body>fixed detail replay</body></html>'),
  })
  await pendingCard.getByLabel('Fixture 原文 URL').fill(
    'https://example.test/notices/fixed-detail',
  )
  await pendingCard.getByRole('button', { name: '继续上传 Fixture' }).click()
  expect(uploads).toHaveLength(2)
  expect(uploads[1]?.headers['x-filename']).toBe('detail.html')
  expect(uploads[1]?.headers['x-document-url']).toBe('https://example.test/notices/fixed-detail')

  await pendingCard.getByLabel('完成原因').fill('固定样本已上传并完成回放')
  await pendingCard.getByRole('button', { name: '完成回放' }).click()
  expect(completionBody).toEqual({ reason: '固定样本已上传并完成回放' })
  await expect(pendingCard.getByText('SUCCEEDED', { exact: true })).toBeVisible()
  await expect(pendingCard.getByText('100.00% READY', { exact: true })).toBeVisible()
  await expect(pendingCard.getByText('2 / 2', { exact: true })).toBeVisible()
})

test('@a11y source center is read-only for auditor and has no axe violations', async ({ page }) => {
  await mockSourceCenter(page)
  await mockIdentity(page, ['auditor'])
  await page.setViewportSize({ width: 720, height: 900 })

  await openSourceCenter(page)
  for (const destination of ['list', 'detail', 'coverage'] as const) {
    if (destination === 'detail') {
      await page.getByRole('link', { name: sourceDetail.name }).click()
      await expect(page.getByRole('heading', { level: 1, name: sourceDetail.name })).toBeVisible()
    }
    if (destination === 'coverage') {
      await page.getByRole('button', { name: '打开导航' }).click()
      await page.getByRole('link', { name: '覆盖缺口', exact: true }).click()
      await expect(page.getByRole('heading', { level: 1, name: '来源覆盖缺口' })).toBeVisible()
    }
    await page.getByRole('button', { name: '打开导航' }).click()
    await expect(page.getByRole('link', { name: '管理入口' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('button', { name: /暂停来源|恢复来源|退役来源|批准生产/ })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /更新治理元数据|追加双维评估|新建策略版本|新建连接器配置|申请试运行/ })).toHaveCount(0)
    await expect(page.locator('input[name="governance-metadata-reason"]')).toHaveCount(0)
    await expect(page.locator('input[name="assessment-reason"]')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(720)
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([])
  }
})
