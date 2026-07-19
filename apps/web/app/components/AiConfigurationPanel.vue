<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type ProviderView = {
  code: string
  base_url: string
  request_path: string
  models: string[]
  real_call_enabled: boolean
  key_configured: boolean
  configured: boolean
  available: boolean
  runtime_status: string
  blocking_reasons: string[]
  token_limits?: { CLASSIFY: number, EXTRACT: number, SUMMARIZE?: number, VERIFY?: number }
  budget?: { monthly_points: number, document_points: number } | null
}

const props = withDefaults(defineProps<{
  providers: ProviderView[]
  savingSecret?: boolean
  secretSavedNonce?: number
}>(), {
  savingSecret: false,
  secretSavedNonce: 0,
})
const emit = defineEmits<{
  activate: [provider: string, model: string]
  saveSecret: [provider: string, value: string]
}>()
const selectedProvider = ref('deepseek')
const selectedModel = ref('deepseek-v4-flash')
const secretValue = ref('')
const selected = computed(() =>
  props.providers.find(provider => provider.code === selectedProvider.value),
)

watch(() => props.secretSavedNonce, () => {
  secretValue.value = ''
})

function runtimeStatusLabel(status: string): string {
  return status === 'AVAILABLE' ? '可用' : `不可用（${status}）`
}

function selectProvider(code: string): void {
  selectedProvider.value = code
  selectedModel.value = props.providers.find(provider => provider.code === code)?.models[0] ?? ''
  secretValue.value = ''
}

function saveSecret(): void {
  if (!secretValue.value || props.savingSecret) return
  emit('saveSecret', selectedProvider.value, secretValue.value)
}
</script>

<template>
  <section class="ai-config" aria-labelledby="ai-config-title">
    <header>
      <p>R-AI01 · 受控模型能力</p>
      <h1 id="ai-config-title">AI 模型配置</h1>
      <p>端点和能力由服务端目录固定；密钥只写入本地私有 Secret，永不回显。</p>
    </header>

    <div class="ai-config__layout">
      <nav aria-label="模型提供方">
        <button
          v-for="provider in providers"
          :key="provider.code"
          type="button"
          :aria-current="provider.code === selectedProvider ? 'page' : undefined"
          @click="selectProvider(provider.code)"
        >
          <span>{{ provider.code.toUpperCase() }}</span>
          <small>{{ provider.real_call_enabled ? runtimeStatusLabel(provider.runtime_status) : '仅 Mock' }}</small>
        </button>
      </nav>

      <form v-if="selected" class="ai-config__form" @submit.prevent>
        <dl>
          <div><dt>固定端点</dt><dd>{{ selected.base_url }}{{ selected.request_path }}</dd></div>
          <div><dt>运行能力</dt><dd>{{ selected.real_call_enabled ? '允许受控调用' : '仅 Mock' }}</dd></div>
          <div><dt>配置状态</dt><dd>{{ selected.configured ? '已配置' : '未配置' }}</dd></div>
          <div><dt>真实可用性</dt><dd class="ai-config__runtime" :data-status="selected.runtime_status">{{ runtimeStatusLabel(selected.runtime_status) }}</dd></div>
          <div><dt>Secret</dt><dd>{{ selected.key_configured ? '已配置' : '未配置' }}</dd></div>
          <div><dt>阻断原因</dt><dd>{{ selected.blocking_reasons.join('、') || '无' }}</dd></div>
          <div v-if="selected.token_limits">
            <dt>Token 上限</dt>
            <dd>
              分类 {{ selected.token_limits.CLASSIFY }} / 抽取 {{ selected.token_limits.EXTRACT }} /
              判断 {{ selected.token_limits.SUMMARIZE ?? 1500 }} / 核验 {{ selected.token_limits.VERIFY ?? 1500 }}
            </dd>
          </div>
          <div v-if="selected.budget"><dt>预算</dt><dd>月度 {{ selected.budget.monthly_points }} 分 / 单文档 {{ selected.budget.document_points }} 分</dd></div>
        </dl>
        <label>
          模型
          <select v-model="selectedModel">
            <option v-for="model in selected.models" :key="model" :value="model">{{ model }}</option>
          </select>
        </label>
        <button type="button" @click="emit('activate', selected.code, selectedModel)">激活配置版本</button>
        <label>
          写入 Secret
          <input v-model="secretValue" type="password" autocomplete="new-password" maxlength="4096" :disabled="savingSecret">
        </label>
        <button data-testid="save-secret" type="button" :disabled="!secretValue || savingSecret" @click="saveSecret">
          {{ savingSecret ? '正在保存…' : '保存 Secret' }}
        </button>
      </form>
    </div>
  </section>
</template>

<style scoped>
.ai-config { display: grid; width: min(100%, var(--srbg-layout-content-max)); margin-inline: auto; gap: var(--spacing-5); }
.ai-config > header, .ai-config__form { padding: var(--spacing-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.ai-config h1, .ai-config p, .ai-config dl { margin: 0; }
.ai-config > header { display: grid; gap: var(--spacing-2); }
.ai-config__layout { display: grid; grid-template-columns: minmax(12rem, .32fr) minmax(0, 1fr); gap: var(--spacing-4); }
.ai-config nav, .ai-config__form, .ai-config__form dl { display: grid; gap: var(--spacing-3); }
.ai-config nav button, .ai-config__form button, .ai-config input, .ai-config select { min-height: var(--spacing-10); padding: var(--spacing-2) var(--spacing-3); color: var(--color-ink-900); background: var(--color-surface); border: 1px solid var(--color-borderStrong); border-radius: var(--radius-sm); }
.ai-config nav button { display: flex; justify-content: space-between; gap: var(--spacing-2); }
.ai-config nav button[aria-current='page'] { color: var(--color-brand-700); background: var(--color-brand-50); }
.ai-config__form dl div, .ai-config__form label { display: grid; gap: var(--spacing-1); }
.ai-config__form dt, .ai-config__form label { color: var(--color-ink-600); font-size: var(--text-sm); }
.ai-config__form dd { margin: 0; overflow-wrap: anywhere; color: var(--color-ink-900); }
.ai-config__runtime[data-status='AVAILABLE'] { color: var(--color-brand-700); }
@media (max-width: 47.999rem) { .ai-config__layout { grid-template-columns: 1fr; } }
</style>
