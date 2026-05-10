<!-- frontend/mambo/src/mobile/components/settings/resource/MobileKnowledgeBaseConfig.vue -->
<template>
  <div class="mobile-kb-config">
    <el-scrollbar class="main-scroll">
      <!-- Section 1: Basic Configuration -->
      <div class="config-section">
        <div class="section-title">{{ $t('kb.config.title') }}</div>

        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="kb-form">
          <el-form-item :label="$t('kb.config.labels.name')" prop="name">
            <el-input v-model="form.name" :placeholder="$t('kb.form.namePlaceholder')" />
          </el-form-item>

          <el-form-item :label="$t('kb.config.labels.description')" prop="description">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="2"
              :placeholder="$t('resource.meta.descPlaceholder')"
              resize="none"
            />
          </el-form-item>

          <el-form-item :label="$t('kb.config.labels.embeddingModel')" prop="embeddingModelId">
            <el-select
              v-model="form.embeddingModelId"
              :placeholder="$t('kb.form.modelPlaceholder')"
              :disabled="isSaving"
              clearable
              style="width: 100%"
            >
              <el-option
                v-for="model in embeddingModels"
                :key="model.id"
                :label="model.name"
                :value="model.id"
              >
                <span style="float: left">{{ model.name }}</span>
                <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px">
                  {{ getProviderName(model.providerId) }}
                </span>
              </el-option>
            </el-select>
          </el-form-item>

          <el-form-item>
            <template #label>
              <span>{{ $t('kb.config.labels.dimension') }}</span>
              <el-tooltip
                :content="$t('kb.config.dimensionTooltip')"
                placement="top"
              >
                <el-icon class="label-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input :model-value="currentDimension" disabled />
          </el-form-item>

          <el-form-item prop="embeddingRateLimit">
            <template #label>
              <span>{{ $t('kb.config.labels.rateLimit') }}</span>
              <el-tooltip :content="$t('kb.form.rateLimitTooltip')" placement="top">
                <el-icon class="label-icon"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input-number
              v-model="form.embeddingRateLimit"
              :min="0"
              :step="0.1"
              :precision="2"
              style="width: 100%"
              :placeholder="$t('kb.form.rateLimitPlaceholder')"
            />
          </el-form-item>

          <el-button
            type="primary"
            @click="handleSave"
            :loading="isSaving"
            :disabled="!isFormDirty"
            style="width: 100%"
          >
            {{ $t('common.action.save') }}
          </el-button>
        </el-form>
      </div>

      <el-divider />

      <!-- Section 2: File Management -->
      <div class="files-section">
        <div class="section-header">
          <span class="section-title">{{ $t('kb.config.file.listTitle') }}</span>
          <el-button type="primary" :icon="Upload" size="small" @click="triggerUpload" :disabled="!canUpload">
            {{ $t('kb.config.file.upload') }}
          </el-button>
          <input
            ref="fileInputRef"
            type="file"
            style="display: none"
            accept=".txt,.md,.pdf,.docx"
            @change="handleFileChange"
          />
        </div>

        <div v-loading="isFilesLoading" class="file-list-container">
          <template v-if="kbTreeData.length > 0">
            <div v-for="node in flattenTree(kbTreeData)" :key="node.id" class="file-item-card">
              <div class="file-item-content" @click="handleNodeClick(node)">
                <el-icon class="file-icon" :class="{ 'is-folder': node.itemType === 'folder' }">
                  <Folder v-if="node.itemType === 'folder'" />
                  <Document v-else />
                </el-icon>
                <div class="file-info">
                  <span class="file-name">{{ node.name }}</span>
                  <span class="file-meta" v-if="node.itemType === 'resource'">
                    {{ new Date(node.updatedAt).toLocaleDateString() }}
                  </span>
                </div>
              </div>

              <!-- Actions for Files -->
              <div v-if="node.itemType === 'resource'" class="file-actions">
                <el-button
                  type="primary"
                  link
                  size="small"
                  @click.stop="handleManageFile(node)"
                >
                  <el-icon><Setting /></el-icon>
                  {{ $t('kb.config.file.configTask') }}
                </el-button>
                <el-button
                  type="danger"
                  link
                  size="small"
                  @click.stop="handleDeleteFile(node)"
                >
                  {{ $t('common.action.delete') }}
                </el-button>
              </div>
            </div>
          </template>
          <el-empty v-else :description="$t('kb.config.file.empty')" :image-size="60" />
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Upload, Document, QuestionFilled, Setting, Folder } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'

import { useResourceStore } from '@/stores/resourceStore'
import { useProviderStore } from '@/stores/providerStore'
import type { Resource, ResourceWithVersions, ResourceNode } from '@/api/types'

// --- Props & Emits ---
const props = defineProps<{
  resource: ResourceWithVersions
}>()

const emit = defineEmits<{
  (e: 'select-file', resource: Resource): void
}>()

// --- Stores & I18n ---
const resourceStore = useResourceStore()
const providerStore = useProviderStore()
const { providers } = storeToRefs(providerStore)
const { resourceTree } = storeToRefs(resourceStore)
const { t } = useI18n()

// --- State ---
const formRef = ref<FormInstance>()
const fileInputRef = ref<HTMLInputElement>()
const isSaving = ref(false)
const isFilesLoading = ref(false)
const isUploading = ref(false)

interface KBFormState {
  name: string
  description: string
  embeddingModelId: string
  embeddingRateLimit: number
}

const form = reactive<KBFormState>({
  name: '',
  description: '',
  embeddingModelId: '',
  embeddingRateLimit: 0,
})

const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('kb.form.rule.nameRequired'), trigger: 'blur' }],
  embeddingModelId: [{ required: true, message: t('kb.form.rule.modelRequired'), trigger: 'change' }],
}))

// --- Computed ---

const embeddingModels = computed(() => {
  return providerStore.allModels.filter((m) => m.model_type === 'embedding')
})

// 知识库资源的向量维度（创建时固化，不可修改）
const currentDimension = computed(() => {
  const dim = currentAttributes.value.dimension
  if (dim != null && dim !== '') {
    return String(dim)
  }
  return '—'
})

const findNodeById = (nodes: ResourceNode[], id: string): ResourceNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node
    if (node.children) {
      const found = findNodeById(node.children, id)
      if (found) return found
    }
  }
  return null
}

const kbTreeData = computed(() => {
  const kbNode = findNodeById(resourceTree.value, props.resource.id)
  return kbNode?.children || []
})

const currentAttributes = computed(() => {
  return props.resource.latest_version?.attributes || {}
})

const isFormDirty = computed(() => {
  const currentRateLimit = currentAttributes.value.embedding_rate_limit || 0
  return (
    form.name !== props.resource.name ||
    form.description !== (props.resource.description || '') ||
    form.embeddingModelId !== (currentAttributes.value.embedding_model_id || '') ||
    form.embeddingRateLimit !== currentRateLimit
  )
})

const canUpload = computed(() => {
  const savedModelId = currentAttributes.value.embedding_model_id
  return !!savedModelId && !isUploading.value
})

// --- Methods ---

const getProviderName = (providerId: string) => {
  const provider = providers.value.find((p) => p.id === providerId)
  return provider ? provider.name : 'Unknown'
}

const initForm = () => {
  form.name = props.resource.name
  form.description = props.resource.description || ''
  form.embeddingModelId = currentAttributes.value.embedding_model_id || ''
  form.embeddingRateLimit = currentAttributes.value.embedding_rate_limit || 0
}

const loadFiles = async () => {
  isFilesLoading.value = true
  try {
    await resourceStore.fetchResourceChildren(props.resource.id)
  } finally {
    isFilesLoading.value = false
  }
}

const handleSave = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      isSaving.value = true
      try {
        if (form.name !== props.resource.name || form.description !== (props.resource.description || '')) {
          await resourceStore.updateResourceItem(props.resource.id, {
            name: form.name,
            description: form.description,
          })
        }

        const currentModelId = currentAttributes.value.embedding_model_id
        const currentRateLimit = currentAttributes.value.embedding_rate_limit || 0

        if (form.embeddingModelId !== currentModelId || form.embeddingRateLimit !== currentRateLimit) {
          if (props.resource.latest_version) {
            await resourceStore.updateResourceVersionItem(
              props.resource.id,
              props.resource.latest_version.id,
              {
                attributes: {
                  ...currentAttributes.value,
                  embedding_model_id: form.embeddingModelId,
                  embedding_rate_limit: form.embeddingRateLimit,
                },
              },
            )
          }
        }
        ElMessage.success(t('kb.msg.configSaved'))
      } catch (error) {
        console.error(error)
        ElMessage.error(t('kb.msg.saveFailed'))
      } finally {
        isSaving.value = false
      }
    }
  })
}

const triggerUpload = () => {
  if (!canUpload.value) {
    ElMessage.warning(t('kb.msg.configureModelFirst'))
    return
  }
  fileInputRef.value?.click()
}

const handleFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return

  const file = input.files[0]
  isUploading.value = true
  const loadingInstance = ElMessage.info({ message: t('kb.msg.uploading'), duration: 0 })

  try {
    await resourceStore.uploadKBFile(props.resource.id, file)
    ElMessage.success(t('kb.msg.uploadSuccess'))
    await loadFiles()
  } catch (error) {
    console.error('Upload failed', error)
    ElMessage.error(t('kb.msg.uploadFailed'))
  } finally {
    loadingInstance.close()
    isUploading.value = false
    input.value = ''
  }
}

const handleManageFile = (file: Resource) => {
  emit('select-file', file)
}

const handleDeleteFile = async (file: Resource) => {
  try {
    await ElMessageBox.confirm(
      t('kb.msg.deleteConfirm', { name: file.name }),
      t('common.action.delete'),
      { type: 'warning' }
    )
    await resourceStore.deleteResourceItem(file.id)
    ElMessage.success(t('kb.msg.deleteSuccess'))
  } catch {}
}

// Flatten tree for simple list rendering in mobile view
// Preserves folder structure logic if needed, but here we just show a flat list for simplicity
// or we can keep tree logic. Let's keep it simple: flatten.
const flattenTree = (nodes: ResourceNode[]): Resource[] => {
  const result: Resource[] = []
  const traverse = (items: ResourceNode[]) => {
    for (const item of items) {
      // We only show resources (files) directly, or handle folders if needed
      // For KB, usually it's files. But if folders exist:
      if (item.itemType === 'folder') {
        // Optional: handle folders
      } else if (item.itemType === 'resource') {
        result.push(item as unknown as Resource)
      }
      if (item.children && item.children.length > 0) {
        traverse(item.children)
      }
    }
  }
  traverse(nodes)
  return result
}

const handleNodeClick = (node: Resource) => {
  // On mobile, clicking the file item usually opens detail
  if (node.itemType === 'resource') {
    handleManageFile(node)
  }
}

// --- Lifecycle & Watchers ---

onMounted(() => {
  providerStore.fetchProviders()
  initForm()
  loadFiles()
})

watch(() => props.resource.id, () => {
  initForm()
  loadFiles()
})

watch(() => props.resource.latest_version?.attributes, (newAttrs) => {
  if (newAttrs) {
    if (newAttrs.embedding_model_id && form.embeddingModelId !== newAttrs.embedding_model_id) {
      form.embeddingModelId = newAttrs.embedding_model_id
    }
    const rateLimit = newAttrs.embedding_rate_limit || 0
    if (form.embeddingRateLimit !== rateLimit) {
      form.embeddingRateLimit = rateLimit
    }
  }
}, { deep: true })

</script>

<style scoped>
.mobile-kb-config {
  height: 100%;
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
}

.main-scroll {
  flex: 1;
}

.config-section {
  padding: 20px 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 16px;
}

.kb-form {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.label-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  cursor: help;
  vertical-align: middle;
}

/* Files Section */
.files-section {
  padding: 0 16px 20px 16px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.file-list-container {
  min-height: 150px;
}

.file-item-card {
  background-color: var(--color-background-soft);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.file-item-content {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.file-icon {
  font-size: 20px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
}

.file-icon.is-folder {
  color: var(--el-color-warning);
}

.file-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}

.file-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.file-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
  margin-left: 10px;
}

/* Adjust Divider */
.el-divider {
  margin: 10px 0;
}
</style>
