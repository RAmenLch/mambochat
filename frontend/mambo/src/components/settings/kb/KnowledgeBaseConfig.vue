<!-- frontend/mambo/src/components/settings/kb/KnowledgeBaseConfig.vue -->
<template>
  <div class="kb-config-container">
    <div class="kb-config-header">
      <div class="header-title">知识库配置</div>
      <div class="header-subtitle">配置嵌入模型并管理知识库文档</div>
    </div>

    <el-scrollbar class="kb-config-content">
      <div class="config-section">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="kb-form">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="知识库名称" prop="name">
                <el-input v-model="form.name" placeholder="请输入知识库名称" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="嵌入模型" prop="embeddingModelId">
                <el-select
                  v-model="form.embeddingModelId"
                  placeholder="请选择嵌入模型"
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
                    <span
                      style="float: right; color: var(--el-text-color-secondary); font-size: 12px"
                    >
                      {{ getProviderName(model.providerId) }}
                    </span>
                  </el-option>
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item prop="embeddingRateLimit">
                <template #label>
                  <span>嵌入频率限制 (秒)</span>
                  <el-tooltip
                    content="每次 Embedding 请求后的冷却时间，用于防止触发 API 速率限制"
                    placement="top"
                  >
                    <el-icon class="label-icon"><QuestionFilled /></el-icon>
                  </el-tooltip>
                </template>
                <el-input-number
                  v-model="form.embeddingRateLimit"
                  :min="0"
                  :step="0.1"
                  :precision="2"
                  style="width: 100%"
                  placeholder="0.0"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="描述" prop="description">
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              placeholder="请输入知识库描述"
              resize="none"
            />
          </el-form-item>

          <div class="form-actions">
            <el-button
              type="primary"
              @click="handleSave"
              :loading="isSaving"
              :disabled="!isFormDirty"
            >
              保存配置
            </el-button>
          </div>
        </el-form>
      </div>

      <el-divider />

      <div class="files-section">
        <div class="files-header">
          <span class="section-title">文档列表</span>
          <div class="files-actions">
            <el-button type="primary" :icon="Upload" @click="triggerUpload" :disabled="!canUpload">
              上传文档
            </el-button>
            <input
              ref="fileInputRef"
              type="file"
              style="display: none"
              accept=".txt,.md,.pdf,.docx"
              @change="handleFileChange"
            />
          </div>
        </div>

        <div v-loading="isFilesLoading" class="tree-container">
          <el-tree
            v-if="kbTreeData.length > 0"
            :data="kbTreeData"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            default-expand-all
            :expand-on-click-node="false"
            class="kb-file-tree"
          >
            <template #default="{ node, data }">
              <div class="custom-tree-node" :class="{ 'is-stub': data.itemType === 'stub' }">
                <div class="node-content">
                  <el-icon class="node-icon">
                    <Folder v-if="data.itemType === 'folder'" />
                    <Document v-else />
                  </el-icon>
                  <span class="node-label" :title="node.label">{{ node.label }}</span>
                </div>

                <div class="node-actions" v-if="data.itemType === 'resource'">
                  <span class="upload-time">{{
                    new Date(data.updatedAt).toLocaleDateString()
                  }}</span>
                  <el-button type="primary" link size="small" @click="handleManageFile(data)">
                    <el-icon class="el-icon--left"><Setting /></el-icon>
                    配置任务
                  </el-button>
                  <el-button type="danger" link size="small" @click="handleDeleteFile(data)">
                    删除
                  </el-button>
                </div>
              </div>
            </template>
          </el-tree>
          <el-empty v-else description="暂无文档，请上传" :image-size="80" />
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

// --- Stores ---
const resourceStore = useResourceStore()
const providerStore = useProviderStore()
const { providers } = storeToRefs(providerStore)
const { resourceTree } = storeToRefs(resourceStore)

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

const rules = reactive<FormRules>({
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  embeddingModelId: [{ required: true, message: '请选择嵌入模型', trigger: 'change' }],
})

// --- Computed ---

// 获取所有 Embedding 类型的模型
const embeddingModels = computed(() => {
  return providerStore.allModels.filter((m) => m.model_type === 'embedding')
})

/**
 * 递归查找当前知识库节点
 */
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

/**
 * 获取当前知识库的树状结构数据
 */
const kbTreeData = computed(() => {
  const kbNode = findNodeById(resourceTree.value, props.resource.id)
  return kbNode?.children || []
})

// 获取 attributes
const currentAttributes = computed(() => {
  return props.resource.latest_version?.attributes || {}
})

// 判断表单是否有变更
const isFormDirty = computed(() => {
  const currentRateLimit = currentAttributes.value.embedding_rate_limit || 0
  return (
    form.name !== props.resource.name ||
    form.description !== (props.resource.description || '') ||
    form.embeddingModelId !== (currentAttributes.value.embedding_model_id || '') ||
    form.embeddingRateLimit !== currentRateLimit
  )
})

// 只有配置了模型且未在上传中时才允许上传
const canUpload = computed(() => {
  const savedModelId = currentAttributes.value.embedding_model_id
  return !!savedModelId && !isUploading.value
})

// --- Methods ---

const getProviderName = (providerId: string) => {
  const provider = providers.value.find((p) => p.id === providerId)
  return provider ? provider.name : 'Unknown Provider'
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
        // 1. 更新基本信息
        if (form.name !== props.resource.name || form.description !== (props.resource.description || '')) {
          await resourceStore.updateResourceItem(props.resource.id, {
            name: form.name,
            description: form.description,
          })
        }

        // 2. 更新版本信息
        const currentModelId = currentAttributes.value.embedding_model_id
        const currentRateLimit = currentAttributes.value.embedding_rate_limit || 0

        if (
          form.embeddingModelId !== currentModelId ||
          form.embeddingRateLimit !== currentRateLimit
        ) {
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

        ElMessage.success('配置已保存')
      } catch (error) {
        console.error(error)
        ElMessage.error('保存失败')
      } finally {
        isSaving.value = false
      }
    }
  })
}

const triggerUpload = () => {
  if (!canUpload.value) {
    ElMessage.warning('请先配置并保存嵌入模型')
    return
  }
  fileInputRef.value?.click()
}

const handleFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return

  const file = input.files[0]
  isUploading.value = true
  const loadingInstance = ElMessage.info({
    message: '正在上传文件...',
    duration: 0,
  })

  try {
    // 调用 Store 方法上传文件，Store 负责更新本地状态
    await resourceStore.uploadKBFile(props.resource.id, file)

    ElMessage.success('上传成功，请点击"配置任务"以启动切分与嵌入')
    // 刷新文件列表以确保视图更新
    await loadFiles()
  } catch (error) {
    console.error('Upload failed', error)
    ElMessage.error('上传失败')
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
      `确定要删除文档 "${file.name}" 吗？相关的向量数据也将被删除。`,
      '警告',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await resourceStore.deleteResourceItem(file.id)
    ElMessage.success('删除成功')
  } catch {
    // Cancelled
  }
}

// --- Lifecycle & Watchers ---

onMounted(() => {
  providerStore.fetchProviders()
  initForm()
  loadFiles()
})

// 监听资源ID变化，重置表单和文件列表
watch(
  () => props.resource.id,
  () => {
    initForm()
    loadFiles()
  },
)

// 监听属性变化，处理异步数据加载的情况
watch(
  () => props.resource.latest_version?.attributes,
  (newAttrs) => {
    if (newAttrs) {
      if (newAttrs.embedding_model_id && form.embeddingModelId !== newAttrs.embedding_model_id) {
        form.embeddingModelId = newAttrs.embedding_model_id
      }
      const rateLimit = newAttrs.embedding_rate_limit || 0
      if (form.embeddingRateLimit !== rateLimit) {
        form.embeddingRateLimit = rateLimit
      }
    }
  },
  { deep: true },
)
</script>

<style scoped>
.kb-config-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: #fff;
}

.kb-config-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.header-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.kb-config-content {
  flex-grow: 1;
}

.config-section {
  padding: 24px;
  max-width: 800px;
}

.form-actions {
  margin-top: 24px;
  display: flex;
  justify-content: flex-start;
}

.files-section {
  padding: 0 24px 24px 24px;
}

.files-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.files-actions {
  display: flex;
  gap: 12px;
}

.label-icon {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
  cursor: help;
  vertical-align: middle;
}

/* Tree Styles */
.tree-container {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
}

.kb-file-tree {
  /* Remove default padding if needed */
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  padding-right: 8px;
  height: 40px; /* Increase row height for better button visibility */
  width: 100%;
}

.custom-tree-node.is-stub {
  display: none;
}

.node-content {
  display: flex;
  align-items: center;
  overflow: hidden;
  flex-grow: 1;
}

.node-icon {
  margin-right: 8px;
  font-size: 16px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.node-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.upload-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: 8px;
}

:deep(.el-tree-node__content) {
  height: auto; /* Allow custom height */
  padding-top: 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

:deep(.el-tree-node__content:hover) {
  background-color: var(--el-fill-color-light);
}
</style>
