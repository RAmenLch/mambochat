<!-- frontend/mambo/src/components/settings/resource/ResourceEditor.vue -->
<template>
  <div class="editor-container">
    <!-- Top Region: Version History -->
    <ResourceVersionBar
      v-if="resource.itemType === 'resource'"
      :versions="resource.versions || []"
      :active-version-id="resource.latest_version?.id || null"
      :viewing-version-id="loadedVersionInEditor?.id || null"
      :kb-id="resource.kb_id"
      :view-mode="viewMode"
      @select-version="loadVersionIntoEditor"
      @set-active="handleSetActiveVersion"
      @toggle-kb-view="viewMode = 'kb_config'"
      @reorder-versions="handleReorderVersions"
      @delete-version="handleDeleteVersion"
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

          <!-- Case: File Resource (Extracted) -->
          <ResourceFileEditor
            v-if="resource.resourceType === 'file'"
            :file-info="currentFileInfo"
            :is-uploading="isUploading"
            :is-loading-content="isFileContentLoading"
            :content="editableFileContent"
            :editor-options="editorOptions"
            @update:content="editableFileContent = $event"
            @file-change="handleFileChange"
          />

          <!-- Case: Text Resource -->
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
        <div class="editor-footer">
          <el-button @click="resetForm">{{ t('resource.editor.reset') }}</el-button>
          <el-button
            v-if="resource.itemType === 'resource' && (resource.resourceType !== 'file' || isEditableFile)"
            type="success"
            @click="openNewVersionDialog"
          >{{ t('resource.editor.saveAsNew') }}</el-button>
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

  <!-- New Version Dialog -->
  <el-dialog v-model="newVersionDialog.visible" :title="t('resource.dialog.saveAsNewTitle')" width="500px">
    <el-form :model="newVersionDialog.form" label-position="top" ref="newVersionFormRef">
      <el-form-item :label="t('resource.dialog.versionName')" prop="name" :rules="{ required: true, message: t('resource.dialog.versionNameRequired'), trigger: 'blur' }">
        <el-input v-model="newVersionDialog.form.name" :placeholder="t('resource.dialog.versionNamePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('resource.dialog.commitMessage')" prop="commitMessage">
        <el-input v-model="newVersionDialog.form.commitMessage" type="textarea" :placeholder="t('resource.dialog.commitPlaceholder')" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="newVersionDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="handleConfirmNewVersion">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance } from 'element-plus'
import type { editor } from 'monaco-editor'

import { useResourceEditor } from '@/composables/useResourceEditor'
import type { ResourceWithVersions } from '@/api/types'
import ResourceVersionBar from './ResourceVersionBar.vue'
import ResourceMetaSidebar from './ResourceMetaSidebar.vue'
import KnowledgeBaseFileDetail from '../kb/KnowledgeBaseFileDetail.vue'
import ResourceUniversalEditor from '@/components/common/ResourceUniversalEditor.vue'
import ResourceFileEditor from './ResourceFileEditor.vue'

const { t } = useI18n()

const props = defineProps<{
  resource: ResourceWithVersions
  initialViewMode?: 'editor' | 'kb_config'
}>()

// --- Use Composable ---
const {
  form,
  viewMode,
  loadedVersionInEditor,
  currentFileInfo,
  isEditableFile,
  isFormDirty,
  isUploading,
  editableFileContent,
  isFileContentLoading, // 提取加载状态
  newVersionDialog,
  resetForm,
  handleSaveChanges,
  handleFileChange,
  loadVersionIntoEditor,
  handleSetActiveVersion,
  handleReorderVersions,
  handleDeleteVersion,
  openNewVersionDialog,
  handleConfirmNewVersion,
} = useResourceEditor(props)

// --- Local UI State ---
const formRef = ref<FormInstance>()
const newVersionFormRef = ref<FormInstance>()

// --- Computed (UI Specific) ---
const contentEditorLabel = computed(() => {
  if (loadedVersionInEditor.value) {
    return t('resource.editor.viewing', { name: loadedVersionInEditor.value.name })
  }
  return t('resource.editor.currentVersion')
})

const editorLanguage = computed(() => {
  if (form.name.endsWith('.json')) return 'json'
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
</style>
