<script setup lang="ts">
import type { FixtureUploadResponse, SourceDetail } from '@srbg/contracts'
import { PageHeader, ResponsiveDrawer, StatusBadge } from '@srbg/ui'
import { computed, reactive, ref, watchEffect } from 'vue'

const route = useRoute()
const sourceId = computed(() => String(route.params.id))
const policyOpen = ref(false)
const onboardingOpen = ref(false)
const uploadOpen = ref(false)
const busy = ref(false)
const actionError = ref<string | null>(null)
const selectedFile = ref<File | null>(null)
const documentUrl = ref('')

const {
  data: source,
  error,
  refresh,
} = await useFetch<SourceDetail>(() => `/api/v1/admin/sources/${sourceId.value}`, {
  retry: 0,
  timeout: 5_000,
})

const defaultExpiry = new Date(Date.now() + 90 * 24 * 60 * 60 * 1_000).toISOString().slice(0, 16)
const policy = reactive({
  policy_version: '1.0.0',
  robots_result: 'ALLOWED',
  robots_url: '',
  terms_result: 'NOT_PRESENT',
  terms_url: '',
  allowed_domains: '',
  valid_until: defaultExpiry,
  approval_id: '',
  rate_limit_per_minute: 10,
  user_agent: 'SRBGSourceAdapter/1.0',
})

const requiredChecks = [
  'OWNER_VERIFIED',
  'ROBOTS_REVIEWED',
  'TERMS_REVIEWED',
  'COPYRIGHT_POLICY_SET',
  'RATE_LIMIT_SET',
  'DOMAIN_ALLOWLIST_SET',
  'THIRTY_FIXTURES_VALIDATED',
  'CONTRACT_TEST_PASS',
  'STRUCTURE_BASELINE_SET',
  'SECURITY_TEST_PASS',
  'OWNER_ASSIGNED',
] as const
const onboardingEvidence = reactive<Record<string, string>>(
  Object.fromEntries(requiredChecks.map(code => [code, ''])),
)
const onboardingValidUntil = ref(defaultExpiry)

watchEffect(() => {
  if (!source.value) return
  const url = new URL(source.value.base_url)
  policy.allowed_domains ||= url.hostname
  policy.robots_url ||= new URL('/robots.txt', url).toString()
  policy.terms_url ||= new URL('/terms-review', url).toString()
  policy.approval_id ||= `source-${source.value.registry_code ?? source.value.id}`
  documentUrl.value ||= source.value.base_url
  for (const code of requiredChecks) {
    onboardingEvidence[code] ||= `${source.value.base_url}#${code}`
  }
})

const stateLabel = computed(() => ({
  CANDIDATE: '候选',
  COMPLIANCE_REVIEW: '合规复核',
  FIXTURE_TEST: '样本测试',
  APPROVED: '已批准',
  ACTIVE: source.value?.effective_active ? '有效激活' : '未满足激活门禁',
}[source.value?.state ?? 'CANDIDATE']))

const nextState = computed(() => ({
  CANDIDATE: 'COMPLIANCE_REVIEW',
  COMPLIANCE_REVIEW: 'FIXTURE_TEST',
  FIXTURE_TEST: 'APPROVED',
  APPROVED: 'ACTIVE',
  ACTIVE: null,
} as const)[source.value?.state ?? 'ACTIVE'])

function apiMessage(value: unknown): string {
  if (typeof value !== 'object' || value === null) return '操作失败，请稍后重试。'
  const data = 'data' in value ? value.data : undefined
  if (typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string') {
    return data.detail
  }
  return '操作失败，请检查准入证据和服务状态。'
}

async function runAction(action: () => Promise<unknown>): Promise<void> {
  busy.value = true
  actionError.value = null
  try {
    await action()
    await refresh()
  } catch (requestError) {
    actionError.value = apiMessage(requestError)
  } finally {
    busy.value = false
  }
}

async function transition(): Promise<void> {
  if (!nextState.value) return
  if (nextState.value === 'ACTIVE') {
    await runAction(() => $fetch(`/api/v1/admin/sources/${sourceId.value}/enable`, {
      method: 'POST',
      body: { reason: '来源管理员确认启用' },
    }))
    return
  }
  await runAction(() => $fetch(`/api/v1/admin/sources/${sourceId.value}/transitions`, {
    method: 'POST',
    body: { target_state: nextState.value, reason: '来源管理员推进准入阶段' },
  }))
}

async function disableSource(): Promise<void> {
  await runAction(() => $fetch(`/api/v1/admin/sources/${sourceId.value}/disable`, {
    method: 'POST',
    body: { reason: '来源管理员手动停用' },
  }))
}

async function submitPolicy(): Promise<void> {
  await runAction(() => $fetch(`/api/v1/admin/sources/${sourceId.value}/policy`, {
    method: 'PUT',
    body: {
      policy_version: policy.policy_version,
      status: 'VALID',
      robots_review: {
        result: policy.robots_result,
        evidence_url: policy.robots_url,
        checked_at: new Date().toISOString(),
      },
      terms_review: {
        result: policy.terms_result,
        evidence_url: policy.terms_url,
        checked_at: new Date().toISOString(),
      },
      copyright: {
        storage_policy: 'RAW_EVIDENCE_ALLOWED',
        display_policy: 'METADATA_EXCERPT_LINK',
        fulltext_allowed: false,
        image_allowed: false,
        excerpt_max_chars: 300,
        attribution_template: '来源: {source_name}',
      },
      access: {
        allowed_domains: policy.allowed_domains.split(',').map(value => value.trim()).filter(Boolean),
        requires_auth: false,
        rate_limit_per_minute: policy.rate_limit_per_minute,
        user_agent: policy.user_agent,
      },
      review: {
        valid_until: new Date(policy.valid_until).toISOString(),
        approval_id: policy.approval_id,
      },
    },
  }))
  if (!actionError.value) policyOpen.value = false
}

async function submitOnboarding(): Promise<void> {
  await runAction(() => $fetch(`/api/v1/admin/sources/${sourceId.value}/onboarding-records`, {
    method: 'POST',
    body: {
      checks: requiredChecks.map(code => ({ code, evidence_ref: onboardingEvidence[code] })),
      valid_until: new Date(onboardingValidUntil.value).toISOString(),
    },
  }))
  if (!actionError.value) onboardingOpen.value = false
}

function selectFile(event: Event): void {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function uploadFixture(): Promise<void> {
  if (!selectedFile.value) {
    actionError.value = '请选择 HTML 或 PDF 文件。'
    return
  }
  busy.value = true
  actionError.value = null
  try {
    const result = await $fetch<FixtureUploadResponse>(
      `/api/v1/admin/sources/${sourceId.value}/fixture`,
      {
        method: 'POST',
        body: selectedFile.value,
        headers: {
          'Content-Type': selectedFile.value.type,
          'X-Filename': selectedFile.value.name,
          'X-Document-URL': documentUrl.value,
        },
        timeout: 30_000,
      },
    )
    uploadOpen.value = false
    await navigateTo(`/admin/documents/${result.document.id}`)
  } catch (requestError) {
    actionError.value = apiMessage(requestError)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section v-if="source" class="source-detail-page">
    <PageHeader
      :title="source.name"
      eyebrow="来源准入档案"
      :description="source.base_url"
      :updated-at="source.created_at"
      updated-label="登记时间"
    >
      <template #status>
        <StatusBadge
          :tone="source.effective_active ? 'healthy' : source.state === 'ACTIVE' ? 'conflict' : 'pending'"
          :label="stateLabel"
        />
        <span>{{ source.enabled ? 'enabled' : 'disabled' }} · {{ source.fixture_count }}/{{ source.eligibility.required_fixture_count }} 样本</span>
      </template>
      <template #actions>
        <button class="secondary-button" type="button" @click="policyOpen = true">准入策略</button>
        <button class="secondary-button" type="button" @click="onboardingOpen = true">准入记录</button>
        <button class="secondary-button" type="button" @click="uploadOpen = true">上传样本</button>
        <button v-if="nextState" class="primary-button" type="button" :disabled="busy" @click="transition">推进至 {{ nextState }}</button>
        <button v-if="source.enabled" class="danger-button" type="button" :disabled="busy" @click="disableSource">停用</button>
      </template>
    </PageHeader>

    <p v-if="actionError" class="problem" role="alert">{{ actionError }}</p>

    <div class="detail-grid">
      <article class="panel">
        <h2>准入门禁</h2>
        <dl class="gate-list">
          <div><dt>有效策略</dt><dd>{{ source.eligibility.policy_valid ? '通过' : '缺失/过期' }}</dd></div>
          <div><dt>准入记录</dt><dd>{{ source.eligibility.onboarding_valid ? '通过' : '缺失/过期' }}</dd></div>
          <div><dt>策略版本匹配</dt><dd>{{ source.eligibility.onboarding_policy_matches ? '匹配' : '不匹配' }}</dd></div>
          <div><dt>必检项</dt><dd>{{ source.eligibility.required_checks_complete ? '11/11' : '未完成' }}</dd></div>
          <div><dt>不同内容样本</dt><dd>{{ source.eligibility.fixture_count }}/{{ source.eligibility.required_fixture_count }}</dd></div>
        </dl>
        <ul v-if="source.eligibility.missing_reasons.length" class="missing-list">
          <li v-for="reason in source.eligibility.missing_reasons" :key="reason">{{ reason }}</li>
        </ul>
      </article>
      <article class="panel">
        <h2>来源元数据</h2>
        <dl class="metadata-list">
          <div><dt>登记编号</dt><dd>{{ source.registry_code ?? source.id }}</dd></div>
          <div><dt>频道 / 类型</dt><dd>{{ source.channel }} / {{ source.source_type }}</dd></div>
          <div><dt>权威 / 优先级</dt><dd>{{ source.authority_level }} / {{ source.priority }}</dd></div>
          <div><dt>接入方式</dt><dd>{{ source.collection_method }}</dd></div>
          <div><dt>负责人</dt><dd>{{ source.owner }}</dd></div>
        </dl>
      </article>
    </div>

    <ResponsiveDrawer v-model="policyOpen" title="来源准入策略" description="证据摘要由服务端计算，生产原始对象仍按字节计算 SHA-256。">
      <form id="policy-form" class="drawer-form" @submit.prevent="submitPolicy">
        <label>策略版本<input v-model.trim="policy.policy_version" required></label>
        <label>robots 证据 URL<input v-model.trim="policy.robots_url" required type="url"></label>
        <label>robots 结论<select v-model="policy.robots_result"><option value="ALLOWED">允许</option><option value="NOT_PRESENT">不存在</option><option value="RESTRICTED">受限</option><option value="BLOCKED">阻止</option></select></label>
        <label>条款复核证据 URL<input v-model.trim="policy.terms_url" required type="url"></label>
        <label>条款结论<select v-model="policy.terms_result"><option value="ALLOWED">允许</option><option value="NOT_PRESENT">不存在</option><option value="RESTRICTED">受限</option><option value="BLOCKED">阻止</option></select></label>
        <label>允许域名（逗号分隔）<input v-model.trim="policy.allowed_domains" required></label>
        <label>每分钟访问上限<input v-model.number="policy.rate_limit_per_minute" required type="number" min="1"></label>
        <label>User-Agent<input v-model.trim="policy.user_agent" required></label>
        <label>有效期至<input v-model="policy.valid_until" required type="datetime-local"></label>
        <label>批准单号<input v-model.trim="policy.approval_id" required></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="policyOpen = false">取消</button><button class="primary-button" type="submit" form="policy-form" :disabled="busy">保存策略</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="onboardingOpen" title="来源准入记录" description="全部 11 项必须留证；样本数量和样本集哈希由服务端读取文档库计算。">
      <form id="onboarding-form" class="drawer-form" @submit.prevent="submitOnboarding">
        <label v-for="code in requiredChecks" :key="code">{{ code }}<input v-model.trim="onboardingEvidence[code]" required maxlength="2048"></label>
        <label>记录有效期至<input v-model="onboardingValidUntil" required type="datetime-local"></label>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="onboardingOpen = false">取消</button><button class="primary-button" type="submit" form="onboarding-form" :disabled="busy">提交准入记录</button></div></template>
    </ResponsiveDrawer>

    <ResponsiveDrawer v-model="uploadOpen" title="上传固定样本" description="仅允许 HTML/PDF，最大 50 MiB；文件将先经结构与恶意内容扫描。">
      <form id="fixture-form" class="drawer-form" @submit.prevent="uploadFixture">
        <label>原文 URL<input v-model.trim="documentUrl" required type="url" maxlength="2048"></label>
        <label>HTML 或 PDF<input required type="file" accept="text/html,application/pdf,.html,.htm,.pdf" @change="selectFile"></label>
        <p class="file-note">{{ selectedFile ? `${selectedFile.name} · ${selectedFile.size} bytes` : '尚未选择文件' }}</p>
      </form>
      <template #footer><div class="drawer-actions"><button class="secondary-button" type="button" @click="uploadOpen = false">取消</button><button class="primary-button" type="submit" form="fixture-form" :disabled="busy">上传并建版本</button></div></template>
    </ResponsiveDrawer>
  </section>

  <section v-else class="source-detail-page">
    <PageHeader title="来源档案" eyebrow="来源管理" description="正在读取来源准入状态。" />
    <p v-if="error" class="problem" role="alert">来源不存在或服务暂不可用。</p>
  </section>
</template>

<style scoped>
.source-detail-page { display: grid; width: min(100%, var(--srbg-layout-content-max)); margin-inline: auto; gap: var(--spacing-5); }
.detail-grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: var(--spacing-4); }
.panel { padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.panel h2 { margin: 0 0 var(--spacing-4); color: var(--color-ink-900); font-size: var(--text-lg); }
.gate-list,
.metadata-list { display: grid; gap: 0; margin: 0; }
.gate-list div,
.metadata-list div { display: grid; grid-template-columns: minmax(8rem, 0.8fr) 1.2fr; gap: var(--spacing-3); padding: var(--spacing-3) 0; border-top: 1px solid var(--color-border); }
dt { color: var(--color-ink-600); }
dd { margin: 0; color: var(--color-ink-900); font-family: var(--font-mono); overflow-wrap: anywhere; }
.missing-list { margin: var(--spacing-4) 0 0; padding: var(--spacing-3) var(--spacing-3) var(--spacing-3) var(--spacing-8); color: var(--color-conflict-700); background: var(--color-conflict-50); border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: var(--text-xs); }
.drawer-form { display: grid; gap: var(--spacing-4); }
.drawer-form label { display: grid; gap: var(--spacing-1); color: var(--color-ink-700); font-size: var(--text-sm); font-weight: var(--font-weight-semibold); }
.drawer-form input,
.drawer-form select { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); color: var(--color-ink-900); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.drawer-actions { display: flex; justify-content: flex-end; gap: var(--spacing-2); }
.primary-button,
.secondary-button,
.danger-button { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-4); font-weight: var(--font-weight-semibold); border: 1px solid currentColor; border-radius: var(--radius-sm); cursor: pointer; }
.primary-button { color: var(--color-surface); background: var(--color-brand-700); border-color: var(--color-brand-700); }
.secondary-button { color: var(--color-brand-700); background: var(--color-surface); }
.danger-button { color: var(--color-conflict-700); background: var(--color-conflict-50); }
button:disabled { cursor: wait; opacity: 0.6; }
.problem { margin: 0; padding: var(--spacing-3); color: var(--color-conflict-700); background: var(--color-conflict-50); border: 1px solid currentColor; border-radius: var(--radius-sm); }
.file-note { margin: 0; color: var(--color-ink-600); font-family: var(--font-mono); font-size: var(--text-xs); }

@media (max-width: 52rem) { .detail-grid { grid-template-columns: 1fr; } }
@media (max-width: 36rem) { .gate-list div, .metadata-list div { grid-template-columns: 1fr; gap: var(--spacing-1); } }
</style>
