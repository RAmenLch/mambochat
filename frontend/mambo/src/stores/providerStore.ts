// frontend/mambo/src/stores/providerStore.ts

import { defineStore } from 'pinia';
import {
  getProviders,
  deleteProvider,
  createModel,
  deleteModel,
  createProviderWithModels,
  testConnection,
  fetchExternalModels,
  updateProvider,
  updateModel,
  fetchModelsForProvider
} from '@/api/providerService';
import { getGlobalSettings, updateGlobalSettings } from '@/api/settingsService';
import type {
  AIProviderWithModels,
  AIModelCreate,
  ProviderWithModelsCreate,
  ConnectionRequest,
  GlobalSettingsUpdate,
  AIModelBase,
  AIProviderUpdate,
  AIModelUpdate
} from '@/api/types';
import { useChatStore } from './chatStore';

interface ProviderState {
  providers: AIProviderWithModels[];
  isLoading: boolean;
  globalSettings: GlobalSettingsUpdate;
}

export const useProviderStore = defineStore('providers', {
  state: (): ProviderState => ({
    providers: [],
    isLoading: false,
    globalSettings: {
      default_model_id: null,
      last_selected_provider_id: null,
    },
  }),

  getters: {
    allModels: (state) => {
      return state.providers.flatMap(p => p.models);
    },
    groupedModels: (state) => {
      return state.providers.map(p => ({
        label: p.name,
        options: p.models
      }));
    }
  },

  actions: {
    /**
     * 检查并同步 chatStore 中的会话模型ID。
     * 确保所有会话都指向一个有效的模型，如果模型ID无效或为空，则回退到全局默认模型。
     */
    async reconcileChatModels() {
      if (!this.globalSettings.default_model_id) {
        await this.fetchGlobalSettings();
      }

      const chatStore = useChatStore();
      if (chatStore.chatList.length === 0) return;

      const validModelIds = new Set(this.allModels.map(m => m.id));
      const defaultModelId = this.globalSettings.default_model_id;

      let changed = false;
      chatStore.chatList.forEach(chat => {
        if (chat.itemType === 'chat') {
          const modelIdIsValid = chat.aiModelId && validModelIds.has(chat.aiModelId);

          // 如果模型ID无效 (包括为 null 或在有效列表中不存在)
          if (!modelIdIsValid) {
            // 只有当它的当前值不等于默认值时才进行修改，避免不必要的更新
            if (chat.aiModelId !== defaultModelId) {
              console.warn(
                `Reconciling chat "${chat.name}": model ${chat.aiModelId} is invalid or null. Falling back to default.`
              );
              chat.aiModelId = defaultModelId;
              changed = true;
            }
          }
        }
      });

      if (changed) {
        console.log('Chat models have been reconciled successfully.');
      }
    },

    // --- Provider & Model Actions ---
    async fetchProviders() {
      this.isLoading = true;
      try {
        this.providers = await getProviders();
        // 在获取最新的服务商和模型列表后，立即同步聊天状态
        await this.reconcileChatModels();
      } catch (error) {
        console.error('Failed to fetch providers:', error);
      } finally {
        this.isLoading = false;
      }
    },

    async addProviderWithModels(providerData: ProviderWithModelsCreate) {
      try {
        const newProvider = await createProviderWithModels(providerData);
        await this.fetchProviders();
        // 后端会自动更新 last_selected_provider_id, 这里获取最新设置以保持同步
        await this.fetchGlobalSettings();
        return newProvider;
      } catch (error) {
        console.error('Failed to add provider:', error);
        throw error;
      }
    },

    async updateProvider(providerId: string, providerData: AIProviderUpdate) {
      try {
        await updateProvider(providerId, providerData);
        await this.fetchProviders();
        await this.fetchGlobalSettings();
      } catch (error) {
        console.error('Failed to update provider:', error);
        throw error;
      }
    },

    async removeProvider(providerId: string) {
      try {
        await deleteProvider(providerId);
        await this.fetchProviders();
        await this.fetchGlobalSettings();
      } catch (error) {
        console.error('Failed to remove provider:', error);
        throw error;
      }
    },

    async addModel(modelData: AIModelCreate) {
      try {
        await createModel(modelData);
        await this.fetchProviders();
      } catch (error) {
        console.error('Failed to add model:', error);
        throw error;
      }
    },

    async updateModel(modelId: string, modelData: AIModelUpdate) {
      try {
        await updateModel(modelId, modelData);
        await this.fetchProviders();
      } catch (error) {
        console.error('Failed to update model:', error);
        throw error;
      }
    },

    async removeModel(modelId: string) {
      try {
        await deleteModel(modelId);
        // 刷新服务商和模型列表，这将自动触发 reconcileChatModels 动作
        await this.fetchProviders();
      }
      catch (error)
      {
        console.error('Failed to remove model:', error);
        throw error;
      }
    },

    // --- External API Actions ---
    async testConnection(connectionData: ConnectionRequest) {
      try {
        return await testConnection(connectionData);
      } catch (error) {
        console.error('Connection test failed:', error);
        throw error;
      }
    },

    async fetchExternalModels(connectionData: ConnectionRequest): Promise<AIModelBase[]> {
       try {
        return await fetchExternalModels(connectionData);
      } catch (error) {
        console.error('Failed to fetch external models:', error);
        throw error;
      }
    },

    async fetchModelsForProvider(providerId: string): Promise<AIModelBase[]> {
      try {
        return await fetchModelsForProvider(providerId);
      } catch (error) {
        console.error('Failed to fetch models for existing provider:', error);
        throw error;
      }
    },

    // --- Global Settings Actions ---
    async fetchGlobalSettings() {
      try {
        this.globalSettings = await getGlobalSettings();
      } catch (error) {
        console.error('Failed to fetch global settings:', error);
      }
    },

    async saveGlobalSettings(settings: GlobalSettingsUpdate) {
      try {
        const updatedSettings = await updateGlobalSettings(settings);
        this.globalSettings = updatedSettings;
      } catch (error) {
        console.error('Failed to save global settings:', error);
        throw error;
      }
    }
  }
});
