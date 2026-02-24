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
      closable
      type="info"
      class="draggable-tag"
      :class="{ 'is-dragging': draggedResourceId === resource.id }"
      draggable="true"
      @dragstart="handleDragStart(resource.id, $event)"
      @dragover.prevent="handleDragOver($event)"
      @dragend="handleDragEnd"
      @close="handleRemove(resource.id)"
    >
      <!--
        修复：添加 :disabled="!!draggedResourceId"
        当正在拖拽任意元素时，禁用所有 Tooltip，防止遮挡
      -->
      <el-tooltip
        placement="top"
        effect="dark"
        :show-after="300"
        popper-class="resource-preview-tooltip"
        :disabled="!!draggedResourceId"
      >
        <template #content>
          <div class="resource-content-preview">
            {{ resource.latest_version?.content || '' }}
          </div>
        </template>
        <span class="resource-tag-name">{{ resource.name }}</span>
      </el-tooltip>
    </el-tag>
  </transition-group>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import type { PropType } from 'vue';
import type { Resource } from '@/api/types/resourceTypes';

const props = defineProps({
  modelValue: {
    type: Array as PropType<Resource[]>,
    required: true,
    default: () => [],
  },
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: Resource[]): void;
}>();

const draggedResourceId = ref<string | null>(null);
let lastSwapTime = 0;
const SWAP_THROTTLE_MS = 100;

const handleDragStart = (resourceId: string, event: DragEvent) => {
  draggedResourceId.value = resourceId;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', resourceId);
  }
};

const handleDragOver = (event: DragEvent) => {
  if (!draggedResourceId.value) return;

  // 节流控制
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
  display: inline-block;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 排序动画 */
.list-move {
  transition: transform 0.3s ease;
}

/* 删除动画：直接消失，触发兄弟元素补位 */
.list-leave-active {
  display: none;
}
</style>

<style>
/* 全局样式，用于控制 Teleport 到 body 的 Tooltip 内容 */
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
