<!-- frontend/mambo/src/components/settings/agent/dialogs/AgentSelectorDialog.vue -->
<template>
  <el-dialog
    :title="$t('agent.selector.title')"
    v-model="dialogVisible"
    width="600px"
    class="agent-selector-dialog"
    destroy-on-close
  >
    <div class="selector-container">
      <el-input
        v-model="searchQuery"
        :placeholder="$t('agent.selector.searchPlaceholder')"
        clearable
        :prefix-icon="Search"
        class="search-input"
      />

      <el-table
        :data="filteredAgents"
        style="width: 100%; margin-top: 16px;"
        height="300"
        @selection-change="handleSelectionChange"
        ref="tableRef"
        row-key="id"
      >
        <template #empty>
          <el-empty :description="$t('agent.selector.noData')" :image-size="60" />
        </template>
        <el-table-column type="selection" width="55" :reserve-selection="true" />
        <el-table-column :label="$t('agent.name')" prop="name">
          <template #default="{ row }">
            <div class="agent-info">
              <el-avatar
                v-if="row.agentAvatarUrl"
                :size="24"
                :src="row.agentAvatarUrl"
                class="agent-avatar"
              />
              <el-icon v-else class="agent-icon"><User /></el-icon>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('agent.description')" prop="description" show-overflow-tooltip />
      </el-table>

      <div class="selected-count">
        {{ $t('agent.selector.selected', { count: selectedAgents.length }) }}
      </div>
    </div>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="dialogVisible = false">{{ $t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="handleConfirm">{{ $t('common.action.confirm') }}</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue';
import { Search, User } from '@element-plus/icons-vue';
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

const dialogVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val)
});

const searchQuery = ref('');
const allAgents = ref<Agent[]>([]);
const selectedAgents = ref<Agent[]>([]);
const tableRef = ref();

const filteredAgents = computed(() => {
  // 过滤掉当前正在编辑的 Agent 自身，防止循环挂载
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

watch(dialogVisible, async (val) => {
  if (val) {
    searchQuery.value = '';
    selectedAgents.value = [];
    try {
      const data = await getAgents(0, 1000);
      allAgents.value = data;

      // 预选中已挂载的 Agent
      nextTick(() => {
        if (tableRef.value) {
          tableRef.value.clearSelection();
          const toSelect = allAgents.value.filter(a => props.initialSelectedIds.includes(a.id));
          toSelect.forEach(row => {
            tableRef.value.toggleRowSelection(row, true);
          });
        }
      });
    } catch (error) {
      console.error('Failed to fetch agents:', error);
    }
  }
});

function handleSelectionChange(selection: Agent[]) {
  selectedAgents.value = selection;
}

function handleConfirm() {
  emit('select', selectedAgents.value);
  dialogVisible.value = false;
}
</script>

<style scoped>
.selector-container {
  display: flex;
  flex-direction: column;
}
.agent-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-avatar {
  background-color: transparent;
}
.agent-icon {
  font-size: 18px;
  color: var(--el-text-color-secondary);
}
.selected-count {
  margin-top: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  text-align: right;
}
</style>
