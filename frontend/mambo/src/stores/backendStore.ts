// frontend/mambo/src/stores/backendStore.ts
import { defineStore } from 'pinia';
import { ref } from 'vue';
import { getBackends, getBackend, createBackend, updateBackend, deleteBackend, getSshPublicKey, testSshConnection, duplicateBackend } from '@/api/backendService';
import type { BackendConfig, BackendCreate, BackendUpdate, SshTestRequest } from '@/api/types/backendTypes';

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

  // [新增] 测试连接方法
  async function testConnection(data: SshTestRequest) {
    return await testSshConnection(data);
  }

  // [新增] 按 ID 回源兜底：缓存未命中时从后端拉取单个 Backend 并合并进缓存，
  // 避免懒加载缓存过期导致导入的 Agent 引用新 Backend 时显示"未知 Backend"
  async function ensureBackend(id: string) {
    const existing = backendList.value.find(b => b.id === id);
    if (existing) return existing;
    try {
      const backend = await getBackend(id);
      if (!backendList.value.find(b => b.id === id)) {
        backendList.value.push(backend);
      }
      return backend;
    } catch {
      return null;
    }
  }

  // [新增] 复制 Backend 副本
  async function duplicateBackendItem(backendId: string) {
    const newBackend = await duplicateBackend(backendId);
    backendList.value.push(newBackend);
    return newBackend;
  }

  return {
    backendList,
    isLoading,
    systemPublicKey,
    fetchBackends,
    fetchPublicKey,
    createNewBackend,
    updateExistingBackend,
    removeBackend,
    testConnection, // [新增]
    ensureBackend, // [新增]
    duplicateBackendItem // [新增]
  };
});
