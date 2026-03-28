<!-- frontend/mambo/src/mobile/components/settings/MobileAgentManager.vue -->
<template>
  <div class="mobile-agent-manager">
    <!-- 视图 1: Agent 列表 (Tree) -->
    <transition name="slide-left">
      <!-- 修复: 将 v-if 改为 v-show 以保持树的展开状态和避免重新挂载触发 onMounted -->
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
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { useRouter, useRoute } from 'vue-router'; // 引入路由以清除参数
import { ArrowLeft } from '@element-plus/icons-vue';

import { useAgentStore } from '@/stores/agentStore';
import MobileAgentTreePanel from './agent/MobileAgentTreePanel.vue';
import MobileAgentEditor from './agent/MobileAgentEditor.vue';
import type { BaseTreeItem, Agent } from '@/api/types';

const { t } = useI18n();
const router = useRouter(); // 实例化 router
const route = useRoute();   // 实例化 route
const agentStore = useAgentStore();
const { agentList, currentAgentId } = storeToRefs(agentStore);

const viewMode = ref<'list' | 'detail'>('list');

const activeAgentDetails = computed(() => {
  if (!currentAgentId.value) return null;
  return agentList.value.find((a) => a.id === currentAgentId.value) || null;
});

// 监听当前选中的 Agent，支持深度链接直接打开详情
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

    // 修复: 删除后清除路由中的 agentId 参数
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

  // 修复: 返回列表时清除路由中的 agentId 参数，防止 TreePanel 重新读取触发闪回
  if (route.query.agentId) {
    const newQuery = { ...route.query };
    delete newQuery.agentId;
    router.replace({ query: newQuery });
  }
}
</script>

<style scoped>
.mobile-agent-manager {
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
