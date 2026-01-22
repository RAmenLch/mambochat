<!-- frontend/mambo/src/components/settings/ResourceManager.vue -->
<template>
  <el-container class="resource-manager-container">
    <!-- Left Panel: Resource Tree -->
    <ResourceTreePanel
      :data="treeData"
      :current-id="selectedResourceId"
      :is-loading="isResourcesLoading"
      @node-click="handleNodeClick"
      @item-created="handleItemCreated"
      @item-deleted="handleItemDeleted"
    />

    <!-- Main Panel: Editor Area -->
    <el-main class="resource-editor-panel">
      <template v-if="activeResourceDetails">
        <!-- Case 1: Knowledge Base Configuration -->
        <KnowledgeBaseConfig
          v-if="activeResourceDetails.resourceType === 'knowledge_base'"
          :resource="activeResourceDetails"
          @select-file="handleFileSelected"
        />

        <!-- Case 2: Knowledge Base File Detail -->
        <KnowledgeBaseFileDetail
          v-else-if="isActiveResourceKBFile"
          :resource="activeResourceDetails"
        />

        <!-- Case 3: Standard Resource Editor -->
        <ResourceEditor
          v-else
          :resource="activeResourceDetails"
        />
      </template>

      <div v-else class="editor-placeholder">
        <el-empty description="从左侧选择一个资源进行编辑" />
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, type ComputedRef } from 'vue';
import { storeToRefs } from 'pinia';

import { useResourceStore } from '@/stores/resourceStore';
import ResourceTreePanel from './resource/ResourceTreePanel.vue';
import ResourceEditor from './resource/ResourceEditor.vue';
import KnowledgeBaseConfig from './kb/KnowledgeBaseConfig.vue';
import KnowledgeBaseFileDetail from './kb/KnowledgeBaseFileDetail.vue';
import type { Resource, ResourceWithVersions, BaseTreeItem } from '@/api/types';

// --- Store ---
const resourceStore = useResourceStore();
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore);

// --- State ---
const selectedResourceId = ref<string | null>(null);

// --- Computed Properties ---
const treeData = computed(() => resourceTree.value);

const activeResourceDetails: ComputedRef<ResourceWithVersions | null> = computed(() => {
  if (!selectedResourceId.value) return null;
  return resources.value.find(r => r.id === selectedResourceId.value) || null;
});

/**
 * 辅助函数：向上递归查找当前资源是否属于某个 Knowledge Base
 */
const findKBRoot = (resource: Resource | null): Resource | null => {
  if (!resource) return null;

  // 如果当前资源本身就是 KB，返回它 (虽然这个函数主要用于查父级，但兼容一下)
  if (resource.resourceType === 'knowledge_base') return resource;

  // 如果没有父级，说明已经到了根且不是 KB
  if (!resource.parentId) return null;

  // 在 store 中查找父资源
  const parent = resources.value.find(r => r.id === resource.parentId);
  if (!parent) return null;

  // 如果父级是 KB，找到了
  if (parent.resourceType === 'knowledge_base') return parent;

  // 否则继续向上找
  return findKBRoot(parent);
};

/**
 * 判断当前选中的资源是否为知识库中的文件。
 * 支持多级文件夹嵌套，向上追溯祖先节点。
 */
const isActiveResourceKBFile = computed(() => {
  const current = activeResourceDetails.value;
  if (!current || current.itemType !== 'resource') return false;

  // 查找其所属的 KB 根节点
  const kbRoot = findKBRoot(current);
  return !!kbRoot;
});


// --- Lifecycle ---
onMounted(() => {
  resourceStore.initializeList();
});

// --- Handlers ---

/**
 * Handles clicks on tree nodes to select a resource for editing.
 */
async function handleNodeClick(data: BaseTreeItem) {
  selectedResourceId.value = data.id;

  // Cast to Resource to access resourceType safely
  const resource = data as unknown as Resource;
  const isKnowledgeBase = resource.resourceType === 'knowledge_base';

  // Fetch details for standard resources OR knowledge bases (which are technically folders but have config pages)
  if (data.itemType === 'resource' || isKnowledgeBase) {
    await resourceStore.fetchResourceDetails(data.id);
  }
}

/**
 * Handles the event after a new resource or folder is created.
 * Selects the new item in the tree and editor view.
 */
async function handleItemCreated(newItem: Resource) {
  selectedResourceId.value = newItem.id;

  const isKnowledgeBase = newItem.resourceType === 'knowledge_base';

  if (newItem.itemType === 'resource' || isKnowledgeBase) {
    // Ensure details are fetched for the new resource to populate the editor.
    await resourceStore.fetchResourceDetails(newItem.id);
  }
}

/**
 * Handles the event after an item is deleted.
 * Clears the editor view if the deleted item was the one being edited.
 */
function handleItemDeleted(deletedId: string) {
  if (selectedResourceId.value === deletedId) {
    selectedResourceId.value = null;
  }
}

/**
 * Handles the 'select-file' event from KnowledgeBaseConfig.
 * Switches the view to the file detail editor.
 */
function handleFileSelected(file: Resource) {
  selectedResourceId.value = file.id;
}
</script>

<style scoped>
.resource-manager-container {
  height: 100%;
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  background-color: #fff;
}

.resource-editor-panel {
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.editor-placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
