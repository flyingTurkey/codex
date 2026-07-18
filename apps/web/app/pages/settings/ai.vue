<script setup lang="ts">
type ProviderView = {
  code: string
  base_url: string
  request_path: string
  models: string[]
  real_call_enabled: boolean
  key_configured: boolean
  runtime_status: string
  blocking_reasons: string[]
}

type Feedback = { kind: 'success' | 'error', message: string }

const feedback = ref<Feedback | null>(null)
const savingSecret = ref(false)
const secretSavedNonce = ref(0)
const { data, error, refresh } = await useFetch<ProviderView[]>('/api/v1/settings/ai/providers', {
  server: false,
  retry: 0,
})

async function activate(provider: string, model: string): Promise<void> {
  feedback.value = null
  try {
    await $fetch('/api/v1/settings/ai/configurations', {
      method: 'POST',
      body: { provider, model },
    })
    await refresh()
    feedback.value = { kind: 'success', message: '配置版本已成功激活。' }
  }
  catch {
    feedback.value = { kind: 'error', message: '配置激活失败，请检查服务端状态后重试。' }
  }
}

async function saveSecret(provider: string, apiKey: string): Promise<void> {
  feedback.value = null
  savingSecret.value = true
  try {
    await $fetch(`/api/v1/settings/ai/providers/${provider}/secret`, {
      method: 'PUT',
      body: { api_key: apiKey },
    })
    await refresh()
    secretSavedNonce.value += 1
    feedback.value = {
      kind: 'success',
      message: '配置成功：Secret 已写入私有存储，页面不会回显。',
    }
  }
  catch {
    feedback.value = {
      kind: 'error',
      message: 'Secret 保存失败，输入内容已保留，请检查服务端状态后重试。',
    }
  }
  finally {
    savingSecret.value = false
  }
}
</script>

<template>
  <div>
    <aside
      v-if="feedback"
      class="ai-feedback"
      :data-kind="feedback.kind"
      :role="feedback.kind === 'error' ? 'alert' : 'status'"
      :aria-live="feedback.kind === 'error' ? 'assertive' : 'polite'"
    >
      <span>{{ feedback.message }}</span>
      <button type="button" aria-label="关闭提示" @click="feedback = null">关闭</button>
    </aside>
    <p v-if="error" role="alert">AI 配置暂不可用，请检查权限与服务端状态。</p>
    <template v-else-if="data">
      <AiConfigurationPanel
        :providers="data"
        :saving-secret="savingSecret"
        :secret-saved-nonce="secretSavedNonce"
        @activate="activate"
        @save-secret="saveSecret"
      />
    </template>
    <p v-else role="status">正在加载 AI 配置…</p>
  </div>
</template>

<style scoped>
.ai-feedback {
  position: fixed;
  z-index: 50;
  inset-block-start: var(--spacing-5);
  inset-inline-end: var(--spacing-5);
  display: flex;
  width: min(calc(100% - (2 * var(--spacing-5))), 28rem);
  align-items: start;
  justify-content: space-between;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  color: var(--color-brand-900);
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-300);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
}

.ai-feedback[data-kind='error'] {
  color: var(--color-danger-900);
  background: var(--color-danger-50);
  border-color: var(--color-danger-300);
}

.ai-feedback button {
  flex: none;
  min-height: var(--spacing-8);
  padding-inline: var(--spacing-2);
  color: inherit;
  background: transparent;
  border: 1px solid currentcolor;
  border-radius: var(--radius-sm);
}
</style>
