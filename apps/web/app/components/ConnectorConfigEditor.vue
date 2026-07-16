<script setup lang="ts">
import { computed, reactive } from 'vue'

import type {
  ConnectorDefinitionOption,
  ConnectorKind,
  DeclarativeConnectorPayload,
} from '../source-center'

const props = defineProps<{
  definitions: readonly ConnectorDefinitionOption[]
}>()

const emit = defineEmits<{
  preview: [payload: DeclarativeConnectorPayload]
}>()

const form = reactive({
  allowedFileTypes: [] as string[],
  allowedHosts: '',
  connectorType: '' as '' | ConnectorKind,
  credentialRef: '',
  documentUrls: '',
  endpointUrl: '',
  externalIdPointer: '',
  feedUrl: '',
  fileImportEnabled: false,
  itemSelector: '',
  itemsPointer: '',
  linkSelector: '',
  listUrl: '',
  publishedAtPointer: '',
  publishedSelector: '',
  sitemapUrl: '',
  titlePointer: '',
  titleSelector: '',
  urlImportEnabled: false,
  urlPointer: '',
})

const selectedDefinition = computed(() =>
  props.definitions.find(definition => definition.connectorType === form.connectorType),
)

function commaSeparatedValues(value: string): string[] {
  return [...new Set(value.split(',').map(item => item.trim()).filter(Boolean))]
}

function commonConfig(): Record<string, unknown> {
  return {
    allowed_hosts: commaSeparatedValues(form.allowedHosts).map(host => host.toLowerCase()),
    ...(form.credentialRef.trim() ? { credential_ref: form.credentialRef.trim() } : {}),
  }
}

function connectorConfig(kind: ConnectorKind): Record<string, unknown> {
  const common = commonConfig()
  if (kind === 'RSS_ATOM') return { ...common, feed_url: form.feedUrl.trim() }
  if (kind === 'SITEMAP') return { ...common, sitemap_url: form.sitemapUrl.trim() }
  if (kind === 'DIRECT_PDF') {
    return { ...common, document_urls: commaSeparatedValues(form.documentUrls) }
  }
  if (kind === 'JSON_API') {
    return {
      ...common,
      endpoint_url: form.endpointUrl.trim(),
      field_pointers: {
        external_id: form.externalIdPointer.trim(),
        published_at: form.publishedAtPointer.trim() || undefined,
        title: form.titlePointer.trim(),
        url: form.urlPointer.trim(),
      },
      items_pointer: form.itemsPointer.trim(),
      pagination: 'NONE',
    }
  }
  if (kind === 'LIST_DETAIL') {
    return {
      ...common,
      item_selector: form.itemSelector.trim(),
      link_selector: form.linkSelector.trim(),
      list_url: form.listUrl.trim(),
      published_selector: form.publishedSelector.trim() || undefined,
      title_selector: form.titleSelector.trim(),
    }
  }
  return {
    ...common,
    allowed_file_types: [...form.allowedFileTypes],
    file_import_enabled: form.fileImportEnabled,
    url_import_enabled: form.urlImportEnabled,
  }
}

function submitPreview(): void {
  const definition = selectedDefinition.value
  if (!definition) return
  emit('preview', {
    config: connectorConfig(definition.connectorType),
    connector_type: definition.connectorType,
    definition_version: definition.definitionVersion,
  })
  // Accept the reference once; neither the editor nor preview result echoes it.
  form.credentialRef = ''
}
</script>

<template>
  <form class="connector-editor" @submit.prevent="submitPreview">
    <p class="validation-note" role="note">
      此处只执行 Schema 与安全策略校验，不会发起网络采集，也不会创建试运行。
    </p>

    <label for="connector-definition">连接器定义</label>
    <select id="connector-definition" v-model="form.connectorType" name="connector-type" required>
      <option value="" disabled>请选择固定连接器</option>
      <option
        v-for="definition in definitions"
        :key="definition.connectorType"
        :value="definition.connectorType"
      >
        {{ definition.label }} · Definition {{ definition.definitionVersion }}
      </option>
    </select>

    <label for="connector-allowed-hosts">允许主机</label>
    <input
      id="connector-allowed-hosts"
      v-model.trim="form.allowedHosts"
      name="allowed-hosts"
      required
      maxlength="1000"
      placeholder="example.gov.cn, data.example.gov.cn"
      aria-describedby="connector-host-help"
    >
    <p id="connector-host-help" class="field-help">
      只接受来源策略内的固定 DNS 主机；禁止通配符、IP、内网与动态目标。
    </p>

    <template v-if="form.connectorType === 'RSS_ATOM'">
      <label for="connector-feed-url">Feed URL</label>
      <input id="connector-feed-url" v-model.trim="form.feedUrl" name="feed-url" required type="url" maxlength="2048">
    </template>

    <template v-if="form.connectorType === 'SITEMAP'">
      <label for="connector-sitemap-url">Sitemap URL</label>
      <input id="connector-sitemap-url" v-model.trim="form.sitemapUrl" name="sitemap-url" required type="url" maxlength="2048">
    </template>

    <template v-if="form.connectorType === 'JSON_API'">
      <label for="connector-endpoint-url">API 端点 URL</label>
      <input id="connector-endpoint-url" v-model.trim="form.endpointUrl" name="endpoint-url" required type="url" maxlength="2048">
      <label for="connector-items-pointer">记录集合 JSON Pointer</label>
      <input id="connector-items-pointer" v-model.trim="form.itemsPointer" name="items-pointer" required maxlength="300" placeholder="/data/items">
      <fieldset>
        <legend>字段 JSON Pointer</legend>
        <label for="connector-external-id-pointer">外部 ID</label>
        <input id="connector-external-id-pointer" v-model.trim="form.externalIdPointer" name="external-id-pointer" required maxlength="300" placeholder="/id">
        <label for="connector-url-pointer">文档 URL</label>
        <input id="connector-url-pointer" v-model.trim="form.urlPointer" name="url-pointer" required maxlength="300" placeholder="/url">
        <label for="connector-title-pointer">标题</label>
        <input id="connector-title-pointer" v-model.trim="form.titlePointer" name="title-pointer" required maxlength="300" placeholder="/title">
        <label for="connector-published-pointer">原文时间（可选）</label>
        <input id="connector-published-pointer" v-model.trim="form.publishedAtPointer" name="published-at-pointer" maxlength="300" placeholder="/published_at">
      </fieldset>
      <p class="fixed-value">分页协议：NONE（首版固定，不接受表达式）</p>
    </template>

    <template v-if="form.connectorType === 'LIST_DETAIL'">
      <label for="connector-list-url">列表 URL</label>
      <input id="connector-list-url" v-model.trim="form.listUrl" name="list-url" required type="url" maxlength="2048">
      <label for="connector-item-selector">列表项选择器</label>
      <input id="connector-item-selector" v-model.trim="form.itemSelector" name="item-selector" required maxlength="100" placeholder="article.notice">
      <label for="connector-link-selector">详情链接选择器</label>
      <input id="connector-link-selector" v-model.trim="form.linkSelector" name="link-selector" required maxlength="100" placeholder="a.notice-link">
      <label for="connector-title-selector">标题选择器</label>
      <input id="connector-title-selector" v-model.trim="form.titleSelector" name="title-selector" required maxlength="100" placeholder="h2.title">
      <label for="connector-published-selector">原文时间选择器（可选）</label>
      <input id="connector-published-selector" v-model.trim="form.publishedSelector" name="published-selector" maxlength="100" placeholder="time.published">
    </template>

    <template v-if="form.connectorType === 'DIRECT_PDF'">
      <label for="connector-document-urls">PDF 文档 URL（逗号分隔）</label>
      <input id="connector-document-urls" v-model.trim="form.documentUrls" name="document-urls" required maxlength="10000">
    </template>

    <template v-if="form.connectorType === 'MANUAL_IMPORT'">
      <fieldset>
        <legend>人工导入能力</legend>
        <label class="checkbox-row"><input v-model="form.urlImportEnabled" type="checkbox" name="url-import-enabled">允许人工 URL</label>
        <label class="checkbox-row"><input v-model="form.fileImportEnabled" type="checkbox" name="file-import-enabled">允许人工文件</label>
      </fieldset>
      <fieldset>
        <legend>允许文件类型</legend>
        <label v-for="fileType in ['HTML', 'PDF', 'ZIP']" :key="fileType" class="checkbox-row">
          <input v-model="form.allowedFileTypes" type="checkbox" name="allowed-file-types" :value="fileType">
          {{ fileType }}
        </label>
      </fieldset>
    </template>

    <label for="connector-credential-ref">密钥系统引用（非明文，可选）</label>
    <input
      id="connector-credential-ref"
      v-model.trim="form.credentialRef"
      name="credential-ref"
      type="text"
      inputmode="url"
      autocomplete="off"
      maxlength="220"
      pattern="vault://source-connectors/[A-Za-z0-9][A-Za-z0-9/_-]{0,190}"
      placeholder="vault://source-connectors/credential-name"
      aria-describedby="connector-credential-help"
    >
    <p id="connector-credential-help" class="field-help">
      只允许 vault://source-connectors/ 引用；不要填写令牌、密码、Cookie 或 API Key 明文。
    </p>

    <button class="primary-button" type="submit">仅校验配置</button>
  </form>
</template>

<style scoped>
.connector-editor {
  display: grid;
  gap: var(--spacing-2);
}

.connector-editor > label,
.connector-editor fieldset > label:not(.checkbox-row) {
  margin-top: var(--spacing-2);
  color: var(--color-ink-700);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

.connector-editor input:not([type='checkbox']),
.connector-editor select {
  width: 100%;
  min-height: var(--spacing-10);
  padding: var(--spacing-2) var(--spacing-3);
  color: var(--color-ink-900);
  background: var(--color-surface);
  border: 1px solid var(--color-borderStrong);
  border-radius: var(--radius-sm);
}

.connector-editor fieldset {
  display: grid;
  gap: var(--spacing-2);
  margin: var(--spacing-3) 0 0;
  padding: var(--spacing-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
}

.connector-editor legend {
  padding-inline: var(--spacing-1);
  color: var(--color-ink-900);
  font-weight: var(--font-weight-semibold);
}

.checkbox-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  color: var(--color-ink-700);
}

.checkbox-row input {
  width: var(--spacing-4);
  height: var(--spacing-4);
}

.validation-note,
.field-help,
.fixed-value {
  margin: 0;
  color: var(--color-ink-600);
  font-size: var(--text-xs);
  line-height: var(--srbg-font-line-height-body);
}

.validation-note {
  padding: var(--spacing-3);
  color: var(--color-brand-800);
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-200);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.fixed-value {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-surfaceMuted);
  border-radius: var(--radius-sm);
}

.primary-button {
  min-height: var(--spacing-10);
  margin-top: var(--spacing-3);
  padding: var(--spacing-2) var(--spacing-4);
  color: var(--color-surface);
  background: var(--color-brand-700);
  border: 1px solid var(--color-brand-700);
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-semibold);
  cursor: pointer;
}
</style>
