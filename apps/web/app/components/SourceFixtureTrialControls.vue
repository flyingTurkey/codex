<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  busy: boolean
  uploaded: boolean
}>()

const emit = defineEmits<{
  complete: [payload: { reason: string }]
  upload: [payload: { canonicalUrl: string, file: File }]
}>()

const fixtureFile = ref<File | null>(null)
const canonicalUrl = ref('')
const completionReason = ref('')

const canUpload = computed(() =>
  !props.busy
  && fixtureFile.value !== null
  && canonicalUrl.value.trim().length > 0,
)
const canComplete = computed(() =>
  !props.busy
  && props.uploaded
  && completionReason.value.trim().length >= 2,
)

function selectFixture(event: Event): void {
  const input = event.currentTarget
  fixtureFile.value = input instanceof HTMLInputElement ? input.files?.[0] ?? null : null
}

function uploadFixture(): void {
  const file = fixtureFile.value
  const normalizedUrl = canonicalUrl.value.trim()
  if (!file || !normalizedUrl || props.busy) return
  emit('upload', { canonicalUrl: normalizedUrl, file })
}

function completeFixture(): void {
  const reason = completionReason.value.trim()
  if (!props.uploaded || props.busy || reason.length < 2) return
  emit('complete', { reason })
}
</script>

<template>
  <section class="fixture-controls" aria-label="Fixture 回放执行">
    <p class="fixture-controls__note">
      仅上传固定样本，不发起外网请求。服务端会先保存原始响应，再执行长度、MIME、大小、压缩炸弹与主动内容校验。
    </p>

    <form
      class="fixture-controls__form"
      data-form="fixture-upload"
      @submit.prevent="uploadFixture"
    >
      <label>
        Fixture 文件
        <input
          name="fixture-file"
          type="file"
          required
          :disabled="busy"
          @change="selectFixture"
        >
      </label>
      <label>
        Fixture 原文 URL
        <input
          v-model.trim="canonicalUrl"
          name="fixture-canonical-url"
          type="url"
          required
          maxlength="2048"
          placeholder="https://approved.example/path"
          :disabled="busy"
        >
      </label>
      <button class="secondary-button" type="submit" :disabled="!canUpload">
        {{ uploaded ? '继续上传 Fixture' : '上传 Fixture' }}
      </button>
    </form>

    <form
      class="fixture-controls__form fixture-controls__completion"
      data-form="fixture-complete"
      @submit.prevent="completeFixture"
    >
      <label>
        完成原因
        <input
          v-model.trim="completionReason"
          name="fixture-completion-reason"
          required
          minlength="2"
          maxlength="500"
          :disabled="busy || !uploaded"
        >
      </label>
      <button
        class="primary-button"
        data-action="complete-fixture"
        type="submit"
        :disabled="!canComplete"
      >
        完成回放
      </button>
    </form>

    <p class="fixture-controls__boundary">
      Fixture 成功仅形成隔离试运行质量证据，永不授予生产采集授权。
    </p>
  </section>
</template>

<style scoped>
.fixture-controls {
  display: grid;
  margin-top: var(--spacing-4);
  padding: var(--spacing-4);
  background: var(--color-surfaceMuted);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  gap: var(--spacing-3);
}

.fixture-controls__form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr) auto;
  align-items: end;
  gap: var(--spacing-3);
}

.fixture-controls__completion {
  grid-template-columns: minmax(0, 1fr) auto;
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--color-border);
}

.fixture-controls label {
  display: grid;
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  gap: var(--spacing-1);
}

.fixture-controls input {
  min-height: var(--spacing-10);
  min-width: 0;
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.fixture-controls input[type='file'] {
  padding-block: var(--spacing-2);
}

.fixture-controls__note,
.fixture-controls__boundary {
  margin: 0;
  color: var(--color-ink-700);
  font-size: var(--text-sm);
}

.fixture-controls__boundary {
  color: var(--color-conflict-700);
}

.primary-button,
.secondary-button {
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-4);
  font-weight: var(--font-weight-semibold);
  border: 1px solid currentColor;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.primary-button {
  color: var(--color-surface);
  background: var(--color-brand-700);
  border-color: var(--color-brand-700);
}

.secondary-button {
  color: var(--color-brand-700);
  background: var(--color-surface);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

@media (max-width: 63.999rem) {
  .fixture-controls__form,
  .fixture-controls__completion {
    grid-template-columns: 1fr;
  }
}
</style>
