<!-- frontend/mambo/src/components/settings/resource/ResourceEditor.vue -->
<template>
  <div class="editor-container">
    <!-- Top Region: Version History (Horizontal) -->
    <!-- Req 4: Pass kbId to enable the config button -->
    <ResourceVersionBar
      v-if="resource.itemType === 'resource'"
      :versions="resource.versions || []"
      :active-version-id="resource.latest_version?.id || null"
      :viewing-version-id="loadedVersionInEditor?.id || null"
      :kb-id="resource.kb_id"
      @select-version="loadVersionIntoEditor"
      @set-active="handleSetActiveVersion"
      @toggle-kb-view="toggleKbView"
    />

    <!-- Region: KB Configuration View (Req 4) -->
    <div v-if="viewMode === 'kb_config'" class="kb-config-view">
      <div class="config-view-header">
        <el-button link @click="viewMode = 'editor'">
          <el-icon><ArrowLeft /></el-icon> 返回编辑器
        </el-button>
        <span class="view-title">知识库向量化配置</span>
      </div>
      <KnowledgeBaseFileDetail :resource="resource" />
    </div>

    <!-- Region: Standard Editor View -->
    <el-form v-else :model="form" label-position="top" ref="formRef" class="editor-split-layout">
      <!-- Left: Content Editor -->
      <div class="content-column">
        <template v-if="resource.itemType === 'resource'">
          <!-- Case A: File Resource (Req 1) -->
          <div v-if="resource.resourceType === 'file'" class="file-uploader-area">
            <div class="file-info-card">
              <el-icon :size="48" class="file-icon"><Document /></el-icon>
              <div class="file-meta">
                <h3>{{ resource.name }}</h3>
                <p>最后更新: {{ new Date(resource.updatedAt).toLocaleString() }}</p>
                <!-- Show download link if available in attributes, or just info -->
                <p v-if="resource.kb_id" class="kb-badge">
                  <el-tag size="small" type="info">已关联知识库</el-tag>
                </p>
              </div>
            </div>

            <div class="upload-actions">
              <el-upload
                class="upload-demo"
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                :on-change="handleFileChange"
              >
                <template #trigger>
                  <el-button type="primary" :loading="isUploading">
                    <el-icon class="el-icon--left"><Upload /></el-icon>
                    上传新版本
                  </el-button>
                </template>
              </el-upload>
              <div class="upload-tip">
                上传文件将自动创建一个新的版本。
                <span v-if="resource.kb_id"
                  >注意：更新文件内容会导致原有的向量切片失效，需重新执行任务。</span
                >
              </div>
            </div>
          </div>

          <!-- Case B: Text Resource (Prompt/Template) -->
          <template v-else>
            <div class="content-header">
              <span class="content-label">{{ contentEditorLabel }}</span>
            </div>
            <el-form-item prop="content" class="content-form-item">
              <el-input
                v-model="form.content"
                type="textarea"
                placeholder="在此处输入 Prompt 或模板内容..."
                class="content-textarea"
              />
            </el-form-item>
          </template>
        </template>

        <div v-else class="folder-placeholder">
          <el-empty description="文件夹无需编辑内容" :image-size="100" />
        </div>

        <!-- Footer Actions (Attached to content area) -->
        <!-- Only show footer for Text Resources, Files are handled by Upload -->
        <div
          class="editor-footer"
          v-if="resource.itemType === 'resource' && resource.resourceType !== 'file'"
        >
          <el-button @click="resetForm">重置</el-button>
          <el-button type="success" @click="openNewVersionDialog">另存为新版本</el-button>
          <el-button type="primary" @click="handleSaveChanges" :disabled="!isFormDirty"
            >保存更改</el-button
          >
        </div>
      </div>

      <!-- Right: Meta Sidebar -->
      <ResourceMetaSidebar
        :resource="resource"
        v-model:name="form.name"
        v-model:description="form.description"
        v-model:attributes="form.attributes"
        v-model:versionName="form.versionName"
        v-model:versionCommitMessage="form.versionCommitMessage"
      />
    </el-form>
  </div>

  <el-dialog v-model="newVersionDialog.visible" title="另存为新版本" width="500px">
    <el-form :model="newVersionDialog.form" label-position="top" ref="newVersionFormRef">
      <el-form-item
        label="版本名称"
        prop="name"
        :rules="{ required: true, message: '版本名称不能为空', trigger: 'blur' }"
      >
        <el-input v-model="newVersionDialog.form.name" placeholder="例如：v1.1 优化了逻辑" />
      </el-form-item>
      <el-form-item label="提交信息 (可选)" prop="commitMessage">
        <el-input
          v-model="newVersionDialog.form.commitMessage"
          type="textarea"
          placeholder="描述本次变更的内容"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newVersionDialog.visible = false">取消</el-button>
      <el-button type="primary" @click="handleConfirmNewVersion">确认</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile } from 'element-plus'
import { Document, Upload, ArrowLeft } from '@element-plus/icons-vue'

import { useResourceStore } from '@/stores/resourceStore'
import { uploadResourceFile } from '@/api/kbService'
import type { ResourceWithVersions, ResourceVersion, ResourceVersionCreate } from '@/api/types'
import ResourceVersionBar from './ResourceVersionBar.vue'
import ResourceMetaSidebar from './ResourceMetaSidebar.vue'
import KnowledgeBaseFileDetail from '../kb/KnowledgeBaseFileDetail.vue'

// --- Local Type Definitions ---
interface SubMessageTemplateAttributes {
  context_participation_length: number
  is_collapsed: boolean
  is_minimal: boolean
}

// --- Props ---
const props = defineProps<{
  resource: ResourceWithVersions
}>()

// --- Store ---
const resourceStore = useResourceStore()

// --- Constants ---
const DEFAULT_SUBMESSAGE_ATTRIBUTES: SubMessageTemplateAttributes = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: false,
}

// --- State ---
const formRef = ref<FormInstance>()
const newVersionFormRef = ref<FormInstance>()
const loadedVersionInEditor = ref<ResourceVersion | null>(null)
const viewMode = ref<'editor' | 'kb_config'>('editor')
const isUploading = ref(false)

const form = reactive({
  name: '',
  description: '',
  content: '',
  attributes: { ...DEFAULT_SUBMESSAGE_ATTRIBUTES },
  versionName: '',
  versionCommitMessage: '',
})

const newVersionDialog = reactive({
  visible: false,
  form: {
    name: '',
    commitMessage: '',
  },
})

// --- Computed Properties ---
const isFormDirty = computed(() => {
  const original = props.resource
  if (!original) return false

  const originalVersion = loadedVersionInEditor.value ?? original.latest_version
  const isMetaDirty =
    form.name !== original.name || form.description !== (original.description || '')

  if (original.itemType === 'resource' && originalVersion) {
    // Files don't use content/version meta dirty check in the same way (handled by upload)
    if (original.resourceType === 'file') return isMetaDirty

    const isVersionMetaDirty =
      form.versionName !== originalVersion.name ||
      form.versionCommitMessage !== (originalVersion.commitMessage || '')
    const isContentDirty = form.content !== (originalVersion?.content || '')
    let isAttributesDirty = false
    if (original.resourceType === 'submessage_template') {
      const originalAttributes = {
        ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
        ...((originalVersion?.attributes as Partial<SubMessageTemplateAttributes>) || {}),
      }
      isAttributesDirty = JSON.stringify(form.attributes) !== JSON.stringify(originalAttributes)
    }
    return isMetaDirty || isVersionMetaDirty || isContentDirty || isAttributesDirty
  }

  return isMetaDirty
})

const contentEditorLabel = computed(() => {
  if (loadedVersionInEditor.value) {
    return `内容 (正在查看: ${loadedVersionInEditor.value.name})`
  }
  return '内容 (当前版本)'
})

// --- Watchers ---
watch(
  () => props.resource,
  (newSelection) => {
    if (newSelection) {
      resetForm()
      // Reset view mode when switching resources
      viewMode.value = 'editor'
    } else {
      // Reset form when resource becomes null (handled by parent)
      form.name = ''
      form.description = ''
      form.content = ''
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
      form.versionName = ''
      form.versionCommitMessage = ''
    }
  },
  { immediate: true },
)

// --- Handlers ---

function toggleKbView() {
  viewMode.value = viewMode.value === 'editor' ? 'kb_config' : 'editor'
}

function resetForm() {
  const selection = props.resource
  if (selection) {
    const versionToLoad = selection.latest_version
    form.name = selection.name
    form.description = selection.description || ''
    form.content = versionToLoad?.content || ''
    form.versionName = versionToLoad?.name || ''
    form.versionCommitMessage = versionToLoad?.commitMessage || ''

    if (selection.resourceType === 'submessage_template') {
      form.attributes = {
        ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
        ...((versionToLoad?.attributes as Partial<SubMessageTemplateAttributes>) || {}),
      }
    } else {
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
    }
    loadedVersionInEditor.value = null // Reset to viewing latest version
  }
}

async function handleSaveChanges() {
  if (!props.resource || !isFormDirty.value) return
  const resource = props.resource

  // 1. Save Basic Meta (Name/Desc) - Applies to all types
  if (form.name !== resource.name || form.description !== (resource.description || '')) {
    await resourceStore.updateResourceItem(resource.id, {
      name: form.name,
      description: form.description,
    })
  }

  // 2. Save Content/Version Meta - Only for Text Resources
  if (resource.itemType === 'resource' && resource.resourceType !== 'file') {
    const targetVersionId = loadedVersionInEditor.value?.id ?? resource.latest_version?.id

    if (targetVersionId) {
      const payload = {
        name: form.versionName,
        commitMessage: form.versionCommitMessage,
        content: form.content,
        attributes: form.attributes,
      }
      await resourceStore.updateResourceVersionItem(resource.id, targetVersionId, payload)

      if (loadedVersionInEditor.value) {
        const updatedVersion = resource.versions.find((v) => v.id === targetVersionId)
        if (updatedVersion) {
          loadedVersionInEditor.value = { ...updatedVersion, ...payload }
        }
      }
    }
  }

  ElMessage.success('保存成功')
}

// File Upload Handler (Req 1)
async function handleFileChange(uploadFile: UploadFile) {
  if (!uploadFile.raw || !props.resource) return

  isUploading.value = true
  try {
    // Call the new unified upload API with resourceId to update the existing resource
    await uploadResourceFile(uploadFile.raw, undefined, props.resource.id)
    ElMessage.success('文件上传成功，新版本已创建')
    // Refresh details to show new version info
    await resourceStore.fetchResourceDetails(props.resource.id)
  } catch (error) {
    console.error(error)
    ElMessage.error('文件上传失败')
  } finally {
    isUploading.value = false
  }
}

function loadVersionIntoEditor(version: ResourceVersion) {
  form.content = version.content || ''
  form.versionName = version.name
  form.versionCommitMessage = version.commitMessage || ''

  if (props.resource?.resourceType === 'submessage_template') {
    form.attributes = {
      ...DEFAULT_SUBMESSAGE_ATTRIBUTES,
      ...((version.attributes as Partial<SubMessageTemplateAttributes>) || {}),
    }
  } else {
    form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
  }
  loadedVersionInEditor.value = version
}

async function handleSetActiveVersion(versionId: string) {
  if (!props.resource) return
  try {
    await ElMessageBox.confirm('确定要将此版本设为当前活跃版本吗？', '确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'info',
    })
    await resourceStore.setActiveResourceVersion(props.resource.id, versionId)
    ElMessage.success('活跃版本已切换')
  } catch {
    /* User canceled */
  }
}

function openNewVersionDialog() {
  if (!props.resource) return
  newVersionDialog.form.name = `v${props.resource.versions.length + 1}`
  newVersionDialog.form.commitMessage = ''
  newVersionDialog.visible = true
}

async function handleConfirmNewVersion() {
  if (!newVersionFormRef.value || !props.resource) return
  await newVersionFormRef.value.validate(async (valid) => {
    if (valid) {
      const versionData: ResourceVersionCreate = {
        ...newVersionDialog.form,
        content: form.content,
        attributes: form.attributes,
      }
      await resourceStore.createNewVersion(props.resource!.id, versionData)
      newVersionDialog.visible = false
      ElMessage.success('新版本创建成功')
    }
  })
}
</script>

<style scoped>
.editor-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

/* --- KB Config View --- */
.kb-config-view {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
}

.config-view-header {
  padding: 12px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  gap: 16px;
}

.view-title {
  font-weight: 600;
  font-size: 14px;
}

/* --- Split Layout --- */
.editor-split-layout {
  flex-grow: 1;
  display: flex;
  min-height: 0;
}

/* Left: Content Column */
.content-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 0;
  position: relative;
}

.content-header {
  padding: 12px 20px 0 20px;
  flex-shrink: 0;
}

.content-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.content-form-item {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  margin-bottom: 0 !important;
  padding: 10px 20px 0 20px;
}

:deep(.content-form-item .el-form-item__content) {
  flex-grow: 1;
  height: 100%;
}

:deep(.content-textarea) {
  height: 100%;
}

:deep(.content-textarea .el-textarea__inner) {
  height: 100% !important;
  resize: none;
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  line-height: 1.6;
  padding: 12px;
  border-radius: 4px;
}

.folder-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.editor-footer {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 16px 20px;
  border-top: 1px solid var(--el-border-color-lighter);
  background-color: #fff;
}

/* --- File Uploader Styles --- */
.file-uploader-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 32px;
}

.file-info-card {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 24px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-fill-color-lighter);
  width: 100%;
  max-width: 500px;
}

.file-icon {
  color: var(--el-text-color-secondary);
}

.file-meta h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
  color: var(--el-text-color-primary);
}

.file-meta p {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.kb-badge {
  margin-top: 8px !important;
}

.upload-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.upload-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  max-width: 400px;
  line-height: 1.5;
}
</style>
