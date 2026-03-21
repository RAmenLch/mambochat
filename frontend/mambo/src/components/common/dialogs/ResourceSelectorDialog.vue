<!-- frontend/mambo/src/components/common/dialogs/ResourceSelectorDialog.vue -->
<template>
  <el-dialog
    :model-value="visible"
    :title="$t('resource.selector.title')"
    width="70%"
    @update:model-value="val => emit('update:visible', val)"
    @close="handleDialogClose"
  >
    <div class="resource-selector-body">
      <!-- 模式 A: 资源浏览与选择 -->
      <el-container v-if="selectorMode === 'resource'" class="resource-selector-container">
        <!-- 左侧：侧边栏 (树形/搜索) -->
        <ResourceSelectorSidebar
          v-model:selected-resources="selectedResources"
          v-model:is-preview-loading="isPreviewLoading"
          v-model:selector-mode="selectorMode"
          :context-config="contextConfig"
        />

        <!-- 右侧：预览区 -->
        <ResourceSelectorPreview
          :selected-resources="selectedResources"
          :is-preview-loading="isPreviewLoading"
        />
      </el-container>

      <!-- 模式 B: 知识库向量检索 -->
      <KnowledgeBaseSearchDialog
        v-else
        @cancel="selectorMode = 'resource'"
        @confirm="handleKBSelection"
      />
    </div>

    <!-- Footer: 仅在资源模式下显示 -->
    <template #footer v-if="selectorMode === 'resource'">
      <div class="action-buttons">
        <el-button
          v-if="showKbSearchButton"
          type="primary"
          :icon="Search"
          plain
          @click="handleMountKnowledgeBase"
        >
          {{ $t('resource.action.mountKbSearch') }}
        </el-button>

        <el-button
          v-if="showAppendButton"
          type="default"
          @click="handleAppend"
          :disabled="selectedResources.length === 0"
        >
          {{ $t('resource.action.append', { count: selectedResources.length }) }}
        </el-button>

        <el-button
          v-if="showMountButton"
          type="primary"
          @click="handleMount"
          :disabled="selectedResources.length === 0"
        >
          {{ $t('resource.action.mount', { count: selectedResources.length }) }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { Search } from '@element-plus/icons-vue';
import type { Resource, KBSearchResultItem } from '@/api/types';
import ResourceSelectorSidebar from './ResourceSelectorSidebar.vue';
import ResourceSelectorPreview from './ResourceSelectorPreview.vue';
import KnowledgeBaseSearchDialog from '@/components/chat/dialogs/KnowledgeBaseSearchDialog.vue'; // 保持原路径或根据实际情况调整

const props = defineProps<{
  visible: boolean;
  context: 'chat-settings' | 'chat-toolbar' | 'agent-react' | 'agent-deep';
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'mount-resources', resources: Resource[]): void;
  (e: 'append-resources', resources: Resource[]): void;
  (e: 'mount-knowledge-base', resources: Resource[]): void;
}>();

// --- State ---
const selectorMode = ref<'resource' | 'kb'>('resource');
const selectedResources = ref<Resource[]>([]);
const isPreviewLoading = ref(false);

// --- Context Configuration Logic ---
const contextConfig = computed(() => {
  switch (props.context) {
    case 'chat-settings':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base'],
        canMount: ['system_prompt', 'submessage_template'],
        canAppend: [],
        canMountKb: ['knowledge_base']
      };
    case 'chat-toolbar':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'file', 'knowledge_base'],
        canMount: ['submessage_template', 'file'],
        canAppend: ['system_prompt', 'submessage_template'],
        canMountKb: ['knowledge_base']
      };
    case 'agent-react':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base'],
        canMount: ['system_prompt', 'submessage_template', 'knowledge_base'],
        canAppend: [],
        canMountKb: []
      };
    case 'agent-deep':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'knowledge_base', 'skill'],
        canMount: ['system_prompt', 'submessage_template', 'knowledge_base', 'skill'],
        canAppend: [],
        canMountKb: []
      };
    default:
      return { allowedTypes: [], canMount: [], canAppend: [], canMountKb: [] };
  }
});

// --- Button Display Logic ---
const showMountButton = computed(() => {
  if (selectedResources.value.length === 0) return false;
  return selectedResources.value.every(r => contextConfig.value.canMount.includes(r.resourceType as string));
});

const showAppendButton = computed(() => {
  if (selectedResources.value.length === 0) return false;
  return selectedResources.value.every(r => contextConfig.value.canAppend.includes(r.resourceType as string));
});

const showKbSearchButton = computed(() => {
  if (selectorMode.value !== 'resource' || selectedResources.value.length === 0) return false;
  return selectedResources.value.every(r => contextConfig.value.canMountKb.includes(r.resourceType as string));
});

// --- Watchers ---
watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    selectorMode.value = 'resource';
  }
});

// --- Action Handlers ---
function handleMount() {
  if (selectedResources.value.length === 0) return;
  emit('mount-resources', selectedResources.value);
  emit('update:visible', false);
}

function handleAppend() {
  if (selectedResources.value.length === 0) return;
  emit('append-resources', selectedResources.value);
  emit('update:visible', false);
}

function handleMountKnowledgeBase() {
  if (selectedResources.value.length === 0) return;
  emit('mount-knowledge-base', selectedResources.value);
  emit('update:visible', false);
}

const handleKBSelection = (items: KBSearchResultItem[]) => {
  const resources: Resource[] = items.map(item => ({
    id: item.chunk_id,
    name: `片段: ${item.resource_name}`,
    description: `来自知识库: ${item.kb_name} (相似度: ${item.score.toFixed(4)})`,
    itemType: 'resource',
    resourceType: 'knowledge_base_chunk',
    parentId: item.kb_id,
    sortOrder: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    latest_version: {
      id: item.chunk_id,
      resourceId: item.chunk_id,
      name: 'v1',
      commitMessage: null,
      content: item.chunk_content,
      attributes: { score: item.score },
      sortOrder: 0,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      file_info: null
    },
    kb_id: null,
    kb_config: null
  }));

  emit('append-resources', resources);
  emit('update:visible', false);
};

function handleDialogClose() {
  selectedResources.value = [];
  isPreviewLoading.value = false;
  selectorMode.value = 'resource';
}
</script>

<style scoped>
.resource-selector-body {
  display: flex;
  flex-direction: column;
  height: 60vh;
}
.resource-selector-container {
  flex-grow: 1;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
}
.action-buttons {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
</style>
