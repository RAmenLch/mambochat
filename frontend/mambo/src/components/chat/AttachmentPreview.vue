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
    <transition-group
      v-if="attachedResources.length > 0"
      name="list"
      tag="div"
      class="attached-templates-preview"
    >
      <el-tag
        v-for="(resource, index) in attachedResources"
        :key="resource.id"
        closable
        disable-transitions
        type="info"
        class="draggable-tag"
        :class="{ 'is-dragging': draggedIndex === index }"
        draggable="true"
        @dragstart.stop="handleDragStart(index, $event)"
        @dragover.prevent.stop="handleDragOver($event)"
        @drop.stop="handleDrop(index)"
        @dragend="handleDragEnd"
        @close="$emit('remove-resource', resource.id)"
      >
        <!-- 优化：使用 popper-class 控制宽度，使用插槽控制内容格式 -->
        <el-tooltip placement="top" effect="dark" :show-after="300" popper-class="resource-preview-tooltip">
          <template #content>
            <div class="resource-content-preview">
              {{ resource.latest_version?.content || '' }}
            </div>
          </template>
          <span>{{ resource.name }}</span>
        </el-tooltip>
      </el-tag>
    </transition-group>

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
import { computed, ref } from 'vue';
import type { PropType } from 'vue';
import { useI18n } from 'vue-i18n';
import { Document, Picture, Close, Search } from '@element-plus/icons-vue';
import type { FileResponse, Resource } from '@/api/types';

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

// --- Drag and Drop Logic ---
const draggedIndex = ref<number | null>(null);

const handleDragStart = (index: number, event: DragEvent) => {
  draggedIndex.value = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', index.toString());
  }
};

const handleDragOver = (event: DragEvent) => {
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move';
  }
};

const handleDrop = (targetIndex: number) => {
  if (draggedIndex.value === null || draggedIndex.value === targetIndex) {
    return;
  }

  const newResources = [...props.attachedResources];
  const [draggedItem] = newResources.splice(draggedIndex.value, 1);
  newResources.splice(targetIndex, 0, draggedItem);

  emit('update:attachedResources', newResources);
  draggedIndex.value = null;
};

const handleDragEnd = () => {
  draggedIndex.value = null;
};
</script>

<style scoped>
.attachment-preview-wrapper {
  background-color: var(--color-background-soft);
  padding-bottom: 8px;
}

.attached-kb-preview,
.attached-templates-preview {
  padding: 8px 20px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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

/* Drag and Drop Styles */
.draggable-tag {
  cursor: grab;
  transition: all 0.3s ease;
}

.draggable-tag:active {
  cursor: grabbing;
}

.draggable-tag.is-dragging {
  opacity: 0.3;
  background-color: var(--el-color-info-light-8);
  border-style: dashed;
}

/* List Transitions */
.list-move,
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}

.list-leave-active {
  position: absolute;
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

<!-- 非 Scoped 样式，用于控制 Teleport 到 body 的 Tooltip 内容 -->
<style>
/* 设置 Tooltip 气泡的最大宽度 */
.resource-preview-tooltip {
  max-width: 60vw !important;
}

/* 预览内容区域样式 */
.resource-content-preview {
  white-space: pre-wrap;       /* 保留换行和缩进 */
  word-break: break-word;      /* 防止长单词溢出 */
  font-family: monospace;      /* 等宽字体 */
  font-size: 12px;
  line-height: 1.5;
  max-height: 400px;           /* 限制最大高度 */
  overflow-y: auto;            /* 超出滚动 */
  padding-right: 5px;          /* 留出滚动条空间 */
}

/* 自定义滚动条样式 (适配 Dark 主题背景) */
.resource-content-preview::-webkit-scrollbar {
  width: 4px;
}

.resource-content-preview::-webkit-scrollbar-thumb {
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.resource-content-preview::-webkit-scrollbar-thumb:hover {
  background-color: rgba(255, 255, 255, 0.4);
}

.resource-content-preview::-webkit-scrollbar-track {
  background: transparent;
}
</style>
