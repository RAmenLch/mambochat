// frontend/mambo/src/stores/providerStore.ts

import { defineStore } from 'pinia';
import {
  getProviders,
  deleteProvider,
  createModel,
  deleteModel,
  createProviderWithModels,
  testConnection,
  testConnectionForProvider,
  fetchExternalModels,
  updateProvider,
  updateModel,
  fetchModelsForProvider
} from '@/api/providerService';
import type {
  AIProviderWithModels,
  AIModelCreate,
  ProviderWithModelsCreate,
  ConnectionRequest,
  AIModelBase,
  AIProviderUpdate,
  AIModelUpdate,
  ConnectionTestResponse,
} from '@/api/types';
import { useChatListStore } from './chatListStore';
import { useSettingsStore } from './settingsStore';

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
    allModels: (state) => {
      return state.providers.flatMap(p => p.models);
    },
    groupedModels: (state) => {
      const allStarred = state.providers.flatMap(p => p.models.filter(m => m.starred));
      if (allStarred.length === 0) {
        return state.providers.map(p => ({ label: p.name, options: p.models }));
      }
      return [
        { label: '⭐ 标星', options: allStarred },
        ...state.providers.map(p => ({ label: p.name, options: p.models }))
      ];
    }
  },

  actions: {
    /**
     * 检查并同步 chatStore 中的会话模型ID。
     * 确保所有会话都指向一个有效的模型，如果模型ID无效或为空，则回退到全局默认模型。
     */
    async reconcileChatModels() {
      const settingsStore = useSettingsStore();
      if (!settingsStore.globalSettings.default_model_id) {
        await settingsStore.fetchGlobalSettings();
      }

      const chatListStore = useChatListStore();
      if (chatListStore.chatList.length === 0) return;

      const validModelIds = new Set(this.allModels.map(m => m.id));
      const defaultModelId = settingsStore.globalSettings.default_model_id;

      let changed = false;
      chatListStore.chatList.forEach(chat => {
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
      } finally {
        this.isLoading = false;
      }
    },

    async addProviderWithModels(providerData: ProviderWithModelsCreate) {
      const settingsStore = useSettingsStore();
      const newProvider = await createProviderWithModels(providerData);
      await this.fetchProviders();
      // 后端会自动更新 last_selected_provider_id, 这里获取最新设置以保持同步
      await settingsStore.fetchGlobalSettings();
      return newProvider;
    },

    async updateProvider(providerId: string, providerData: AIProviderUpdate) {
      const settingsStore = useSettingsStore();
      await updateProvider(providerId, providerData);
      await this.fetchProviders();
      await settingsStore.fetchGlobalSettings();
    },

    async removeProvider(providerId: string) {
      const settingsStore = useSettingsStore();
      await deleteProvider(providerId);
      await this.fetchProviders();
      await settingsStore.fetchGlobalSettings();
    },

    async addModel(modelData: AIModelCreate) {
      await createModel(modelData);
      await this.fetchProviders();
    },

    async updateModel(modelId: string, modelData: AIModelUpdate) {
      await updateModel(modelId, modelData);
      await this.fetchProviders();
    },

    async removeModel(modelId: string) {
      await deleteModel(modelId);
      // 刷新服务商和模型列表，这将自动触发 reconcileChatModels 动作
      await this.fetchProviders();
    },

    // --- External API Actions ---

    /**
     * 测试新连接，需提供 apiHost, apiKey 和 useProxy 状态。
     * @param connectionData 包含 apiHost 和 apiKey 的连接数据。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async testConnection(connectionData: ConnectionRequest, useProxy: boolean): Promise<ConnectionTestResponse> {
      return await testConnection(connectionData, useProxy);
    },

    /**
     * 为已存在的服务商测试连接。
     * @param providerId 服务商ID。
     * @param apiHost 从表单实时传入的 API Host。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async testConnectionForProvider(providerId: string, apiHost: string, useProxy: boolean): Promise<ConnectionTestResponse> {
      return await testConnectionForProvider(providerId, apiHost, useProxy);
    },

    /**
     * 获取外部模型，需提供 apiHost, apiKey 和 useProxy 状态。
     * @param connectionData 包含 apiHost 和 apiKey 的连接数据。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async fetchExternalModels(connectionData: ConnectionRequest, useProxy: boolean): Promise<AIModelBase[]> {
       return await fetchExternalModels(connectionData, useProxy);
    },

    /**
     * 为已存在的服务商获取模型列表。
     * @param providerId 服务商ID。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async fetchModelsForProvider(providerId: string, useProxy: boolean): Promise<AIModelBase[]> {
      return await fetchModelsForProvider(providerId, useProxy);
    },
  }
});
