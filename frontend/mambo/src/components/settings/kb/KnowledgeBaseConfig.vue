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
            <el-col :span="16">
              <el-form-item label="知识库名称" prop="name">
                <el-input v-model="form.name" placeholder="请输入知识库名称" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="嵌入模型 (Embedding Model)" prop="embeddingModelId">
                <el-select
                  v-model="form.embeddingModelId"
                  placeholder="请选择嵌入模型"
                  :disabled="isSaving"
                  clearable
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
            <el-button @click="refreshFiles" :icon="Refresh" circle />
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

        <el-table
          v-loading="isFilesLoading"
          :data="kbFiles"
          style="width: 100%"
          empty-text="暂无文档，请上传"
        >
          <el-table-column prop="name" label="文件名" min-width="200">
            <template #default="{ row }">
              <div class="file-name-cell">
                <el-icon><Document /></el-icon>
                <span class="text-truncate" :title="row.name">{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="updatedAt" label="上传时间" width="180">
            <template #default="{ row }">
              {{ new Date(row.updatedAt).toLocaleString() }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100" align="right">
            <template #default="{ row }">
              <el-button type="danger" link size="small" @click="handleDeleteFile(row)">
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Refresh, Upload, Document } from '@element-plus/icons-vue'

import { useResourceStore } from '@/stores/resourceStore'
import { useProviderStore } from '@/stores/providerStore'
import { uploadKBFile } from '@/api/kbService'
import type { Resource, ResourceWithVersions } from '@/api/types'

// --- Props ---
const props = defineProps<{
  resource: ResourceWithVersions
}>()

// --- Stores ---
const resourceStore = useResourceStore()
const providerStore = useProviderStore()
const { providers } = storeToRefs(providerStore)

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
}

const form = reactive<KBFormState>({
  name: '',
  description: '',
  embeddingModelId: '',
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

// 获取当前知识库下的文件列表
const kbFiles = computed(() => {
  return resourceStore.resources.filter(
    (r) => r.parentId === props.resource.id && r.itemType === 'resource',
  )
})

// 获取 attributes
const currentAttributes = computed(() => {
  return props.resource.latest_version?.attributes || {}
})

// 判断表单是否有变更
const isFormDirty = computed(() => {
  return (
    form.name !== props.resource.name ||
    form.description !== (props.resource.description || '') ||
    form.embeddingModelId !== (currentAttributes.value.embedding_model_id || '')
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
        // 1. 更新基本信息 (Name/Description)
        if (form.name !== props.resource.name || form.description !== props.resource.description) {
          await resourceStore.updateResourceItem(props.resource.id, {
            name: form.name,
            description: form.description,
          })
        }

        // 2. 更新版本信息 (Attributes -> embedding_model_id)
        // 只有当模型ID变更时才调用版本更新
        const currentModelId = currentAttributes.value.embedding_model_id
        if (form.embeddingModelId !== currentModelId) {
          if (props.resource.latest_version) {
            await resourceStore.updateResourceVersionItem(
              props.resource.id,
              props.resource.latest_version.id,
              {
                attributes: {
                  ...currentAttributes.value,
                  embedding_model_id: form.embeddingModelId,
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

const refreshFiles = () => {
  loadFiles()
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
    message: '正在上传并处理文件...',
    duration: 0,
  })

  try {
    // 接收接口返回的新资源对象
    const newFile = await uploadKBFile(props.resource.id, file)

    // 将新文件直接添加到 Store 中，以立即更新 UI 列表
    // 补充 versions 字段以符合 ResourceWithVersions 类型
    const newResourceWithVersions: ResourceWithVersions = {
      ...newFile,
      versions: [],
    }
    resourceStore.resources.push(newResourceWithVersions)

    ElMessage.success('上传成功，后台正在进行向量化处理')
  } catch (error) {
    console.error('Upload failed', error)
    ElMessage.error('上传失败')
  } finally {
    loadingInstance.close()
    isUploading.value = false
    input.value = ''
  }
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

// 监听嵌入模型ID变化，处理异步数据加载的情况
// 解决刷新页面后，详情数据异步返回导致表单未更新的问题
watch(
  () => props.resource.latest_version?.attributes?.embedding_model_id,
  (newVal) => {
    if (newVal && form.embeddingModelId !== newVal) {
      form.embeddingModelId = newVal
    }
  },
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

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.text-truncate {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
