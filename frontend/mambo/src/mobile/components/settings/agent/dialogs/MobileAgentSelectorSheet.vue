<!-- MobileAgentSelectorSheet.vue — 移动端子 Agent 选择器（Bottom Sheet） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="sheet-overlay" @click="close">
        <div class="sheet-panel" @click.stop>
          <div class="sheet-handle"></div>

          <div class="sheet-header">
            <span class="sheet-title">{{ $t('agent.selector.title') }}</span>
            <button class="sheet-close-btn" @click="close">
              <el-icon :size="20"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-search">
            <el-icon :size="16" class="search-icon"><Search /></el-icon>
            <input
              v-model="searchQuery"
              :placeholder="$t('agent.selector.searchPlaceholder')"
              class="search-input"
            />
            <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">
              <el-icon :size="14"><Close /></el-icon>
            </button>
          </div>

          <div class="sheet-body">
            <div v-if="filteredAgents.length === 0" class="sheet-empty">
              <el-empty :description="$t('agent.selector.noData')" :image-size="60" />
            </div>

            <button
              v-for="agent in filteredAgents"
              :key="agent.id"
              class="sheet-item"
              :class="{ 'is-selected': isSelected(agent.id) }"
              @click="toggleSelection(agent)"
            >
              <div class="item-left">
                <el-avatar v-if="agent.agentAvatarUrl" :size="38" :src="agent.agentAvatarUrl" />
                <el-avatar v-else :size="38" :icon="User" />
                <div class="item-info">
                  <span class="item-name">{{ agent.name }}</span>
                  <span class="item-desc">{{ agent.description || $t('common.noDescription') }}</span>
                </div>
              </div>
              <div class="item-check" :class="{ checked: isSelected(agent.id) }">
                <el-icon v-if="isSelected(agent.id)" :size="18"><Select /></el-icon>
                <div v-else class="check-circle"></div>
              </div>
            </button>
          </div>

          <div class="sheet-footer">
            <span class="footer-count">
              {{ $t('agent.selector.selected', { count: selectedAgents.length }) }}
            </span>
            <button class="footer-confirm" @click="handleConfirm">
              {{ $t('common.action.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { Search, User, Close, Select } from '@element-plus/icons-vue';
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

const searchQuery = ref('');
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

function close() {
  emit('update:visible', false);
}

watch(() => props.visible, async (v) => {
  if (v) {
    searchQuery.value = '';
    try {
      const data = await getAgents(0, 1000);
      allAgents.value = data;
      selectedAgents.value = allAgents.value.filter(a => props.initialSelectedIds.includes(a.id));
    } catch (error) {
      console.error('Failed to fetch agents:', error);
    }
  }
});

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
  close();
}
</script>

<style scoped>
.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 2100;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.sheet-panel {
  width: 100%;
  max-width: 500px;
  max-height: 85vh;
  background: var(--el-bg-color);
  border-radius: 16px 16px 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 2px;
  margin: 10px auto 0;
  flex-shrink: 0;
}

.sheet-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px 8px;
  flex-shrink: 0;
}

.sheet-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--el-text-color-primary);
}

.sheet-close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  background: var(--el-fill-color-light);
  border-radius: 50%;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

/* ===== Search ===== */
.sheet-search {
  display: flex;
  align-items: center;
  margin: 0 16px 8px;
  padding: 0 12px;
  height: 36px;
  background: var(--color-background-soft);
  border-radius: 10px;
  flex-shrink: 0;
}

.search-icon {
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  margin-left: 6px;
  border: none;
  background: transparent;
  font-size: 15px;
  color: var(--el-text-color-primary);
  outline: none;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--el-text-color-placeholder);
}

.search-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: var(--el-fill-color);
  border-radius: 50%;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  flex-shrink: 0;
}

/* ===== Body ===== */
.sheet-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 16px 8px;
  -webkit-overflow-scrolling: touch;
}

.sheet-empty {
  padding: 40px 0;
}

.sheet-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px;
  margin-bottom: 8px;
  background: var(--color-background-soft);
  border: 1.5px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, background 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.sheet-item.is-selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.sheet-item:active {
  background: var(--el-fill-color);
}

.item-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.item-info {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.item-name {
  font-size: 15px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-check {
  flex-shrink: 0;
  margin-left: 10px;
}

.check-circle {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid var(--el-border-color);
}

.item-check.checked {
  color: var(--el-color-primary);
}

/* ===== Footer ===== */
.sheet-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  padding-bottom: max(10px, env(safe-area-inset-bottom));
  background: var(--el-bg-color);
  border-top: 0.5px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.footer-count {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.footer-confirm {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 40px;
  padding: 0 28px;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  border: none;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.3);
  cursor: pointer;
  transition: opacity 0.2s, transform 0.1s;
}

.footer-confirm:active {
  transform: scale(0.97);
}

/* ===== Sheet Transitions ===== */
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.25s ease;
}

.sheet-enter-active .sheet-panel,
.sheet-leave-active .sheet-panel {
  transition: transform 0.25s cubic-bezier(0.32, 0.72, 0, 1);
}

.sheet-enter-from,
.sheet-leave-to {
  opacity: 0;
}

.sheet-enter-from .sheet-panel,
.sheet-leave-to .sheet-panel {
  transform: translateY(100%);
}

@media (prefers-color-scheme: dark) {
  .sheet-handle {
    background: rgba(255, 255, 255, 0.2);
  }
}
</style>
