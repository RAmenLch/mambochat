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
        <!-- Case 1: Knowledge Base Configuration -->
        <KnowledgeBaseConfig
          v-if="activeResourceDetails.resourceType === 'knowledge_base'"
          :resource="activeResourceDetails"
          @select-file="handleFileSelected"
        />

        <!-- Case 2: Skill Overview -->
        <SkillOverview
          v-else-if="activeResourceDetails.resourceType === 'skill'"
          :resource="activeResourceDetails"
          @edit-file="handleFileSelected"
        />

        <!-- Case 3: Unified Resource Editor -->
        <ResourceEditor
          v-else
          :resource="activeResourceDetails"
          :initial-view-mode="initialViewMode"
        />
      </template>

      <div v-else class="editor-placeholder">
        <el-empty :description="t('resource.editor.placeholder')" />
      </div>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, type ComputedRef } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'

import { useResourceStore } from '@/stores/resourceStore'
import ResourceTreePanel from './resource/ResourceTreePanel.vue'
import ResourceEditor from './resource/ResourceEditor.vue'
import KnowledgeBaseConfig from './kb/KnowledgeBaseConfig.vue'
import SkillOverview from './skill/SkillOverview.vue'
import type { Resource, ResourceWithVersions, BaseTreeItem } from '@/api/types'

const { t } = useI18n()

// --- Store ---
const resourceStore = useResourceStore()
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore)

// --- State ---
const selectedResourceId = ref<string | null>(null)
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
 * 处理树节点点击事件
 */
async function handleNodeClick(data: BaseTreeItem) {
  selectedResourceId.value = data.id
  initialViewMode.value = 'editor'

  const resource = data as unknown as Resource
  // Knowledge Base 和 Skill 是特殊文件夹，需要加载详情以展示配置页
  const isSpecialFolder =
    resource.resourceType === 'knowledge_base' || resource.resourceType === 'skill'

  if (data.itemType === 'resource' || isSpecialFolder) {
    await resourceStore.fetchResourceDetails(data.id)
  }
}

/**
 * 处理新资源创建后的事件
 */
async function handleItemCreated(newItem: Resource) {
  // 确保新创建的 ID 被选中
  selectedResourceId.value = newItem.id
  initialViewMode.value = 'editor'

  // 如果是 Skill 或 知识库，需要 fetchDetails 才能显示 Overview 页面
  const isSpecialFolder =
    newItem.resourceType === 'knowledge_base' || newItem.resourceType === 'skill'

  if (newItem.itemType === 'resource' || isSpecialFolder) {
    await resourceStore.fetchResourceDetails(newItem.id)
  }
}

/**
 * 处理项目删除后的事件
 */
function handleItemDeleted(deletedId: string) {
  if (selectedResourceId.value === deletedId) {
    selectedResourceId.value = null
  }
}

/**
 * 处理资源移动后的事件
 */
async function handleMoveSuccess(movedIds: string[]) {
  if (selectedResourceId.value && movedIds.includes(selectedResourceId.value)) {
    await resourceStore.fetchResourceDetails(selectedResourceId.value)
  }
}

/**
 * 处理文件选择事件，切换到编辑器视图
 */
async function handleFileSelected(file: Resource, viewMode: 'editor' | 'kb_config' = 'kb_config') {
  selectedResourceId.value = file.id
  initialViewMode.value = viewMode // 使用传入的模式
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
