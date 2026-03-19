// frontend/mambo/src/stores/agentStore.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getAgentChildren, createAgent, updateAgent, deleteAgent, moveAgent, getAgents } from '@/api/agentService';
import type { Agent, AgentCreate, AgentUpdate, MoveRequest } from '@/api/types';
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';

export const useAgentStore = defineStore('agent', () => {
  const agentList = ref<Agent[]>([]);
  const currentAgentId = ref<string | null>(null);

  // [新增] 用于平铺展示所有 Agent（如下拉列表、选项等）
  const allAgents = ref<Agent[]>([]);
  const isAllAgentsLoading = ref(false);

  const {
    isLoading: isAgentListLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList,
    fetchChildren,
    createItem: createNewItem,
    updateItem: updateAgentSettings,
    deleteItem,
    moveItem: moveAgentItem,
  } = useTreeStoreActions<Agent, AgentCreate, AgentUpdate>({
    items: agentList,
    api: {
      fetchChildren: getAgentChildren,
      create: createAgent,
      update: updateAgent,
      remove: async (id: string) => { await deleteAgent(id); },
      move: async (req: MoveRequest) => { await moveAgent(req); },
    },
    onDeleteItem: (deletedItem: Agent) => {
      if (currentAgentId.value === deletedItem.id) {
        currentAgentId.value = null;
      }
      // [新增] 同步删除 allAgents 中的项
      allAgents.value = allAgents.value.filter(a => a.id !== deletedItem.id);
    },
  });

  // [新增] 获取所有 Agent
  async function fetchAllAgents() {
    isAllAgentsLoading.value = true;
    try {
      allAgents.value = await getAgents(0, 1000);
    } catch (error) {
      console.error('Failed to fetch all agents:', error);
    } finally {
      isAllAgentsLoading.value = false;
    }
  }

  // [修改] 包装 createNewItem，同步更新 allAgents
  async function createNewItemWrapper(data: AgentCreate) {
    const newItem = await createNewItem(data);
    if (newItem) {
      allAgents.value.push(newItem);
    }
    return newItem;
  }

  // [修改] 包装 updateAgentSettings，同步更新 allAgents (修复 TS1345 报错)
  async function updateAgentSettingsWrapper(id: string, data: AgentUpdate) {
    // updateItem 返回 void，直接等待其完成
    await updateAgentSettings(id, data);

    // 从树节点列表中获取最新状态同步过去
    const updatedNode = agentList.value.find(a => a.id === id);
    if (updatedNode) {
      const index = allAgents.value.findIndex(a => a.id === id);
      if (index !== -1) {
        allAgents.value[index] = { ...updatedNode };
      }
    }
  }

  function selectAgent(agentId: string | null) {
    currentAgentId.value = agentId;
  }

  return {
    agentList,
    allAgents, // [新增]
    isAllAgentsLoading, // [新增]
    currentAgentId,
    isAgentListLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList,
    fetchChildren,
    fetchAllAgents, // [新增]
    createNewItem: createNewItemWrapper, // [修改]
    updateAgentSettings: updateAgentSettingsWrapper, // [修改]
    deleteItem,
    moveAgentItem,
    selectAgent
  };
});
