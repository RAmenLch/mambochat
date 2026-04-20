<template>
  <div class="mobile-resource-editor">

    <!-- 1. 版本栏 -->
    <MobileResourceVersionBar
      v-if="resource.itemType === 'resource'"
      :versions="resource.versions || []"
      :active-version-id="resource.latest_version?.id || null"
      :viewing-version-id="loadedVersionInEditor?.id || null"
      :kb-id="resource.kb_id"
      :view-mode="viewMode"
      @select-version="loadVersionIntoEditor"
      @set-active="handleSetActiveVersion"
      @toggle-kb-view="toggleKbView"
    />

    <!-- 2. 主内容区域 -->
    <div class="main-content-area">

      <!-- Case A: 知识库配置视图 -->
      <div v-if="viewMode === 'kb_config'" class="kb-view-container">
        <MobileKnowledgeBaseFileDetail :resource="resource" />
      </div>

      <!-- Case B: 标准编辑器视图 -->
      <template v-else>
        <!-- 标签切换栏 -->
        <div class="top-switcher">
          <el-radio-group v-model="activeTab" size="small">
            <el-radio-button label="editor">{{ t('resource.editor.contentLabel') || 'Content' }}</el-radio-button>
            <el-radio-button label="settings">{{ t('resource.meta.title') || 'Settings' }}</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 编辑器/设置内容 -->
        <div class="tab-content-wrapper">

          <!-- Tab A: 编辑器视图 -->
          <div v-show="activeTab === 'editor'" class="tab-pane-editor">
            <!-- 编辑器核心区域 -->
            <div class="editor-wrapper">
              <!-- Case A: 文件资源 -->
              <div v-if="resource.resourceType === 'file'" class="file-section" :class="{ 'is-editable-layout': isEditableFile }">

                <!-- Sub-case A1: Editable File -->
                <div v-if="isEditableFile" class="editable-file-mobile-layout">
                  <div class="file-info-compact">
                    <div class="file-preview-icon compact">
                      <el-icon :size="32"><Document /></el-icon>
                      <div class="editable-badge">
                        <el-icon><EditPen /></el-icon>
                      </div>
                    </div>
                    <div class="file-meta-content">
                      <span class="file-name">{{ currentFileInfo?.filename }}</span>
                      <div class="file-details">
                        <el-tag size="small" type="info" class="mime-tag">{{ currentFileInfo?.mime_type }}</el-tag>
                        <span class="file-size">{{ formatFileSize(currentFileInfo?.size || 0) }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="file-editor-wrapper">
                    <ResourceUniversalEditor
                      v-model="editableFileContent"
                      language="plaintext"
                      :monaco-options="editorOptions"
                    />
                  </div>

                  <!-- 按钮放在输入框下面 -->
                  <div class="editor-actions">
                    <el-button size="default" @click="resetForm">
                      {{ $t('resource.editor.reset') }}
                    </el-button>
                    <el-button size="default" type="success" plain @click="openNewVersionDialog">
                      {{ $t('resource.editor.saveAsNew') }}
                    </el-button>
                    <el-button
                      size="default"
                      type="primary"
                      @click="handleSaveChanges"
                      :disabled="!isFormDirty"
                    >
                      {{ $t('common.action.save') }}
                    </el-button>
                  </div>
                </div>

                <!-- Sub-case A2: Non-editable File -->
                <template v-else>
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
                </template>
              </div>

              <!-- Case B: 文本/Prompt 资源 -->
              <template v-else>
                <div class="monaco-container">
                  <ResourceUniversalEditor
                    v-model="form.content"
                    :language="editorLanguage"
                    :monaco-options="editorOptions"
                  />
                </div>
                <!-- 按钮放在编辑器下面 -->
                <div class="editor-actions">
                  <el-button size="default" @click="resetForm">
                    {{ $t('resource.editor.reset') }}
                  </el-button>
                  <el-button size="default" type="success" plain @click="openNewVersionDialog">
                    {{ $t('resource.editor.saveAsNew') }}
                  </el-button>
                  <el-button
                    size="default"
                    type="primary"
                    @click="handleSaveChanges"
                    :disabled="!isFormDirty"
                  >
                    {{ $t('common.action.save') }}
                  </el-button>
                </div>
              </template>
            </div>
          </div>

          <!-- Tab B: 设置视图 -->
          <div v-show="activeTab === 'settings'" class="tab-pane-settings">
            <el-scrollbar>
              <div class="settings-form">
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
      </template>

    </div>

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
import { Document, Download, EditPen } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import type { editor } from 'monaco-editor'

import { useResourceStore } from '@/stores/resourceStore'
import { uploadResourceFile } from '@/api/kbService'
import type { ResourceWithVersions, ResourceVersion, ResourceVersionCreate } from '@/api/types'
import ResourceUniversalEditor from '@/components/common/ResourceUniversalEditor.vue'
import MobileResourceVersionBar from './MobileResourceVersionBar.vue'
import MobileKnowledgeBaseFileDetail from './MobileKnowledgeBaseFileDetail.vue'

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

const activeTab = ref<'editor' | 'settings'>('editor')
const formRef = ref<FormInstance>()
const newVersionFormRef = ref<FormInstance>()
const loadedVersionInEditor = ref<ResourceVersion | null>(null)
const viewMode = ref<'editor' | 'kb_config'>('editor')
const isUploading = ref(false)

const editableFileContent = ref('')
const isFileContentLoading = ref(false)

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

const isEditableFile = computed(() => {
  return currentFileInfo.value?.editable ?? false
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
    if (original.resourceType === 'file' && isEditableFile.value) {
      const isContentDirty = editableFileContent.value !== (originalVersion.content || '')
      return isMetaDirty || isContentDirty
    }

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

watch(
  () => props.resource,
  (newSelection, oldSelection) => {
    if (newSelection) {
      if (newSelection.id !== oldSelection?.id) {
        resetForm()
        activeTab.value = 'editor'
        viewMode.value = props.initialViewMode === 'kb_config' ? 'kb_config' : 'editor'
      } else {
        if (newSelection.kb_id !== oldSelection?.kb_id) {
          viewMode.value = 'editor'
        }
        if (!loadedVersionInEditor.value) {
          resetForm()
        }
      }

      if (isEditableFile.value && currentVersion.value) {
        loadFileContent()
      }
    } else {
      form.name = ''
      form.description = ''
      form.content = ''
      form.attributes = { ...DEFAULT_SUBMESSAGE_ATTRIBUTES }
      form.versionName = ''
      form.versionCommitMessage = ''
      editableFileContent.value = ''
    }
  },
  { immediate: true }
)

watch(currentVersion, (newVersion) => {
  if (newVersion && isEditableFile.value) {
    loadFileContent()
  }
})

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function toggleKbView() {
  viewMode.value = 'kb_config'
}

async function loadFileContent() {
  if (!props.resource || !currentVersion.value) return

  isFileContentLoading.value = true
  try {
    await resourceStore.fetchFileContent(props.resource.id, currentVersion.value.id)
    editableFileContent.value = currentVersion.value.content || ''
  } catch (error) {
    console.error('Failed to load file content:', error)
    ElMessage.error(t('resource.editor.loadContentError'))
  } finally {
    isFileContentLoading.value = false
  }
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

    if (isEditableFile.value && versionToLoad) {
       editableFileContent.value = versionToLoad.content || ''
    } else {
       editableFileContent.value = ''
    }
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

  if (resource.itemType === 'resource') {
    if (resource.resourceType === 'file' && isEditableFile.value && currentVersion.value) {
       if (editableFileContent.value !== currentVersion.value.content) {
         await resourceStore.saveFileContent(
           resource.id,
           currentVersion.value.id,
           editableFileContent.value
         )
       }
    }
    else if (resource.resourceType !== 'file') {
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

  if (version.file_info?.editable) {
    loadFileContent()
  }

  if (viewMode.value === 'kb_config') {
    viewMode.value = 'editor'
  }
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
      if (isEditableFile.value && currentFileInfo.value) {
        try {
          const blob = new Blob([editableFileContent.value], { type: currentFileInfo.value.mime_type })
          const file = new File([blob], currentFileInfo.value.filename, { type: currentFileInfo.value.mime_type })

          await uploadResourceFile(file, undefined, props.resource.id)
          ElMessage.success(t('resource.editor.uploadSuccess'))
          newVersionDialog.visible = false
          await resourceStore.fetchResourceDetails(props.resource.id)
        } catch (error) {
          console.error(error)
          ElMessage.error(t('resource.editor.uploadError'))
        }
      }
      else {
        const versionData: ResourceVersionCreate = {
          ...newVersionDialog.form,
          content: form.content,
          attributes: form.attributes,
        }
        await resourceStore.createNewVersion(props.resource!.id, versionData)
        newVersionDialog.visible = false
        ElMessage.success(t('resource.editor.uploadSuccess'))
      }
    }
  })
}
</script>

<style scoped>
.mobile-resource-editor {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  height: 100dvh;
  height: 100%;
  background-color: var(--color-background);
  overflow: hidden;
}

.main-content-area {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background-soft);
  min-height: 0;
}

.kb-view-container {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
}

.tab-content-wrapper {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.top-switcher {
  flex-shrink: 0;
  padding: 2px 16px;
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
  color: var(--el-text-color-regular);
  font-weight: 500;
}

.top-switcher :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: #fff !important;
  color: var(--el-color-primary);
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
  border: none;
}

.tab-pane-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.editor-wrapper {
  flex: 1;
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.monaco-container {
  position: relative;
  flex-shrink: 0;
  margin: 10px 12px 8px 12px;
  height: 250px !important;
  background-color: #fff;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.tab-pane-settings {
  flex: 1;
  height: 100%;
  background-color: var(--color-background-soft);
  overflow-y: auto;
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

.file-section {
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
  box-sizing: border-box;
}

.file-section.is-editable-layout {
  padding: 8px 12px 8px 12px;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  box-sizing: border-box;
}

.editable-file-mobile-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: auto !important;
}

.file-info-compact {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 6px;
  background-color: #fff;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  flex-shrink: 0;
}

.file-preview-icon.compact {
  position: relative;
  width: 48px;
  height: 48px;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: var(--color-background-soft);
  border-radius: 8px;
}

.editable-badge {
  position: absolute;
  bottom: -4px;
  right: -4px;
  background-color: var(--el-color-success);
  color: white;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  border: 2px solid white;
  font-size: 12px;
}

.file-meta-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.file-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.file-details {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mime-tag {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.file-editor-wrapper {
  position: relative;
  background-color: #fff;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 420px !important;
  flex-shrink: 0;
  box-sizing: border-box;
}

.file-editor-wrapper :deep(.simple-textarea) {
  height: 100% !important;
  display: flex;
  flex-direction: column;
}

.file-editor-wrapper :deep(.el-textarea__inner) {
  height: 100% !important;
  max-height: 100% !important;
  overflow: auto !important;
  resize: none;
  padding: 8px 12px !important;
}

.file-editor-wrapper :deep(.monaco-editor-container) {
  height: 100% !important;
  overflow: hidden;
}

.monaco-container :deep(.monaco-editor-container) {
  height: 100% !important;
  overflow: hidden;
}

.monaco-container :deep(.simple-textarea) {
  height: 100% !important;
  display: flex;
  flex-direction: column;
}

.monaco-container :deep(.el-textarea__inner) {
  height: 100% !important;
  max-height: 100% !important;
  overflow: auto !important;
  resize: none;
  border: none !important;
  box-shadow: none !important;
}

.editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 0 0 0;
  flex-shrink: 0;
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
