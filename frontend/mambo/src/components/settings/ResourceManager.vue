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
      @move-success="handleMoveSuccess"
    />

    <!-- Main Panel: Editor Area -->
    <el-main class="resource-editor-panel">
      <template v-if="activeResourceDetails">
        <!-- Case 1: Knowledge Base Configuration (Root Node) -->
        <KnowledgeBaseConfig
          v-if="activeResourceDetails.resourceType === 'knowledge_base'"
          :resource="activeResourceDetails"
          @select-file="handleFileSelected"
        />

        <!-- Case 2: Unified Resource Editor (Files, Prompts, Templates) -->
        <!-- Note: ResourceEditor now handles internal switching for KB files -->
        <ResourceEditor v-else :resource="activeResourceDetails" />
      </template>

      <div v-else class="editor-placeholder">
        <el-empty description="从左侧选择一个资源进行编辑" />
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, type ComputedRef } from 'vue'
import { storeToRefs } from 'pinia'

import { useResourceStore } from '@/stores/resourceStore'
import ResourceTreePanel from './resource/ResourceTreePanel.vue'
import ResourceEditor from './resource/ResourceEditor.vue'
import KnowledgeBaseConfig from './kb/KnowledgeBaseConfig.vue'
import type { Resource, ResourceWithVersions, BaseTreeItem } from '@/api/types'

// --- Store ---
const resourceStore = useResourceStore()
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore)

// --- State ---
const selectedResourceId = ref<string | null>(null)

// --- Computed Properties ---
const treeData = computed(() => resourceTree.value)

const activeResourceDetails: ComputedRef<ResourceWithVersions | null> = computed(() => {
  if (!selectedResourceId.value) return null
  return resources.value.find((r) => r.id === selectedResourceId.value) || null
})

// --- Lifecycle ---
onMounted(() => {
  resourceStore.initializeList()
})

// --- Handlers ---

/**
 * Handles clicks on tree nodes to select a resource for editing.
 */
async function handleNodeClick(data: BaseTreeItem) {
  selectedResourceId.value = data.id

  // Cast to Resource to access resourceType safely
  const resource = data as unknown as Resource
  const isKnowledgeBase = resource.resourceType === 'knowledge_base'

  // Fetch details for standard resources OR knowledge bases (which are technically folders but have config pages)
  if (data.itemType === 'resource' || isKnowledgeBase) {
    await resourceStore.fetchResourceDetails(data.id)
  }
}

/**
 * Handles the event after a new resource or folder is created.
 * Selects the new item in the tree and editor view.
 */
async function handleItemCreated(newItem: Resource) {
  selectedResourceId.value = newItem.id

  const isKnowledgeBase = newItem.resourceType === 'knowledge_base'

  if (newItem.itemType === 'resource' || isKnowledgeBase) {
    // Ensure details are fetched for the new resource to populate the editor.
    await resourceStore.fetchResourceDetails(newItem.id)
  }
}

/**
 * Handles the event after an item is deleted.
 * Clears the editor view if the deleted item was the one being edited.
 */
function handleItemDeleted(deletedId: string) {
  if (selectedResourceId.value === deletedId) {
    selectedResourceId.value = null
  }
}

/**
 * Handles the event after resources are moved successfully.
 * Re-fetches details for the currently selected resource if it was moved.
 */
async function handleMoveSuccess(movedIds: string[]) {
  if (selectedResourceId.value && movedIds.includes(selectedResourceId.value)) {
    await resourceStore.fetchResourceDetails(selectedResourceId.value)
  }
}

/**
 * Handles the 'select-file' event from KnowledgeBaseConfig.
 * Switches the view to the unified editor which will handle the file view.
 * [Fix] Fetches full details to ensure versions and file info are loaded.
 */
async function handleFileSelected(file: Resource) {
  selectedResourceId.value = file.id

  // 关键修复：调用 fetchResourceDetails 获取完整的资源信息（包含 versions 列表）
  // 因为从 KnowledgeBaseConfig 传过来的 file 对象来自 /children 接口，数据不完整
  await resourceStore.fetchResourceDetails(file.id)
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
