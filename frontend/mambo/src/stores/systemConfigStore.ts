// frontend/mambo/src/stores/systemConfigStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getSystemConfig } from '@/api/systemService';
import type { LLMParameterDefinition, DefaultProviderInfo } from '@/api/types';

/**
 * 管理系统级的配置信息，如支持的LLM参数和预设服务商列表。
 * 这些数据在应用生命周期内相对稳定，通常只需获取一次。
 */
export const useSystemConfigStore = defineStore('systemConfig', () => {
  // --- State ---
  const llmParameters = ref<LLMParameterDefinition[]>([]);
  const defaultProviders = ref<DefaultProviderInfo[]>([]);
  const isLoading = ref(false);
  const isLoaded = ref(false); // 标志数据是否已成功加载

  // --- Getters ---

  /**
   * 将LLM参数列表转换为适用于 <el-select> 的选项格式。
   * 每个选项包含 { key, label }，用于在UI中显示和提交。
   */
  const parameterOptions = computed(() => {
    return llmParameters.value.map(p => ({
      key: p.key,
      label: p.label
    }));
  });

  // --- Actions ---

  /**
   * 从后端获取系统配置。
   * 内置了防止重复请求的逻辑，只有在数据未加载时才会真正发起API调用。
   */
  async function fetchSystemConfig() {
    // 如果数据已加载或正在加载中，则直接返回，避免重复请求
    if (isLoaded.value || isLoading.value) {
      return;
    }

    isLoading.value = true;
    try {
      const response = await getSystemConfig();
      llmParameters.value = response.llm_parameters;
      defaultProviders.value = response.default_providers;
      isLoaded.value = true; // 标记为已成功加载
    } catch (error) {
      console.error('Failed to fetch system configuration:', error);
      // 在出错时，重置 isLoaded 状态，以便下次可以重试
      isLoaded.value = false;
    } finally {
      isLoading.value = false;
    }
  }

  return {
    // State
    llmParameters,
    defaultProviders,
    isLoading,
    isLoaded,

    // Getters
    parameterOptions,

    // Actions
    fetchSystemConfig,
  };
});
