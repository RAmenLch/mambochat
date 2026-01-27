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
        <!-- [修改] 传递 initialViewMode prop -->
        <ResourceEditor
          v-else
          :resource="activeResourceDetails"
          :initial-view-mode="initialViewMode"
        />
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
// [新增] 状态：控制 ResourceEditor 的初始视图模式
const initialViewMode = ref<'editor' | 'kb_config'>('editor')

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
  // [修改] 常规点击树节点，默认进入编辑器模式
  initialViewMode.value = 'editor'

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
 */
async function handleItemCreated(newItem: Resource) {
  selectedResourceId.value = newItem.id
  // [修改] 新建资源默认进入编辑器模式
  initialViewMode.value = 'editor'

  const isKnowledgeBase = newItem.resourceType === 'knowledge_base'

  if (newItem.itemType === 'resource' || isKnowledgeBase) {
    await resourceStore.fetchResourceDetails(newItem.id)
  }
}

/**
 * Handles the event after an item is deleted.
 */
function handleItemDeleted(deletedId: string) {
  if (selectedResourceId.value === deletedId) {
    selectedResourceId.value = null
  }
}

/**
 * Handles the event after resources are moved successfully.
 */
async function handleMoveSuccess(movedIds: string[]) {
  if (selectedResourceId.value && movedIds.includes(selectedResourceId.value)) {
    await resourceStore.fetchResourceDetails(selectedResourceId.value)
  }
}

/**
 * Handles the 'select-file' event from KnowledgeBaseConfig.
 * Switches the view to the unified editor which will handle the file view.
 * 这里是"配置任务"按钮的入口，强制进入 kb_config 模式
 */
async function handleFileSelected(file: Resource) {
  selectedResourceId.value = file.id
  // 设置为 kb_config，让 ResourceEditor 打开时直接显示配置页
  initialViewMode.value = 'kb_config'

  // 关键修复：调用 fetchResourceDetails 获取完整的资源信息（包含 versions 列表）
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
