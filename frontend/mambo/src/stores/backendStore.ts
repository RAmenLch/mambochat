// frontend/mambo/src/stores/backendStore.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getBackends, createBackend, updateBackend, deleteBackend, getSshPublicKey } from '@/api/backendService';
import type { BackendConfig, BackendCreate, BackendUpdate } from '@/api/types/backendTypes';

export const useBackendStore = defineStore('backend', () => {
  const backendList = ref<BackendConfig[]>([]);
  const isLoading = ref(false);
  const systemPublicKey = ref<string | null>(null);

  async function fetchBackends() {
    isLoading.value = true;
    try {
      backendList.value = await getBackends(0, 1000); // 暂不分页，拉取全部
    } catch (error) {
      console.error('Failed to fetch backends:', error);
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function fetchPublicKey() {
    try {
      const res = await getSshPublicKey();
      systemPublicKey.value = res.public_key;
    } catch (error) {
      console.error('Failed to fetch SSH public key:', error);
      throw error;
    }
  }

  async function createNewBackend(data: BackendCreate) {
    const newBackend = await createBackend(data);
    backendList.value.push(newBackend);
    return newBackend;
  }

  async function updateExistingBackend(id: string, data: BackendUpdate) {
    const updated = await updateBackend(id, data);
    const index = backendList.value.findIndex(b => b.id === id);
    if (index !== -1) {
      backendList.value[index] = updated;
    }
    return updated;
  }

  async function removeBackend(id: string) {
    await deleteBackend(id);
    backendList.value = backendList.value.filter(b => b.id !== id);
  }

  return {
    backendList,
    isLoading,
    systemPublicKey,
    fetchBackends,
    fetchPublicKey,
    createNewBackend,
    updateExistingBackend,
    removeBackend
  };
});
