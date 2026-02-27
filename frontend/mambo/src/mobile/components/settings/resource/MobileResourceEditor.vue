<!-- frontend/mambo/src/mobile/components/settings/resource/MobileResourceEditor.vue -->
<template>
  <div class="mobile-resource-editor">

    <!-- 0. 顶部操作栏 (固定在最上方) -->
    <div
      class="top-actions-bar"
      v-if="resource.itemType === 'resource' && resource.resourceType !== 'file'"
    >
      <div class="action-left">
        <el-button link size="small" @click="resetForm">
          {{ $t('resource.editor.reset') }}
        </el-button>
      </div>
      <div class="action-right">
        <el-button size="small" type="success" plain @click="openNewVersionDialog">
          {{ $t('resource.editor.saveAsNew') }}
        </el-button>
        <el-button
          size="small"
          type="primary"
          @click="handleSaveChanges"
          :disabled="!isFormDirty"
        >
          {{ $t('common.action.save') }}
        </el-button>
      </div>
    </div>

    <!-- 1. 标签切换栏 -->
    <!-- 修改点: 移除了 fill 属性 -->
    <div class="top-switcher">
      <el-radio-group v-model="activeTab" size="small">
        <el-radio-button label="editor">{{ t('resource.editor.contentLabel') || 'Content' }}</el-radio-button>
        <el-radio-button label="settings">{{ t('resource.meta.title') || 'Settings' }}</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 2. 中间内容区 -->
    <div class="main-content-area">

      <!-- Tab A: 编辑器视图 -->
      <div v-show="activeTab === 'editor'" class="tab-pane-editor">
        <!-- 版本栏 -->
        <MobileResourceVersionBar
          v-if="resource.itemType === 'resource'"
          :versions="resource.versions || []"
          :active-version-id="resource.latest_version?.id || null"
          :viewing-version-id="loadedVersionInEditor?.id || null"
          :kb-id="resource.kb_id"
          :view-mode="viewMode"
          @select-version="loadVersionIntoEditor"
          @set-active="handleSetActiveVersion"
        />

        <!-- 编辑器核心区域 -->
        <div class="editor-wrapper">
          <!-- Case A: 文件资源 -->
          <div v-if="resource.resourceType === 'file'" class="file-section">
            <div v-if="currentFileInfo" class="file-preview-card">
              <div class="preview-area">
                 <el-image
                  v-if="isImage"
                  :src="fileDownloadUrl"
                  fit="contain"
                  class="preview-image"
                  :preview-src-list="[fileDownloadUrl]"
                 />
                 <el-icon v-else :size="60" class="file-icon"><Document /></el-icon>
              </div>
              <div class="file-info">
                <span class="filename">{{ currentFileInfo.filename }}</span>
                <div class="meta">
                  <el-tag size="small" type="info">{{ currentFileInfo.mime_type }}</el-tag>
                  <span class="size">{{ formatFileSize(currentFileInfo.size) }}</span>
                </div>
                <a :href="fileDownloadUrl" target="_blank" class="download-link">
                  <el-button type="primary" size="small" :icon="Download">
                    {{ $t('resource.editor.downloadFile') }}
                  </el-button>
                </a>
              </div>
            </div>

            <div class="upload-area">
              <el-upload
                action="#"
                :auto-upload="false"
                :show-file-list="false"
                :on-change="handleFileChange"
                :disabled="isUploading"
              >
                <el-button type="primary" :loading="isUploading">
                  {{ currentFileInfo ? $t('resource.editor.uploadNew') : $t('resource.editor.uploadFile') }}
                </el-button>
              </el-upload>
            </div>
          </div>

          <!-- Case B: 文本/Prompt 资源 -->
          <template v-else>
            <!-- 卡片式容器，四周留白 -->
            <div class="monaco-container">
              <ResourceUniversalEditor
                v-model="form.content"
                :language="editorLanguage"
                :monaco-options="editorOptions"
              />
            </div>
          </template>
        </div>
      </div>

      <!-- Tab B: 设置视图 -->
      <div v-show="activeTab === 'settings'" class="tab-pane-settings">
        <el-scrollbar>
          <div class="settings-form">
            <!-- 基础信息 -->
            <div class="form-section">
              <div class="section-title">{{ $t('resource.meta.title') }}</div>
              <el-form label-position="top" size="default">
                <el-form-item :label="$t('resource.meta.name')">
                  <el-input v-model="form.name" />
                </el-form-item>
                <el-form-item :label="$t('resource.meta.description')">
                  <el-input v-model="form.description" type="textarea" :rows="3" />
                </el-form-item>
              </el-form>
            </div>

            <!-- 版本信息 -->
            <div class="form-section">
              <div class="section-title">{{ $t('resource.meta.versionTitle') }}</div>
              <el-form label-position="top" size="default">
                <el-form-item :label="$t('resource.meta.versionName')">
                  <el-input v-model="form.versionName" />
                </el-form-item>
                <el-form-item :label="$t('resource.meta.versionCommit')">
                  <el-input v-model="form.versionCommitMessage" type="textarea" :rows="3" />
                </el-form-item>
              </el-form>
            </div>

            <!-- 模板配置 -->
            <template v-if="resource.resourceType === 'submessage_template'">
              <div class="form-section">
                <div class="section-title">{{ $t('resource.meta.configTitle') }}</div>
                <el-form label-position="top" size="default">
                   <el-form-item>
                      <template #label>
                        <span>{{ $t('resource.meta.participation') }}</span>
                      </template>
                      <el-input-number v-model="form.attributes.context_participation_length" :min="0" style="width: 100%" />
                   </el-form-item>
                   <el-form-item :label="$t('resource.meta.collapsed')">
                     <el-switch v-model="form.attributes.is_collapsed" />
                   </el-form-item>
                   <el-form-item :label="$t('resource.meta.minimal')">
                     <el-switch v-model="form.attributes.is_minimal" />
                   </el-form-item>
                </el-form>
              </div>
            </template>
          </div>
        </el-scrollbar>
      </div>

    </div>

    <!-- New Version Dialog -->
    <el-dialog v-model="newVersionDialog.visible" :title="$t('resource.dialog.saveAsNewTitle')" width="90%">
      <el-form :model="newVersionDialog.form" label-position="top" ref="newVersionFormRef">
        <el-form-item
          :label="$t('resource.dialog.versionName')"
          prop="name"
          :rules="{ required: true, message: $t('resource.dialog.versionNameRequired'), trigger: 'blur' }"
        >
          <el-input v-model="newVersionDialog.form.name" />
        </el-form-item>
        <el-form-item :label="$t('resource.dialog.commitMessage')" prop="commitMessage">
          <el-input v-model="newVersionDialog.form.commitMessage" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newVersionDialog.visible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="handleConfirmNewVersion">{{ $t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile } from 'element-plus'
import { Document, Download, Warning } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import type { editor } from 'monaco-editor'

import { useResourceStore } from '@/stores/resourceStore'
import { uploadResourceFile } from '@/api/kbService'
import type { ResourceWithVersions, ResourceVersion, ResourceVersionCreate } from '@/api/types'
import ResourceUniversalEditor from '@/components/common/ResourceUniversalEditor.vue'
import MobileResourceVersionBar from './MobileResourceVersionBar.vue'

const { t } = useI18n()

interface SubMessageTemplateAttributes {
  context_participation_length: number
  is_collapsed: boolean
  is_minimal: boolean
}

const props = defineProps<{
  resource: ResourceWithVersions
  initialViewMode?: 'editor' | 'kb_config'
}>()

const resourceStore = useResourceStore()

const DEFAULT_SUBMESSAGE_ATTRIBUTES: SubMessageTemplateAttributes = {
  context_participation_length: 1,
  is_collapsed: false,
  is_minimal: false,
}

// --- State ---
const activeTab = ref<'editor' | 'settings'>('editor')
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

// --- Computed ---
const currentVersion = computed(() => {
  return loadedVersionInEditor.value ?? props.resource.latest_version
})

const currentFileInfo = computed(() => {
  return currentVersion.value?.file_info ?? null
})

const isImage = computed(() => {
  const mime = currentFileInfo.value?.mime_type
  return mime ? mime.startsWith('image/') : false
})

const fileDownloadUrl = computed(() => {
  return currentFileInfo.value?.url ?? ''
})

const isFormDirty = computed(() => {
  const original = props.resource
  if (!original) return false

  const originalVersion = currentVersion.value
  const isMetaDirty =
    form.name !== original.name || form.description !== (original.description || '')

  if (original.itemType === 'resource' && originalVersion) {
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

const editorLanguage = computed(() => {
  if (form.name.endsWith('.json')) return 'json'
  return 'markdown'
})

const editorOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
  minimap: { enabled: false },
  lineNumbers: 'on',
  lineNumbersMinChars: 3,
  folding: true,
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  fontSize: 14,
  fontFamily: 'var(--el-font-family)',
  automaticLayout: true
}))

// --- Watchers ---
watch(
  () => props.resource,
  (newSelection) => {
    if (newSelection) {
      resetForm()
      activeTab.value = 'editor'
      viewMode.value = props.initialViewMode === 'kb_config' ? 'kb_config' : 'editor'
    }
  },
  { immediate: true }
)

// --- Methods ---
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
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
    loadedVersionInEditor.value = null
  }
}

async function handleSaveChanges() {
  if (!props.resource || !isFormDirty.value) return
  const resource = props.resource

  if (form.name !== resource.name || form.description !== (resource.description || '')) {
    await resourceStore.updateResourceItem(resource.id, {
      name: form.name,
      description: form.description,
    })
  }

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

  ElMessage.success(t('resource.editor.saveSuccess'))
}

async function handleFileChange(uploadFile: UploadFile) {
  if (!uploadFile.raw || !props.resource) return

  isUploading.value = true
  try {
    await uploadResourceFile(uploadFile.raw, undefined, props.resource.id)
    ElMessage.success(t('resource.editor.uploadSuccess'))
    await resourceStore.fetchResourceDetails(props.resource.id)
  } catch (error) {
    console.error(error)
    ElMessage.error(t('resource.editor.uploadError'))
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
  activeTab.value = 'editor'
}

async function handleSetActiveVersion(versionId: string) {
  if (!props.resource) return
  try {
    await ElMessageBox.confirm(
      t('resource.version.confirmActive'),
      t('resource.tree.moveWarningTitle'),
      { type: 'info' }
    )
    await resourceStore.setActiveResourceVersion(props.resource.id, versionId)
    ElMessage.success(t('resource.version.switchSuccess'))
  } catch {}
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
      ElMessage.success(t('resource.editor.uploadSuccess'))
    }
  })
}
</script>

<style scoped>
.mobile-resource-editor {
  /* 强制填满父容器 */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
  overflow: hidden;
}

/* 0. 顶部操作栏 */
.top-actions-bar {
  flex-shrink: 0;
  padding: 10px 16px;
  background-color: #fff;
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  z-index: 20;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

.action-right {
  display: flex;
  gap: 8px;
}

/* 1. 顶部切换器 */
.top-switcher {
  flex-shrink: 0;
  padding: 12px 16px;
  display: flex;
  justify-content: center;
  background-color: var(--color-background-soft);
}

.top-switcher :deep(.el-radio-group) {
  width: 100%;
  display: flex;
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px;
  border-radius: 4px;
}
.top-switcher :deep(.el-radio-button) {
  flex: 1;
}
.top-switcher :deep(.el-radio-button__inner) {
  width: 100%;
  border: none;
  background: transparent;
  border-radius: 4px;
  /* 确保未选中状态文字颜色清晰 */
  color: var(--el-text-color-regular);
  font-weight: 500;
}

/* 核心修复：选中状态样式 */
.top-switcher :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  /* 使用 !important 确保覆盖 Element Plus 默认的蓝色背景 */
  background-color: #fff !important;
  /* 选中时文字变为主题色 */
  color: var(--el-color-primary);
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
  border: none;
}

/* 2. 中间内容区 */
.main-content-area {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
}

/* Tab A: 编辑器视图 */
.tab-pane-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.editor-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.monaco-container {
  /* 关键：往回缩，形成卡片效果 */
  position: absolute;
  top: 10px;
  left: 12px;
  right: 12px;
  bottom: 12px;

  background-color: #fff;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
}

/* Tab B: 设置视图 */
.tab-pane-settings {
  flex: 1;
  height: 100%;
  background-color: var(--color-background-soft);
}

.settings-form {
  padding: 16px;
  padding-bottom: 40px;
}

.form-section {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  margin-bottom: 16px;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

/* File Section */
.file-section {
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
}

.file-preview-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  border: 1px solid var(--el-border-color);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

.preview-area {
  width: 100%;
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-background-soft);
  border-radius: 4px;
}

.preview-image {
  max-width: 100%;
  max-height: 180px;
}

.file-info {
  width: 100%;
  text-align: center;
}

.filename {
  font-weight: 600;
  font-size: 15px;
  display: block;
  margin-bottom: 8px;
  word-break: break-all;
}

.meta {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
</style>
