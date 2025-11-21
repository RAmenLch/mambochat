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
      <ResourceEditor v-if="activeResourceDetails" :resource="activeResourceDetails" />
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
  // The store's `resources` array is of type ResourceWithVersions[], so this is safe.
  return resources.value.find(r => r.id === selectedResourceId.value) || null;
});

// --- Lifecycle ---
onMounted(() => {
  resourceStore.fetchResources();
});

// --- Handlers ---

/**
 * Handles clicks on tree nodes to select a resource for editing.
 */
async function handleNodeClick(data: BaseTreeItem) {
  selectedResourceId.value = data.id;
  if (data.itemType === 'resource') {
    // Ensure the full details including all versions are loaded.
    await resourceStore.fetchResourceDetails(data.id);
  }
}

/**
 * Handles the event after a new resource or folder is created.
 * Selects the new item in the tree and editor view.
 */
async function handleItemCreated(newItem: Resource) {
  selectedResourceId.value = newItem.id;
  if (newItem.itemType === 'resource') {
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
