// frontend/mambo/src/stores/imageGenStore.ts

import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

import {
  createImageGenConfig,
  deleteImageGenConfig,
  getImageGenConfigs,
  testImageGenConfig,
  updateImageGenConfig,
} from '@/api/imageGenService';
import type {
  ImageGenConfig,
  ImageGenConfigCreate,
  ImageGenConfigUpdate,
  ImageGenToolCheckResult,
} from '@/api/types';

/** 生图配置的全局状态。 */
export const useImageGenStore = defineStore('imageGen', () => {
  const configs = ref<ImageGenConfig[]>([]);
  const isLoading = ref(false);

  const enabledConfigs = computed(() => configs.value.filter(c => c.isEnabled));

  async function fetchConfigs() {
    isLoading.value = true;
    try {
      configs.value = await getImageGenConfigs();
    } catch (error) {
      console.error('Failed to fetch image generation configs:', error);
      configs.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  async function createConfig(data: ImageGenConfigCreate) {
    const created = await createImageGenConfig(data);
    await fetchConfigs();
    return created;
  }

  async function updateConfig(id: string, data: ImageGenConfigUpdate) {
    const updated = await updateImageGenConfig(id, data);
    await fetchConfigs();
    return updated;
  }

  async function removeConfig(id: string) {
    await deleteImageGenConfig(id);
    await fetchConfigs();
  }

  async function checkConfig(id: string): Promise<ImageGenToolCheckResult> {
    return await testImageGenConfig(id);
  }

  return {
    configs,
    isLoading,
    enabledConfigs,
    fetchConfigs,
    createConfig,
    updateConfig,
    removeConfig,
    checkConfig,
  };
});
