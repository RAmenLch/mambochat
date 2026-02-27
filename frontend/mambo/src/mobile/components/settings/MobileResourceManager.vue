<!-- frontend/mambo/src/mobile/components/settings/MobileResourceManager.vue -->
<template>
  <div class="mobile-resource-manager">
    <!-- View 1: Resource List (Tree) -->
    <transition name="slide-left">
      <div v-if="viewMode === 'list'" class="list-view-container">
        <MobileResourceTreePanel
          :data="treeData"
          :current-id="selectedResourceId"
          :is-loading="isResourcesLoading"
          @node-click="handleNodeClick"
          @item-created="handleItemCreated"
          @item-deleted="handleItemDeleted"
        />
      </div>
    </transition>

    <!-- View 2: Resource Detail (Editor/Config) -->
    <transition name="slide-right">
      <div v-if="viewMode === 'detail' && activeResourceDetails" class="detail-view-container">
        <!-- Detail Header -->
        <div class="detail-header">
          <el-button link :icon="ArrowLeft" @click="handleBackToList" class="back-btn">
            {{ t('common.action.back') }}
          </el-button>
          <span class="title">{{ activeResourceDetails.name }}</span>
          <span class="placeholder"></span>
        </div>

        <!-- Detail Content -->
        <div class="detail-content">
          <!-- Case 1: Knowledge Base Configuration -->
          <MobileKnowledgeBaseConfig
            v-if="activeResourceDetails.resourceType === 'knowledge_base'"
            :resource="activeResourceDetails"
            @select-file="handleSelectFile"
          />

          <!-- Case 2: Standard Resource Editor -->
          <MobileResourceEditor
            v-else
            :resource="activeResourceDetails"
            :initial-view-mode="initialViewMode"
          />
        </div>
      </div>

      <!-- Loading / Empty State for Detail View -->
      <div v-else-if="viewMode === 'detail'" class="detail-view-container loading-state">
        <div class="detail-header">
          <el-button link :icon="ArrowLeft" @click="handleBackToList" class="back-btn">
            {{ t('common.action.back') }}
          </el-button>
          <span class="title">...</span>
          <span class="placeholder"></span>
        </div>
        <el-skeleton :rows="10" animated />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { ArrowLeft } from '@element-plus/icons-vue'

import { useResourceStore } from '@/stores/resourceStore'
import MobileResourceTreePanel from './resource/MobileResourceTreePanel.vue'
import MobileResourceEditor from './resource/MobileResourceEditor.vue'
import MobileKnowledgeBaseConfig from './resource/MobileKnowledgeBaseConfig.vue'
import type { Resource, ResourceWithVersions, BaseTreeItem } from '@/api/types'

const { t } = useI18n()

// --- Store ---
const resourceStore = useResourceStore()
const { isResourcesLoading, resources, resourceTree } = storeToRefs(resourceStore)

// --- State ---
const viewMode = ref<'list' | 'detail'>('list')
const selectedResourceId = ref<string | null>(null)
const initialViewMode = ref<'editor' | 'kb_config'>('editor')

// --- Computed Properties ---
const treeData = computed(() => resourceTree.value)

const activeResourceDetails = computed<ResourceWithVersions | null>(() => {
  if (!selectedResourceId.value) return null
  return resources.value.find((r) => r.id === selectedResourceId.value) || null
})

// --- Lifecycle ---
onMounted(() => {
  resourceStore.initializeList()
})

// --- Handlers ---
async function handleNodeClick(data: BaseTreeItem) {
  selectedResourceId.value = data.id
  initialViewMode.value = 'editor'
  const resource = data as unknown as Resource
  const isKnowledgeBase = resource.resourceType === 'knowledge_base'
  if (data.itemType === 'resource' || isKnowledgeBase) {
    await resourceStore.fetchResourceDetails(data.id)
  }
  viewMode.value = 'detail'
}

async function handleItemCreated(newItem: Resource) {
  selectedResourceId.value = newItem.id
  initialViewMode.value = 'editor'
  const isKnowledgeBase = newItem.resourceType === 'knowledge_base'
  if (newItem.itemType === 'resource' || isKnowledgeBase) {
    await resourceStore.fetchResourceDetails(newItem.id)
  }
  viewMode.value = 'detail'
}

function handleItemDeleted(deletedId: string) {
  if (selectedResourceId.value === deletedId) {
    selectedResourceId.value = null
    viewMode.value = 'list'
  }
}

function handleBackToList() {
  viewMode.value = 'list'
}

async function handleSelectFile(file: Resource) {
  selectedResourceId.value = file.id
  initialViewMode.value = 'kb_config'
  await resourceStore.fetchResourceDetails(file.id)
}
</script>

<style scoped>
.mobile-resource-manager {
  height: 100%;
  width: 100%;
  background-color: var(--color-background);
  position: relative;
  overflow: hidden;
}

.list-view-container,
.detail-view-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: var(--color-background);
  display: flex;
  flex-direction: column;
}

.loading-state {
  padding: 20px;
}

/* Detail Header */
.detail-header {
  height: 50px;
  padding: 0 10px;
  background-color: var(--color-background-soft);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
  z-index: 10;
}

.back-btn {
  font-size: 15px;
  font-weight: 500;
}

.title {
  font-size: 17px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%;
  text-align: center;
}

.placeholder {
  width: 60px;
}

.detail-content {
  /* 关键修复：占据剩余所有空间，并作为绝对定位的基准 */
  flex: 1;
  position: relative;
  width: 100%;
  overflow: hidden;
}

/* Transitions */
.slide-left-enter-active,
.slide-left-leave-active,
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.3s ease;
}
.slide-left-leave-to {
  transform: translateX(-100%);
}
.slide-right-enter-from {
  transform: translateX(100%);
}
</style>
