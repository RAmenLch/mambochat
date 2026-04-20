<!-- frontend/mambo/src/mobile/components/settings/MobileAgentManager.vue -->
<template>
  <div class="mobile-agent-manager-wrapper">
    <el-tabs v-model="activeTab" class="mobile-agent-tabs">
      <!-- Tab 1: Agent 管理 -->
      <el-tab-pane :label="t('agent.manager')" name="agent" class="tab-pane-full">
        <div class="mobile-agent-manager">
          <!-- 视图 1: Agent 列表 (Tree) -->
          <transition name="slide-left">
            <div v-show="viewMode === 'list'" class="list-view-container">
              <MobileAgentTreePanel
                @node-click="handleNodeClick"
                @item-created="handleItemCreated"
                @item-deleted="handleItemDeleted"
              />
            </div>
          </transition>

          <!-- 视图 2: Agent 详情 (Editor) -->
          <transition name="slide-right">
            <div v-if="viewMode === 'detail' && activeAgentDetails" class="detail-view-container">
              <!-- 详情 Header -->
              <div class="detail-header">
                <el-button link :icon="ArrowLeft" @click="handleBackToList" class="back-btn">
                  {{ t('common.action.back') }}
                </el-button>
                <span class="title">{{ activeAgentDetails.name }}</span>
                <span class="placeholder"></span>
              </div>

              <!-- 详情内容 -->
              <div class="detail-content">
                <MobileAgentEditor />
              </div>
            </div>

            <!-- 加载状态 -->
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
      </el-tab-pane>

      <!-- Tab 2: Backend 挂载配置 -->
      <el-tab-pane :label="t('backend.manager')" name="backend" class="tab-pane-full">
        <MobileBackendManagerPanel />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { useRouter, useRoute } from 'vue-router';
import { ArrowLeft } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import MobileAgentTreePanel from './agent/MobileAgentTreePanel.vue';
import MobileAgentEditor from './agent/MobileAgentEditor.vue';
import MobileBackendManagerPanel from './agent/MobileBackendManagerPanel.vue'; // [新增]
import type { BaseTreeItem, Agent } from '@/api/types';

const { t } = useI18n();
const router = useRouter();
const route = useRoute();
const agentStore = useAgentStore();
const { agentList, currentAgentId } = storeToRefs(agentStore);

const activeTab = ref('agent'); // [新增]
const viewMode = ref<'list' | 'detail'>('list');

const activeAgentDetails = computed(() => {
  if (!currentAgentId.value) return null;
  return agentList.value.find((a) => a.id === currentAgentId.value) || null;
});

watch(currentAgentId, (newId) => {
  if (newId) {
    viewMode.value = 'detail';
  }
}, { immediate: true });

onMounted(() => {
  agentStore.initializeList();
});

function handleNodeClick(data: BaseTreeItem) {
  if (data.itemType === 'agent') {
    agentStore.selectAgent(data.id);
    viewMode.value = 'detail';
  }
}

function handleItemCreated(newItem: Agent) {
  if (newItem.itemType === 'agent') {
    agentStore.selectAgent(newItem.id);
    viewMode.value = 'detail';
  }
}

function handleItemDeleted(deletedId: string) {
  if (currentAgentId.value === deletedId) {
    agentStore.selectAgent(null);
    viewMode.value = 'list';

    if (route.query.agentId === deletedId) {
      const newQuery = { ...route.query };
      delete newQuery.agentId;
      router.replace({ query: newQuery });
    }
  }
}

function handleBackToList() {
  viewMode.value = 'list';
  agentStore.selectAgent(null);

  if (route.query.agentId) {
    const newQuery = { ...route.query };
    delete newQuery.agentId;
    router.replace({ query: newQuery });
  }
}
</script>

<style scoped>
.mobile-agent-manager-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
}

.mobile-agent-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

:deep(.mobile-agent-tabs > .el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  background-color: var(--color-background-soft);
  border-bottom: 1px solid var(--color-border);
}

:deep(.mobile-agent-tabs > .el-tabs__content) {
  flex-grow: 1;
  padding: 0;
  overflow: hidden;
}

.tab-pane-full {
  height: 100%;
  position: relative;
}

.mobile-agent-manager {
  height: 100%;
  width: 100%;
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
  flex: 1;
  position: relative;
  width: 100%;
  overflow: hidden;
}

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
