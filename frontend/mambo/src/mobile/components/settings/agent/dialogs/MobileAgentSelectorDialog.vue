<!-- frontend/mambo/src/mobile/components/settings/agent/dialogs/MobileAgentSelectorDialog.vue -->
<template>
  <el-drawer
    :model-value="visible"
    direction="btt"
    size="85%"
    :with-header="false"
    class="mobile-agent-selector-drawer"
    @update:model-value="val => emit('update:visible', val)"
    @open="handleOpen"
  >
    <div class="drawer-container">
      <div class="drawer-header">
        <span class="title">{{ $t('agent.selector.title') }}</span>
        <el-icon class="close-btn" @click="emit('update:visible', false)"><Close /></el-icon>
      </div>

      <div class="search-bar">
        <el-input
          v-model="searchQuery"
          :placeholder="$t('agent.selector.searchPlaceholder')"
          clearable
          :prefix-icon="Search"
        />
      </div>

      <el-scrollbar class="agent-list-container">
        <div v-if="filteredAgents.length === 0" class="empty-state">
          <el-empty :description="$t('agent.selector.noData')" :image-size="60" />
        </div>

        <div class="agent-list">
          <div
            v-for="agent in filteredAgents"
            :key="agent.id"
            class="agent-item"
            :class="{ 'is-selected': isSelected(agent.id) }"
            @click="toggleSelection(agent)"
          >
            <div class="agent-avatar-wrapper">
              <el-avatar v-if="agent.agentAvatarUrl" :size="40" :src="agent.agentAvatarUrl" />
              <el-avatar v-else :size="40" :icon="User" />
            </div>
            <div class="agent-info">
              <div class="agent-name">{{ agent.name }}</div>
              <div class="agent-desc">{{ agent.description || $t('common.noDescription') }}</div>
            </div>
            <div class="agent-action">
              <el-checkbox :model-value="isSelected(agent.id)" @click.stop="toggleSelection(agent)" size="large" />
            </div>
          </div>
        </div>
      </el-scrollbar>

      <div class="drawer-footer">
        <div class="selected-count">
          {{ $t('agent.selector.selected', { count: selectedAgents.length }) }}
        </div>
        <el-button type="primary" @click="handleConfirm" class="confirm-btn">
          {{ $t('common.action.confirm') }}
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { Search, User, Close } from '@element-plus/icons-vue';
import { getAgents } from '@/api/agentService';
import type { Agent } from '@/api/types';

const props = defineProps<{
  visible: boolean;
  currentAgentId: string;
  initialSelectedIds: string[];
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (e: 'select', agents: Agent[]): void;
}>();

const searchQuery = ref<string>('');
const allAgents = ref<Agent[]>([]);
const selectedAgents = ref<Agent[]>([]);

const filteredAgents = computed<Agent[]>(() => {
  let list = allAgents.value.filter(a => a.itemType === 'agent' && a.id !== props.currentAgentId);
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(a =>
      a.name.toLowerCase().includes(q) ||
      (a.description && a.description.toLowerCase().includes(q))
    );
  }
  return list;
});

const isSelected = (id: string): boolean => {
  return selectedAgents.value.some(a => a.id === id);
};

async function handleOpen() {
  searchQuery.value = '';
  try {
    const data = await getAgents(0, 1000);
    allAgents.value = data;
    selectedAgents.value = allAgents.value.filter(a => props.initialSelectedIds.includes(a.id));
  } catch (error) {
    console.error('Failed to fetch agents:', error);
  }
}

function toggleSelection(agent: Agent) {
  const index = selectedAgents.value.findIndex(a => a.id === agent.id);
  if (index > -1) {
    selectedAgents.value.splice(index, 1);
  } else {
    selectedAgents.value.push(agent);
  }
}

function handleConfirm() {
  emit('select', selectedAgents.value);
  emit('update:visible', false);
}
</script>

<style scoped>
.mobile-agent-selector-drawer {
  background-color: var(--el-bg-color-page);
}

.drawer-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background-color: var(--el-bg-color-page);
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background-color: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.close-btn {
  font-size: 20px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

.search-bar {
  padding: 12px 16px;
  background-color: var(--el-bg-color);
}

.agent-list-container {
  flex: 1;
  overflow: hidden;
}

.empty-state {
  padding-top: 40px;
}

.agent-list {
  padding: 8px 16px;
}

.agent-item {
  display: flex;
  align-items: center;
  padding: 12px;
  margin-bottom: 12px;
  background-color: var(--el-bg-color);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.2s;
  border: 1px solid transparent;
}

.agent-item.is-selected {
  border-color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.agent-avatar-wrapper {
  margin-right: 12px;
  flex-shrink: 0;
}

.agent-info {
  flex: 1;
  overflow: hidden;
}

.agent-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.agent-action {
  margin-left: 12px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
}

.drawer-footer {
  padding: 12px 16px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom));
  background-color: var(--el-bg-color);
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.selected-count {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.confirm-btn {
  width: 120px;
}
</style>
