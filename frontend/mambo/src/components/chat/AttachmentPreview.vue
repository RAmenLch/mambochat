<!-- frontend/mambo/src/components/chat/AttachmentPreview.vue -->
<template>
  <div v-if="hasAttachments" class="attachment-preview-wrapper">
    <!-- Attached Knowledge Bases Preview Area -->
    <div v-if="attachedKnowledgeBases.length > 0" class="attached-kb-preview">
      <el-tag
        v-for="kb in attachedKnowledgeBases"
        :key="kb.id"
        closable
        disable-transitions
        type="primary"
        class="kb-tag"
        @close="$emit('remove-knowledge-base', kb.id)"
      >
        <div class="kb-tag-content">
          <el-icon class="kb-icon"><Search /></el-icon>
          <el-tooltip :content="kb.description || t('chat.attachment.knowledgeBase')" placement="top">
            <span>{{ kb.name }}</span>
          </el-tooltip>
        </div>
      </el-tag>
    </div>

    <!-- Attached Templates Preview Area -->
    <div v-if="attachedResources.length > 0" class="attached-templates-preview">
      <MountedResourceTags
        :model-value="attachedResources"
        @update:model-value="(val) => $emit('update:attachedResources', val)"
      />
    </div>

    <!-- Uploaded Files Preview Area -->
    <div v-if="uploadedFiles.length > 0" class="uploaded-files-preview">
      <div v-for="file in uploadedFiles" :key="file.id" class="file-item">
        <el-image
          v-if="file.mime_type.startsWith('image/')"
          :src="file.url"
          fit="cover"
          class="file-thumbnail"
        >
          <template #error>
            <div class="image-slot-error">
              <el-icon><Picture /></el-icon>
            </div>
          </template>
        </el-image>
        <div v-else class="file-icon">
          <el-icon><Document /></el-icon>
        </div>
        <span class="file-name" :title="file.filename">{{ file.filename }}</span>
        <el-button
          :icon="Close"
          circle
          text
          class="remove-file-btn"
          @click="$emit('remove-file', file.id)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { PropType } from 'vue';
import { useI18n } from 'vue-i18n';
import { Document, Picture, Close, Search } from '@element-plus/icons-vue';
import type { FileResponse, Resource } from '@/api/types';
import MountedResourceTags from '@/components/common/MountedResourceTags.vue';

const { t } = useI18n();

const props = defineProps({
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
});

const emit = defineEmits<{
  (e: 'remove-file', fileId: string): void;
  (e: 'remove-resource', resourceId: string): void;
  (e: 'remove-knowledge-base', resourceId: string): void;
  (e: 'update:attachedResources', resources: Resource[]): void;
}>();

const hasAttachments = computed(() =>
  props.uploadedFiles.length > 0 ||
  props.attachedResources.length > 0 ||
  props.attachedKnowledgeBases.length > 0
);
</script>

<style scoped>
.attachment-preview-wrapper {
  background-color: var(--color-background-soft);
  padding-bottom: 8px;
}

.attached-kb-preview {
  padding: 8px 20px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.attached-templates-preview {
  padding: 8px 20px 0;
  /* Flex layout handled by MountedResourceTags component */
}

/* Knowledge Base Tag Styles */
.kb-tag-content {
  display: flex;
  align-items: center;
  gap: 4px;
}

.kb-icon {
  font-size: 12px;
}

.uploaded-files-preview {
  padding: 8px 20px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 100px;
  overflow-y: auto;
}
.file-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 4px;
  background-color: var(--color-background);
  border: 1px solid var(--color-border);
  font-size: 13px;
}
.file-thumbnail {
  width: 24px;
  height: 24px;
  border-radius: 3px;
}
.image-slot-error {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.file-icon {
  font-size: 18px;
  color: var(--el-text-color-secondary);
  display: flex;
  align-items: center;
}
.file-name {
  max-width: 150px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.remove-file-btn {
  margin-left: 4px;
  font-size: 14px;
  --el-button-text-color: var(--el-text-color-placeholder);
}
.remove-file-btn:hover {
  --el-button-text-color: var(--el-color-danger);
  background-color: transparent;
}
</style>
