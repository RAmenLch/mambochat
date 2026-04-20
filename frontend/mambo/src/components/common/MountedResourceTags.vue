<!-- frontend/mambo/src/components/common/MountedResourceTags.vue -->
<template>
  <transition-group
    v-if="modelValue.length > 0"
    name="list"
    tag="div"
    class="mounted-resources-area"
  >
    <el-tag
      v-for="resource in modelValue"
      :key="resource.id"
      :data-resource-id="resource.id"
      :closable="!readonly"
      disable-transitions
      :type="colorByType ? getTagType(resource) : 'info'"
      :class="{ 'draggable-tag': !readonly, 'is-dragging': draggedResourceId === resource.id }"
      :draggable="!readonly ? 'true' : 'false'"
      @dragstart="!readonly && handleDragStart(resource.id, $event)"
      @dragover.prevent="!readonly && handleDragOver($event)"
      @dragend="!readonly && handleDragEnd()"
      @close="!readonly && handleRemove(resource.id)"
    >
      <el-tooltip
        placement="top"
        effect="dark"
        :show-after="300"
        popper-class="resource-preview-tooltip"
        :disabled="!!draggedResourceId"
      >
        <template #content>
          <div class="resource-content-preview">
            <div v-if="colorByType" class="preview-type-badge">{{ getResourceTypeLabel(resource) }}</div>
            {{ getPreviewText(resource) }}
          </div>
        </template>
        <span class="resource-tag-name">
          <el-icon v-if="colorByType" class="tag-type-icon">
            <component :is="getTagIcon(resource)" />
          </el-icon>
          {{ resource.name }}
        </span>
      </el-tooltip>
    </el-tag>
  </transition-group>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { PropType, Component } from 'vue';
import { Search, Document, Memo, Tickets, Reading } from '@element-plus/icons-vue';
import type { Resource } from '@/api/types/resourceTypes';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

const props = defineProps({
  modelValue: {
    type: Array as PropType<Resource[]>,
    required: true,
    default: () => [],
  },
  colorByType: {
    type: Boolean,
    default: false,
  },
  readonly: {
    type: Boolean,
    default: false,
  }
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: Resource[]): void;
}>();

const draggedResourceId = ref<string | null>(null);
let lastSwapTime = 0;
const SWAP_THROTTLE_MS = 100;

// --- Color-by-type helpers ---

type ElTagType = 'success' | 'warning' | 'info' | 'danger' | 'primary';

function getTagType(resource: Resource): ElTagType {
  switch (resource.resourceType) {
    case 'knowledge_base': return 'primary';
    case 'system_prompt': return 'success';
    case 'submessage_template': return 'warning';
    case 'skill': return 'danger';
    case 'file': return 'info';
    default: return 'info';
  }
}

function getTagIcon(resource: Resource): Component {
  switch (resource.resourceType) {
    case 'knowledge_base': return Search;
    case 'system_prompt': return Document;
    case 'submessage_template': return Memo;
    case 'skill': return Reading; // [修改] 使用 Reading 图标
    case 'file': return Tickets;
    default: return Document;
  }
}

function getResourceTypeLabel(resource: Resource): string {
  switch (resource.resourceType) {
    case 'knowledge_base': return t('resource.types.knowledge_base');
    case 'system_prompt': return t('resource.types.system_prompt');
    case 'submessage_template': return t('resource.types.submessage_template');
    case 'skill': return t('resource.types.skill');
    case 'file': return t('resource.types.file');
    default: return resource.resourceType || t('resource.types.unknown');
  }
}

function getPreviewText(resource: Resource): string {
  if (resource.resourceType === 'knowledge_base') {
    return resource.description || t('resource.selector.kbMountContent');
  }
  if (resource.resourceType === 'skill') {
    return resource.description || t('resource.skill.descPlaceholder');
  }
  if (resource.resourceType === 'file') {
    const fileInfo = resource.latest_version?.file_info;
    if (fileInfo) {
      const size = fileInfo.size;
      const sizeStr = size < 1024 ? `${size} B` : size < 1048576 ? `${(size / 1024).toFixed(1)} KB` : `${(size / 1048576).toFixed(1)} MB`;
      return `${fileInfo.filename} (${sizeStr})`;
    }
    return `(${t('common.status.noData')})`;
  }
  const content = resource.latest_version?.content;
  if (!content) return `(${t('common.status.noData')})`;
  return content.length > 500 ? content.substring(0, 500) + '...' : content;
}

// --- Drag & Drop ---

const handleDragStart = (resourceId: string, event: DragEvent) => {
  draggedResourceId.value = resourceId;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', resourceId);
  }
};

const handleDragOver = (event: DragEvent) => {
  if (!draggedResourceId.value) return;

  const now = Date.now();
  if (now - lastSwapTime < SWAP_THROTTLE_MS) return;

  const target = event.target as HTMLElement;
  const targetTag = target.closest('.draggable-tag') as HTMLElement | null;

  if (!targetTag) return;

  const targetResourceId = targetTag.dataset.resourceId;
  if (!targetResourceId || targetResourceId === draggedResourceId.value) return;

  const list = [...props.modelValue];
  const draggedIndex = list.findIndex(r => r.id === draggedResourceId.value);
  const targetIndex = list.findIndex(r => r.id === targetResourceId);

  if (draggedIndex !== -1 && targetIndex !== -1) {
    const [draggedItem] = list.splice(draggedIndex, 1);
    list.splice(targetIndex, 0, draggedItem);
    emit('update:modelValue', list);
    lastSwapTime = now;
  }
};

const handleDragEnd = () => {
  draggedResourceId.value = null;
  lastSwapTime = 0;
};

const handleRemove = (resourceId: string) => {
  const newList = props.modelValue.filter(r => r.id !== resourceId);
  emit('update:modelValue', newList);
};
</script>

<style scoped>
.mounted-resources-area {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.draggable-tag {
  cursor: grab;
  transition: transform 0.3s ease;
  user-select: none;
}

.draggable-tag:active {
  cursor: grabbing;
}

.draggable-tag.is-dragging {
  opacity: 0.3;
  background-color: var(--el-color-info-light-8);
  border-style: dashed;
}

.resource-tag-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-type-icon {
  font-size: 12px;
  flex-shrink: 0;
}

.list-move {
  transition: transform 0.3s ease;
}

.list-leave-active {
  display: none;
}
</style>

<style>
.resource-preview-tooltip {
  max-width: 60vw !important;
}

.resource-content-preview {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: monospace;
  font-size: 12px;
  line-height: 1.5;
  max-height: 400px;
  overflow-y: auto;
  padding-right: 5px;
}

.preview-type-badge {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.15);
}

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
