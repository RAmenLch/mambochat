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
      <el-container v-if="selectorMode === 'resource'" class="resource-selector-container">
        <ResourceSelectorSidebar
          v-model:selected-resources="selectedResources"
          v-model:is-preview-loading="isPreviewLoading"
          v-model:selector-mode="selectorMode"
          :context-config="contextConfig"
        />

        <ResourceSelectorPreview
          :selected-resources="selectedResources"
          :is-preview-loading="isPreviewLoading"
        />
      </el-container>

      <KnowledgeBaseSearchDialog
        v-else
        @cancel="selectorMode = 'resource'"
        @confirm="handleKBSelection"
      />
    </div>

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
import KnowledgeBaseSearchDialog from '@/components/chat/dialogs/KnowledgeBaseSearchDialog.vue';

const props = defineProps<{
  visible: boolean;
  context: 'chat-settings' | 'chat-toolbar' | 'agent-toolbar' | 'agent-react' | 'agent-deep';
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'mount-resources', resources: Resource[]): void;
  (e: 'append-resources', resources: Resource[]): void;
  (e: 'mount-knowledge-base', resources: Resource[]): void;
}>();

const selectorMode = ref<'resource' | 'kb'>('resource');
const selectedResources = ref<Resource[]>([]);
const isPreviewLoading = ref(false);

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
    case 'agent-toolbar':
      return {
        allowedTypes: ['system_prompt', 'submessage_template', 'file'],
        canMount: ['submessage_template', 'file'],
        canAppend: ['system_prompt', 'submessage_template'],
        canMountKb: []
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

watch(() => props.visible, (isVisible) => {
  if (isVisible) {
    selectorMode.value = 'resource';
  }
});

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
  height: 65vh;
}

.resource-selector-container {
  flex-grow: 1;
  display: flex;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background-color: var(--el-bg-color);
}

.action-buttons {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 16px;
}
</style>
