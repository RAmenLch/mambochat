// frontend/mambo/src/stores/agentStore.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getAgentChildren, createAgent, updateAgent, deleteAgent, moveAgent } from '@/api/agentService';
import type { Agent, AgentCreate, AgentUpdate, MoveRequest } from '@/api/types';
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';

export const useAgentStore = defineStore('agent', () => {
  const agentList = ref<Agent[]>([]);
  const currentAgentId = ref<string | null>(null);

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
    },
  });

  function selectAgent(agentId: string | null) {
    currentAgentId.value = agentId;
  }

  return {
    agentList,
    currentAgentId,
    isAgentListLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList,
    fetchChildren,
    createNewItem,
    updateAgentSettings,
    deleteItem,
    moveAgentItem,
    selectAgent
  };
});
