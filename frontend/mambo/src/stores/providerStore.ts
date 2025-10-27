// frontend/mambochat/src/stores/providerStore.ts

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
import { getGlobalSettings, updateGlobalSettings, testProxyConnection } from '@/api/settingsService';
import type {
  AIProviderWithModels,
  AIModelCreate,
  ProviderWithModelsCreate,
  ConnectionRequest,
  GlobalSettingsUpdate,
  AIModelBase,
  AIProviderUpdate,
  AIModelUpdate,
  ConnectionTestResponse,
  ProxyTestRequest
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
      default_max_context_messages: 0,
      default_temperature: 1.0,
      default_top_p: 1.0,
      default_stream: true,
      proxy_enabled: false,
      proxy_url: null,
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
        throw error;
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

    /**
     * 测试新连接，需提供 apiHost, apiKey 和 useProxy 状态。
     * @param connectionData 包含 apiHost 和 apiKey 的连接数据。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async testConnection(connectionData: ConnectionRequest, useProxy: boolean): Promise<ConnectionTestResponse> {
      try {
        return await testConnection(connectionData, useProxy);
      } catch (error) {
        console.error('Connection test failed:', error);
        throw error;
      }
    },

    /**
     * 为已存在的服务商测试连接。
     * @param providerId 服务商ID。
     * @param apiHost 从表单实时传入的 API Host。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async testConnectionForProvider(providerId: string, apiHost: string, useProxy: boolean): Promise<ConnectionTestResponse> {
      try {
        return await testConnectionForProvider(providerId, apiHost, useProxy);
      } catch (error) {
        console.error('Connection test for existing provider failed:', error);
        throw error;
      }
    },

    /**
     * 获取外部模型，需提供 apiHost, apiKey 和 useProxy 状态。
     * @param connectionData 包含 apiHost 和 apiKey 的连接数据。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async fetchExternalModels(connectionData: ConnectionRequest, useProxy: boolean): Promise<AIModelBase[]> {
       try {
        return await fetchExternalModels(connectionData, useProxy);
      } catch (error) {
        console.error('Failed to fetch external models:', error);
        throw error;
      }
    },

    /**
     * 为已存在的服务商获取模型列表。
     * @param providerId 服务商ID。
     * @param useProxy 从表单实时传入的代理状态。
     */
    async fetchModelsForProvider(providerId: string, useProxy: boolean): Promise<AIModelBase[]> {
      try {
        return await fetchModelsForProvider(providerId, useProxy);
      } catch (error) {
        console.error('Failed to fetch models for existing provider:', error);
        throw error;
      }
    },

    // --- Global Settings & Proxy Actions ---
    async fetchGlobalSettings() {
      try {
        this.globalSettings = await getGlobalSettings();
      } catch (error) {
        console.error('Failed to fetch global settings:', error);
        throw error;
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
    },

    async testProxy(requestData: ProxyTestRequest): Promise<ConnectionTestResponse> {
        return await testProxyConnection(requestData);
    },
  }
});
