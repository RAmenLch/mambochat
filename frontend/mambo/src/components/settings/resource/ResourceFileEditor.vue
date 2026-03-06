<!-- frontend/mambo/src/components/settings/resource/ResourceFileEditor.vue -->
<template>
  <div class="file-uploader-area" :class="{ 'is-editable-layout': isEditable }">
    <!-- Case 1: Editable File -->
    <div v-if="isEditable" class="editable-file-layout">
      <!-- Left: Compact Info -->
      <div class="file-info-compact">
        <div class="file-preview-icon compact">
          <el-icon :size="56"><Document /></el-icon>
          <el-tooltip content="Editable file" placement="top" effect="dark">
            <div class="editable-badge"><el-icon><EditPen /></el-icon></div>
          </el-tooltip>
        </div>

        <div class="file-meta-content">
          <h3 class="file-name" :title="fileInfo?.filename">{{ fileInfo?.filename }}</h3>
          <div class="file-details">
            <el-tag size="small" type="info">{{ fileInfo?.mime_type }}</el-tag>
            <span class="file-size">{{ formatFileSize(fileInfo?.size || 0) }}</span>
          </div>
          <div class="file-actions">
            <a :href="fileInfo?.url" target="_blank" class="download-link">
              <el-button type="primary" link icon="Download">{{t('resource.editor.downloadFile')}}</el-button>
            </a>
          </div>
        </div>

        <el-divider class="compact-divider" />

        <div class="upload-actions compact-upload">
          <el-upload
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="onFileChange"
            :disabled="isUploading"
          >
            <template #trigger>
              <el-button type="primary" :loading="isUploading" plain>
                <el-icon class="el-icon--left"><Upload /></el-icon>
                {{ t('resource.editor.uploadNew') }}
              </el-button>
            </template>
          </el-upload>
        </div>
      </div>

      <!-- Right: Editor -->
      <div class="file-editor-wrapper" v-loading="isLoadingContent">
        <ResourceUniversalEditor
          :model-value="content"
          @update:model-value="$emit('update:content', $event)"
          language="plaintext"
          :monaco-options="editorOptions"
        />
      </div>
    </div>

    <!-- Case 2: Non-editable File -->
    <template v-else>
      <div v-if="fileInfo" class="file-info-card">
        <!-- Image Preview -->
        <div v-if="isImage" class="file-preview-image">
          <el-image
            :src="fileInfo.url"
            :preview-src-list="[fileInfo.url]"
            fit="contain"
            class="preview-img"
          >
            <template #error>
              <div class="image-slot">
                <el-icon><Picture /></el-icon>
                <span>Load failed</span>
              </div>
            </template>
          </el-image>
        </div>

        <!-- Generic File Icon -->
        <div v-else class="file-preview-icon">
          <el-icon :size="64"><Document /></el-icon>
        </div>

        <div class="file-meta-content">
          <h3 class="file-name" :title="fileInfo.filename">{{ fileInfo.filename }}</h3>
          <div class="file-details">
            <el-tag size="small" type="info">{{ fileInfo.mime_type }}</el-tag>
            <span class="file-size">{{ formatFileSize(fileInfo.size) }}</span>
          </div>
          <div class="file-actions">
            <a :href="fileInfo.url" target="_blank" class="download-link">
              <el-button type="primary" link icon="Download">{{t('resource.editor.downloadFile')}}</el-button>
            </a>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="file-empty-state">
        <el-icon :size="64" class="empty-icon"><DocumentAdd /></el-icon>
        <p class="empty-text">No file uploaded</p>
      </div>

      <!-- Upload Action -->
      <div class="upload-actions">
        <el-upload
          action="#"
          :auto-upload="false"
          :show-file-list="false"
          :on-change="onFileChange"
          :disabled="isUploading"
        >
          <template #trigger>
            <el-button type="primary" :loading="isUploading">
              <el-icon class="el-icon--left"><Upload /></el-icon>
              {{ fileInfo ? t('resource.editor.uploadNew') : t('resource.editor.uploadFile')}}
            </el-button>
          </template>
        </el-upload>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document, Upload, Picture, DocumentAdd, EditPen } from '@element-plus/icons-vue'
import type { FileResponse } from '@/api/types'
import ResourceUniversalEditor from '@/components/common/ResourceUniversalEditor.vue'
import type { UploadFile } from 'element-plus'
import {useI18n} from "vue-i18n";
const { t } = useI18n()

// 使用 withDefaults 赋予 isLoadingContent 默认值，解决 TS 报错
const props = withDefaults(defineProps<{
  fileInfo: FileResponse | null
  isUploading: boolean
  isLoadingContent?: boolean
  content: string
  editorOptions: any
}>(), {
  isLoadingContent: false
})

const emit = defineEmits<{
  (e: 'update:content', value: string): void
  (e: 'file-change', file: UploadFile): void
}>()

const isImage = computed(() => {
  const mime = props.fileInfo?.mime_type
  return mime ? mime.startsWith('image/') : false
})

const isEditable = computed(() => props.fileInfo?.editable ?? false)

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const onFileChange = (uploadFile: UploadFile) => {
  emit('file-change', uploadFile)
}
</script>

<style scoped>
/* 样式保持不变 */
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
}

.file-preview-icon.compact {
  width: 80px;
  height: 80px;
  position: relative;
  margin-bottom: 12px;
  display: flex;
  justify-content: center;
  align-items: center;
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
}

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
}

.file-preview-image {
  width: 100%;
  height: 200px;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #fff;
  border-radius: 4px;
  overflow: hidden;
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

.file-size {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.upload-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.file-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  color: var(--el-text-color-placeholder);
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
