import { defineStore } from 'pinia';
import {
  getProviders,
  createProvider,
  deleteProvider,
  createModel,
  deleteModel
} from '@/api/providerService';
import type { AIProviderWithModels, AIProviderCreate, AIModelCreate } from '@/api/types';

interface ProviderState {
  providers: AIProviderWithModels[];
  isLoading: boolean;
}

export const useProviderStore = defineStore('providers', {
  state: (): ProviderState => ({
    providers: [],
    isLoading: false,
  }),

  getters: {
    // 一个方便的 getter，用于获取所有模型的扁平列表，方便在下拉框中使用
    allModels: (state) => {
      return state.providers.flatMap(p => p.models);
    }
  },

  actions: {
    /**
     * 从后端获取并加载所有服务商和模型数据
     */
    async fetchProviders() {
      this.isLoading = true;
      try {
        const data = await getProviders();
        this.providers = data;
      } catch (error) {
        console.error('Failed to fetch providers:', error);
        // 这里可以添加UI错误提示，例如使用 ElMessage
      } finally {
        this.isLoading = false;
      }
    },

    /**
     * 添加一个新的服务商
     */
    async addProvider(providerData: AIProviderCreate) {
      try {
        await createProvider(providerData);
        // 操作成功后，重新获取最新列表以保证数据同步
        await this.fetchProviders();
      } catch (error) {
        console.error('Failed to add provider:', error);
        throw error; // 将错误向上抛出，以便UI层可以捕获并处理
      }
    },

    /**
     * 删除一个服务商
     */
    async removeProvider(providerId: string) {
      try {
        await deleteProvider(providerId);
        await this.fetchProviders();
      } catch (error) {
        console.error('Failed to remove provider:', error);
        throw error;
      }
    },

    /**
     * 为指定服务商添加一个新模型
     */
    async addModel(modelData: AIModelCreate) {
      try {
        await createModel(modelData);
        await this.fetchProviders();
      } catch (error) {
        console.error('Failed to add model:', error);
        throw error;
      }
    },

    /**
     * 删除一个模型
     */
    async removeModel(modelId: string) {
      try {
        await deleteModel(modelId);
        await this.fetchProviders();
      } catch (error) {
        console.error('Failed to remove model:', error);
        throw error;
      }
    }
  }
});
