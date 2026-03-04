<!-- frontend/mambo/src/components/settings/resource/ResourceEditor.vue -->
<template>
  <div class="editor-container">
    <!-- Top Region: Version History (Horizontal) -->
    <ResourceVersionBar
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

    <!-- Region: KB Configuration View -->
    <div v-if="viewMode === 'kb_config'" class="kb-config-view">
      <div class="kb-detail-wrapper">
        <KnowledgeBaseFileDetail :resource="resource" />
      </div>
    </div>

    <!-- Region: Standard Editor View -->
    <el-form v-else :model="form" label-position="top" ref="formRef" class="editor-split-layout">
      <!-- Left: Content Editor -->
      <div class="content-column">
        <template v-if="resource.itemType === 'resource'">
          <!-- Case A: File Resource -->
          <div v-if="resource.resourceType === 'file'" class="file-uploader-area" :class="{ 'is-editable-layout': isEditableFile }">

            <!-- Sub-case A1: Editable File (New Layout) -->
            <div v-if="isEditableFile" class="editable-file-layout">
              <!-- Left: Compact Info -->
              <div class="file-info-compact">
                <!-- Icon & Editable Badge with Tooltip -->
                <div class="file-preview-icon compact">
                  <el-icon :size="56"><Document /></el-icon>
                  <el-tooltip :content="t('resource.editor.editableTooltip')" placement="top" effect="dark">
                    <div class="editable-badge">
                      <el-icon><EditPen /></el-icon>
                    </div>
                  </el-tooltip>
                </div>

                <!-- Meta Info (Restored from original) -->
                <div class="file-meta-content">
                  <h3 class="file-name" :title="currentFileInfo?.filename">
                    {{ currentFileInfo?.filename }}
                  </h3>
                  <div class="editable-status-text">
                    <el-icon><Select /></el-icon> {{ t('resource.editor.editableHint') }}
                  </div>
                  <div class="file-details">
                    <el-tag size="small" type="info" class="mime-tag">{{ currentFileInfo?.mime_type }}</el-tag>
                    <span class="file-size">{{ formatFileSize(currentFileInfo?.size || 0) }}</span>
                  </div>
                  <div class="file-actions">
                    <a :href="fileDownloadUrl" target="_blank" class="download-link">
                      <el-button type="primary" link icon="Download">
                        {{ t('resource.editor.downloadFile') }}
                      </el-button>
                    </a>
                  </div>
                  <p v-if="resource.kb_id" class="kb-badge">
                    <el-tag size="small" type="warning" effect="plain">{{ t('resource.editor.kbLinked') }}</el-tag>
                  </p>
                </div>

                <el-divider class="compact-divider" />

                <!-- Upload Actions (Restored from original) -->
                <div class="upload-actions compact-upload">
                  <el-upload
                    class="upload-demo"
                    action="#"
                    :auto-upload="false"
                    :show-file-list="false"
                    :on-change="handleFileChange"
                    :disabled="isUploading"
                  >
                    <template #trigger>
                      <el-button type="primary" :loading="isUploading" plain>
                        <el-icon class="el-icon--left"><Upload /></el-icon>
                        {{ t('resource.editor.uploadNew') }}
                      </el-button>
                    </template>
                  </el-upload>
                  <div class="upload-tip">
                    {{ t('resource.editor.uploadAutoVersion') }}<br />
                    <span v-if="resource.kb_id" class="warning-text">
                      {{ t('resource.editor.kbWarning') }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- Right: Editor Area -->
              <div class="file-editor-wrapper" v-loading="isFileContentLoading">
                <ResourceUniversalEditor
                  v-model="editableFileContent"
                  language="plaintext"
                  :monaco-options="editorOptions"
                />
              </div>
            </div>

            <!-- Sub-case A2: Non-editable File (Original Layout) -->
            <template v-else>
              <!-- Sub-case A2.1: File Exists (Show Info/Preview) -->
              <div v-if="currentFileInfo" class="file-info-card">
                <!-- Image Preview -->
                <div v-if="isImage" class="file-preview-image">
                  <el-image
                    :src="fileDownloadUrl"
                    :preview-src-list="[fileDownloadUrl]"
                    fit="contain"
                    class="preview-img"
                  >
                    <template #error>
                      <div class="image-slot">
                        <el-icon><Picture /></el-icon>
                        <span>{{ t('resource.editor.imageLoadError') }}</span>
                      </div>
                    </template>
                  </el-image>
                </div>

                <!-- Generic File Icon -->
                <div v-else class="file-preview-icon">
                  <el-icon :size="64"><Document /></el-icon>
                </div>

                <div class="file-meta-content">
                  <h3 class="file-name" :title="currentFileInfo.filename">
                    {{ currentFileInfo.filename }}
                  </h3>
                  <div class="file-details">
                    <el-tag size="small" type="info">{{ currentFileInfo.mime_type }}</el-tag>
                    <span class="file-size">{{ formatFileSize(currentFileInfo.size) }}</span>
                  </div>
                  <div class="file-actions">
                    <a :href="fileDownloadUrl" target="_blank" class="download-link">
                      <el-button type="primary" link icon="Download">
                        {{ t('resource.editor.downloadFile') }}
                      </el-button>
                    </a>
                  </div>
                  <p v-if="resource.kb_id" class="kb-badge">
                    <el-tag size="small" type="warning" effect="plain">{{ t('resource.editor.kbLinked') }}</el-tag>
                  </p>
                </div>
              </div>

              <!-- Sub-case A2.2: No File (Empty State) -->
              <div v-else class="file-empty-state">
                <el-icon :size="64" class="empty-icon"><DocumentAdd /></el-icon>
                <p class="empty-text">{{ t('resource.editor.noFile') }}</p>
                <p class="empty-subtext">{{ t('resource.editor.uploadPrompt') }}</p>
              </div>

              <!-- Upload Action Area (Only for non-editable or empty) -->
              <div class="upload-actions">
                <el-upload
                  class="upload-demo"
                  action="#"
                  :auto-upload="false"
                  :show-file-list="false"
                  :on-change="handleFileChange"
                  :disabled="isUploading"
                >
                  <template #trigger>
                    <el-button type="primary" :loading="isUploading">
                      <el-icon class="el-icon--left"><Upload /></el-icon>
                      {{ currentFileInfo ? t('resource.editor.uploadNew') : t('resource.editor.uploadFile') }}
                    </el-button>
                  </template>
                </el-upload>
                <div class="upload-tip">
                  <template v-if="currentFileInfo">
                    {{ t('resource.editor.uploadAutoVersion') }}<br />
                    <span v-if="resource.kb_id" class="warning-text">
                      {{ t('resource.editor.kbWarning') }}
                    </span>
                  </template>
                  <template v-else> {{ t('resource.editor.uploadTip') }} </template>
                </div>
              </div>
            </template>
          </div>

          <!-- Case B: Text Resource (Prompt/Template) -->
          <template v-else>
            <div class="content-header">
              <span class="content-label">{{ contentEditorLabel }}</span>
            </div>
            <el-form-item prop="content" class="content-form-item">
              <div class="monaco-wrapper">
                <ResourceUniversalEditor
                  v-model="form.content"
                  :language="editorLanguage"
                  :monaco-options="editorOptions"
                />
              </div>
            </el-form-item>
          </template>
        </template>

        <div v-else class="folder-placeholder">
          <el-empty :description="t('resource.editor.folderNoContent')" :image-size="100" />
        </div>

        <!-- Footer Actions -->
        <div
          class="editor-footer"
          v-if="resource.itemType === 'resource' && (resource.resourceType !== 'file' || isEditableFile)"
        >
          <el-button @click="resetForm">{{ t('resource.editor.reset') }}</el-button>
          <el-button type="success" @click="openNewVersionDialog">{{ t('resource.editor.saveAsNew') }}</el-button>
          <el-button type="primary" @click="handleSaveChanges" :disabled="!isFormDirty">
            {{ t('common.action.save') }}
          </el-button>
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

  <el-dialog v-model="newVersionDialog.visible" :title="t('resource.dialog.saveAsNewTitle')" width="500px">
    <el-form :model="newVersionDialog.form" label-position="top" ref="newVersionFormRef">
      <el-form-item
        :label="t('resource.dialog.versionName')"
        prop="name"
        :rules="{ required: true, message: t('resource.dialog.versionNameRequired'), trigger: 'blur' }"
      >
        <el-input v-model="newVersionDialog.form.name" :placeholder="t('resource.dialog.versionNamePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('resource.dialog.commitMessage')" prop="commitMessage">
        <el-input
          v-model="newVersionDialog.form.commitMessage"
          type="textarea"
          :placeholder="t('resource.dialog.commitPlaceholder')"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newVersionDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirmNewVersion">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type UploadFile } from 'element-plus'
import { Document, Upload, Picture, DocumentAdd, EditPen, Select } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import type { editor } from 'monaco-editor'

import { useResourceStore } from '@/stores/resourceStore'
import { uploadResourceFile } from '@/api/kbService'
import type { ResourceWithVersions, ResourceVersion, ResourceVersionCreate } from '@/api/types'
import ResourceVersionBar from './ResourceVersionBar.vue'
import ResourceMetaSidebar from './ResourceMetaSidebar.vue'
import KnowledgeBaseFileDetail from '../kb/KnowledgeBaseFileDetail.vue'
import ResourceUniversalEditor from '@/components/common/ResourceUniversalEditor.vue'

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

const contentEditorLabel = computed(() => {
  if (loadedVersionInEditor.value) {
    return t('resource.editor.viewing', { name: loadedVersionInEditor.value.name })
  }
  return t('resource.editor.currentVersion')
})

const editorLanguage = computed(() => {
  if (form.name.endsWith('.json')) {
    return 'json'
  }
  return 'markdown'
})

const editorOptions = computed<editor.IStandaloneEditorConstructionOptions>(() => ({
  minimap: { enabled: true },
  lineNumbers: 'on',
  lineNumbersMinChars: 2,
  lineDecorationsWidth: 0,
  folding: true,
  wordWrap: 'on',
  scrollBeyondLastLine: false,
  renderLineHighlight: 'all',
  fontSize: 14,
  fontFamily: 'var(--el-font-family)',
}))

watch(
  () => props.resource,
  (newSelection, oldSelection) => {
    if (newSelection) {
      if (newSelection.id !== oldSelection?.id) {
        resetForm()
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
  { immediate: true },
)

watch(currentVersion, (newVersion) => {
  if (newVersion && isEditableFile.value) {
    loadFileContent()
  }
})

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
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

  if (version.file_info?.editable) {
    loadFileContent()
  }

  if (viewMode.value !== 'editor') {
    viewMode.value = 'editor'
  }
}

async function handleSetActiveVersion(versionId: string) {
  if (!props.resource) return
  try {
    await ElMessageBox.confirm(
      t('resource.version.confirmActive'),
      t('resource.tree.moveWarningTitle'),
      {
        confirmButtonText: t('common.action.confirm'),
        cancelButtonText: t('common.action.cancel'),
        type: 'info',
      }
    )
    await resourceStore.setActiveResourceVersion(props.resource.id, versionId)
    ElMessage.success(t('resource.version.switchSuccess'))
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
.editor-container {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
}

.kb-config-view {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: #fff;
}

.kb-detail-wrapper {
  flex: 1;
  min-height: 0;
  position: relative;
  width: 100%;
}

.editor-split-layout {
  flex-grow: 1;
  display: flex;
  min-height: 0;
}

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

.monaco-wrapper {
  width: 100%;
  height: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  background-color: #ffffff;
  padding: 0 6px;
}

.monaco-wrapper :deep(.simple-textarea .el-textarea__inner) {
  border: none !important;
  box-shadow: none !important;
  padding: 8px 2px;
  background-color: transparent;
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

.file-uploader-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px;
  gap: 32px;
  overflow-y: auto;
}

.file-uploader-area.is-editable-layout {
  padding: 20px;
}

/* Editable File Layout */
.editable-file-layout {
  display: flex;
  width: 100%;
  height: 100%;
  gap: 20px;
  align-items: stretch;
}

.file-info-compact {
  flex: 0 0 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-fill-color-lighter);
  height: fit-content;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.02);
}

.file-preview-icon.compact {
  width: 80px;
  height: 80px;
  position: relative;
  margin-bottom: 12px;
}

.editable-badge {
  position: absolute;
  bottom: 0;
  right: 0;
  background-color: var(--el-color-success);
  color: white;
  border-radius: 50%;
  width: 26px;
  height: 26px;
  display: flex;
  justify-content: center;
  align-items: center;
  border: 2px solid white;
  cursor: help;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.editable-status-text {
  font-size: 12px;
  color: var(--el-color-success);
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: -4px;
}

.compact-divider {
  margin: 16px 0;
  width: 100%;
}

.compact-upload {
  width: 100%;
}

.compact-upload .upload-tip {
  margin-top: 8px;
}

.file-editor-wrapper {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background-color: #fff;
  padding: 0 6px;
}

/* Non-editable File Styles */
.file-info-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 24px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background-color: var(--el-fill-color-lighter);
  width: 100%;
  max-width: 400px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.file-preview-image {
  width: 100%;
  height: 200px;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #fff;
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
  overflow: hidden;
}

.preview-img {
  width: 100%;
  height: 100%;
}

.file-preview-icon {
  width: 120px;
  height: 120px;
  display: flex;
  justify-content: center;
  align-items: center;
  color: var(--el-text-color-secondary);
  background-color: #fff;
  border-radius: 50%;
}

.file-meta-content {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.file-name {
  margin: 0;
  font-size: 16px;
  color: var(--el-text-color-primary);
  text-align: center;
  word-break: break-all;
}

.file-details {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}

.mime-tag {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.file-actions {
  margin-top: 8px;
}

.download-link {
  text-decoration: none;
}

.file-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: var(--el-text-color-placeholder);
}

.empty-icon {
  margin-bottom: 16px;
  color: var(--el-text-color-secondary);
}

.empty-text {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 8px 0;
  color: var(--el-text-color-regular);
}

.empty-subtext {
  font-size: 13px;
  margin: 0;
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

.warning-text {
  color: var(--el-color-warning);
}

.image-slot {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 12px;
  flex-direction: column;
  gap: 8px;
}
</style>
