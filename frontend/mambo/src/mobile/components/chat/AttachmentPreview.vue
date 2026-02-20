<!-- frontend/mambo/src/mobile/components/chat/AttachmentPreview.vue -->
<template>
  <div class="mobile-attachment-preview">
    <!-- Knowledge Bases -->
    <div v-if="attachedKnowledgeBases.length > 0" class="preview-section">
      <div class="preview-list horizontal">
        <div v-for="kb in attachedKnowledgeBases" :key="kb.id" class="preview-tag kb">
          <el-icon class="tag-icon"><Search /></el-icon>
          <span class="tag-name">{{ kb.name }}</span>
          <el-icon class="remove-icon" @click="$emit('remove-knowledge-base', kb.id)"
            ><Close
          /></el-icon>
        </div>
      </div>
    </div>

    <!-- Resources (Templates) -->
    <div v-if="attachedResources.length > 0" class="preview-section">
      <div class="preview-list horizontal">
        <div v-for="resource in attachedResources" :key="resource.id" class="preview-tag resource">
          <span class="tag-name">{{ resource.name }}</span>
          <el-icon class="remove-icon" @click="$emit('remove-resource', resource.id)"
            ><Close
          /></el-icon>
        </div>
      </div>
    </div>

    <!-- Uploaded Files -->
    <div v-if="uploadedFiles.length > 0" class="preview-section">
      <div class="preview-list horizontal scrollable">
        <div v-for="file in uploadedFiles" :key="file.id" class="file-card">
          <el-image
            v-if="file.mime_type.startsWith('image/')"
            :src="file.url"
            fit="cover"
            class="file-image"
          >
            <template #error>
              <div class="image-error">
                <el-icon><Picture /></el-icon>
              </div>
            </template>
          </el-image>
          <div v-else class="file-icon-wrapper">
            <el-icon class="file-icon"><Document /></el-icon>
          </div>
          <div class="file-info">
            <span class="file-name">{{ file.filename }}</span>
          </div>
          <el-button
            class="remove-file-btn"
            :icon="Close"
            circle
            size="small"
            @click="$emit('remove-file', file.id)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { FileResponse, Resource } from '@/api/types'
import { Document, Picture, Close, Search } from '@element-plus/icons-vue'

defineProps({
  uploadedFiles: {
    type: Array as PropType<FileResponse[]>,
    required: true,
  },
  attachedResources: {
    type: Array as PropType<Resource[]>,
    required: true,
  },
  attachedKnowledgeBases: {
    type: Array as PropType<Resource[]>,
    default: () => [],
  },
})

defineEmits<{
  (e: 'remove-file', fileId: string): void
  (e: 'remove-resource', resourceId: string): void
  (e: 'remove-knowledge-base', resourceId: string): void
}>()
</script>

<style scoped>
.mobile-attachment-preview {
  padding-top: 8px;
  padding-bottom: 4px;
  background-color: var(--color-background);
  border-bottom: 1px solid var(--color-border-light);
}

.preview-section {
  margin-bottom: 6px;
}

.preview-section:last-child {
  margin-bottom: 0;
}

.preview-list {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-list.scrollable {
  overflow-x: auto;
  padding-bottom: 4px; /* Space for scrollbar */
}

.preview-tag {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  flex-shrink: 0;
  position: relative;
}

.preview-tag.kb {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.preview-tag.resource {
  background-color: var(--el-color-info-light-9);
  color: var(--el-color-info);
}

.tag-icon {
  margin-right: 4px;
  font-size: 12px;
}

.tag-name {
  max-width: 100px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-icon {
  margin-left: 6px;
  font-size: 12px;
  cursor: pointer;
  opacity: 0.7;
}

.remove-icon:active {
  opacity: 1;
}

/* File Cards */
.file-card {
  position: relative;
  width: 70px;
  height: 70px;
  border-radius: 6px;
  overflow: hidden;
  background-color: var(--color-background-soft);
  border: 1px solid var(--color-border-light);
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.file-image {
  width: 100%;
  height: 100%;
}

.image-error {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--el-fill-color-light);
}

.file-icon-wrapper {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}

.file-icon {
  font-size: 24px;
  color: var(--el-text-color-placeholder);
}

.file-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 4px;
}

.file-name {
  display: block;
  font-size: 10px;
  color: white;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.remove-file-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  border: none;
}

.remove-file-btn:active {
  background: rgba(0, 0, 0, 0.7);
}
</style>
