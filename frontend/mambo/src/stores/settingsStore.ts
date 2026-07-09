// frontend/mambo/src/stores/settingsStore.ts

import { defineStore } from 'pinia'
import {
  getGlobalSettings,
  updateGlobalSettings,
  testProxyConnection,
  uploadAvatar,
  deleteAvatar,
} from '@/api/settingsService'
import type { GlobalSettingsUpdate, ProxyTestRequest, ConnectionTestResponse } from '@/api/types'

interface SettingsState {
  globalSettings: GlobalSettingsUpdate
}

export const useSettingsStore = defineStore('settings', {
  state: (): SettingsState => ({
    globalSettings: {
      default_model_id: null,
      title_generation_model_id: null,
      last_selected_provider_id: null,
      default_max_context_messages: 0,
      default_temperature: 1.0,
      default_top_p: 1.0,
      default_stream: true,
      proxy_enabled: false,
      proxy_url: null,
      user_avatar_url: null,
      ai_avatar_url: null,
      zip_history_system_prompt: null,
      frontend_editor: 'simple',
      message_display_mode: 'interleaved',
      kb_default_chunk_size: 500,
      kb_default_chunk_overlap: 50,
      send_message_shortcut: 'enter',
      language: 'zh-CN',
      default_enable_suggest: false,
      default_enable_ask_user: false,
      default_max_retries: 3,
      default_timeout: 60,
    },
  }),

  actions: {
    /**
     * 从后端获取最新的全局配置。
     */
    async fetchGlobalSettings() {
      this.globalSettings = await getGlobalSettings()
    },

    /**
     * 保存全局配置到后端。
     * @param settings - 包含要更新的配置的对象。
     */
    async saveGlobalSettings(settings: GlobalSettingsUpdate) {
      const updatedSettings = await updateGlobalSettings(settings)
      this.globalSettings = updatedSettings
    },

    /**
     * 测试代理服务器的连通性。
     * @param requestData - 包含代理URL和测试目标URL的对象。
     */
    async testProxy(requestData: ProxyTestRequest): Promise<ConnectionTestResponse> {
      return await testProxyConnection(requestData)
    },

    /**
     * 上传指定类型的头像。
     * @param type - 头像类型, 'user' 或 'ai'。
     * @param file - 文件对象。
     */
    async uploadAvatar(type: 'user' | 'ai', file: File) {
      await uploadAvatar(type, file)
      await this.fetchGlobalSettings() // 成功后刷新全局设置以获取新URL
    },

    /**
     * 删除指定类型的头像。
     * @param type - 头像类型, 'user' 或 'ai'。
     */
    async deleteAvatar(type: 'user' | 'ai') {
      await deleteAvatar(type)
      await this.fetchGlobalSettings() // 成功后刷新全局设置
    },
  },
})
