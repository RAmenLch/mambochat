// frontend/mambo/src/stores/chatStore.ts

import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import {
  getChats,
  createChat,
  getChatWithMessages,
  deleteChat,
  updateChatSettings,
  reorderChats,
  updateMessage,
  deleteMessage,
  duplicateChat,
  prepareGenerate,
  prepareRegenerate,
  stopGeneration as stopGenerationAPI,
} from '@/api/chatService';
import type { Chat, Message, ChatCreate, ChatUpdate, ChatReorderItem } from '@/api/types';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useProviderStore } from './providerStore';

interface ChatState {
  chatList: Chat[];
  currentChatId: string | null;
  currentChatMessages: Message[];
  isChatListLoading: boolean;
  isChatHistoryLoading: boolean;
  activeSubscriptions: Map<string, AbortController>; // messageId -> AbortController
  userInputCache: Record<string, string>;
}

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    chatList: [],
    currentChatId: null,
    currentChatMessages: [],
    isChatListLoading: false,
    isChatHistoryLoading: false,
    activeSubscriptions: new Map(),
    userInputCache: {},
  }),

  getters: {
    currentChat: (state): Chat | null => {
      if (!state.currentChatId) return null;
      const chat = state.chatList.find(chat => chat.id === state.currentChatId);
      return chat?.itemType === 'chat' ? chat : null;
    },
    isGenerating(state): boolean {
      return state.activeSubscriptions.size > 0;
    }
  },

  actions: {
    // --- 会话列表管理 ---
    async fetchChatList() {
      this.isChatListLoading = true;
      try {
        this.chatList = await getChats();
      } catch (error) {
        console.error('Failed to fetch chat list:', error);
      } finally {
        this.isChatListLoading = false;
      }
    },

    async selectChat(chatId: string) {
      if (this.currentChatId === chatId) return;

      this.stopAllGenerations();

      const selectedItem = this.chatList.find(item => item.id === chatId);
      if (!selectedItem || selectedItem.itemType === 'folder') {
        this.currentChatId = chatId;
        this.currentChatMessages = [];
        return;
      }

      this.currentChatId = chatId;
      this.isChatHistoryLoading = true;
      this.currentChatMessages = [];

      try {
        const chatWithMessages = await getChatWithMessages(chatId);
        const chatIndex = this.chatList.findIndex(c => c.id === chatId);
        if (chatIndex !== -1) {
          const { messages: newMessages, ...chatDetails } = chatWithMessages;
          this.chatList[chatIndex] = { ...this.chatList[chatIndex], ...chatDetails };
          this.currentChatMessages = newMessages.sort((a, b) => a.sortOrder - b.sortOrder);
        } else {
          this.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);
        }

        this.currentChatMessages.forEach(msg => {
            if (msg.role === 'assistant' && msg.status === 'generating') {
                this._subscribeToMessageStream(msg);
            }
        });

      } catch (error) {
        console.error(`Failed to fetch messages for chat ${chatId}:`, error);
        this.currentChatId = null;
      } finally {
        this.isChatHistoryLoading = false;
      }
    },

    async createNewItem(itemData: ChatCreate): Promise<Chat | null> {
      try {
        const finalItemData = { ...itemData };
        if (finalItemData.itemType === 'chat' && !finalItemData.aiModelId) {
          const providerStore = useProviderStore();
          if (!providerStore.globalSettings.default_model_id) {
            await providerStore.fetchGlobalSettings();
          }
          if (providerStore.globalSettings.default_model_id) {
            finalItemData.aiModelId = providerStore.globalSettings.default_model_id;
          }
        }

        const newItem = await createChat(finalItemData);
        this.chatList.push(newItem);
        return newItem;
      } catch (error) {
        console.error('Failed to create new item:', error);
        return null;
      }
    },

    async updateChatSettings(itemId: string, settings: ChatUpdate) {
      if (!itemId) return;
      try {
        const updatedChat = await updateChatSettings(itemId, settings);
        const index = this.chatList.findIndex(c => c.id === itemId);
        if (index !== -1) {
          Object.assign(this.chatList[index], updatedChat);
        }
      } catch (error) {
        console.error(`Failed to update settings for item ${itemId}:`, error);
      }
    },

    async deleteItem(itemId: string) {
      try {
        await deleteChat(itemId);
        await this.fetchChatList();
        const currentChatExists = this.chatList.some(c => c.id === this.currentChatId);
        if (!currentChatExists) {
            this.currentChatId = null;
            this.currentChatMessages = [];
        }
      } catch (error) {
        console.error(`Failed to delete item ${itemId}:`, error);
        ElMessage.error('删除失败，请稍后重试。');
      }
    },

    async reorderChatItems(updates: ChatReorderItem[]) {
      updates.forEach(update => {
        const item = this.chatList.find(c => c.id === update.id);
        if (item) {
          item.parentId = update.parentId;
          item.sortOrder = update.sortOrder;
        }
      });
      try {
        await reorderChats(updates);
      } catch (error) {
        console.error('Failed to reorder items:', error);
        await this.fetchChatList();
      }
    },

    async duplicateChat(itemId: string): Promise<Chat | null> {
      try {
        const newChat = await duplicateChat(itemId);
        this.chatList.push(newChat);
        return newChat;
      } catch (error) {
        console.error(`Failed to duplicate chat ${itemId}:`, error);
        return null;
      }
    },

    // --- 消息操作 ---
    async editMessage(payload: { messageId: string, content: string, resend?: boolean }) {
      if (!this.currentChatId) return;
      const { messageId, content, resend = false } = payload;
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      try {
        this.currentChatMessages[messageIndex].content = content;

        const assistantPlaceholder = await updateMessage(messageId, { content, resend });

        if (resend) {
          this.currentChatMessages.splice(messageIndex + 1);
          this.currentChatMessages.push(assistantPlaceholder);
          this._subscribeToMessageStream(assistantPlaceholder);
        }
      } catch (error) {
        console.error('Failed to update message and resend:', error);
        ElMessage.error('操作失败，请重试。');
        await this.selectChat(this.currentChatId);
      }
    },

    async deleteMessage(messageId: string) {
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const deletedMessage = this.currentChatMessages.splice(messageIndex, 1)[0];
      try {
        await deleteMessage(messageId);
      } catch (error)
      {
        console.error('Failed to delete message:', error);
        this.currentChatMessages.splice(messageIndex, 0, deletedMessage);
        ElMessage.error('删除消息失败');
      }
    },

    // --- 对话生成 ---
    saveDraft(content: string) {
      if (this.currentChatId) {
        this.userInputCache[this.currentChatId] = content;
      }
    },

    async sendMessage(content: string) {
      if (!this.currentChatId || this.isGenerating) return;

      const chatId = this.currentChatId;
      delete this.userInputCache[chatId];

      try {
        const tempUserMessage: Message = { id: `temp-user-${Date.now()}`, chatId, role: 'user', content, createdAt: new Date().toISOString(), sortOrder: 99998, status: 'completed' };
        this.currentChatMessages.push(tempUserMessage);

        const assistantPlaceholder = await prepareGenerate(chatId, content);

        const chatWithMessages = await getChatWithMessages(chatId);
        const realUserMessage = chatWithMessages.messages[chatWithMessages.messages.length - 2];
        const tempMsgIndex = this.currentChatMessages.findIndex(m => m.id === tempUserMessage.id);
        if (tempMsgIndex > -1) {
            this.currentChatMessages[tempMsgIndex] = realUserMessage;
        }

        this.currentChatMessages.push(assistantPlaceholder);
        this._subscribeToMessageStream(assistantPlaceholder);
      } catch (error) {
        console.error('Failed to prepare generation:', error);
        ElMessage.error('发送失败，请检查网络或服务配置。');
        const tempMsgIndex = this.currentChatMessages.findIndex(m => m.id.startsWith('temp-user-'));
        if (tempMsgIndex > -1) this.currentChatMessages.splice(tempMsgIndex, 1);
      }
    },

    async regenerateFrom(messageId: string) {
      if (!this.currentChatId || this.isGenerating) return;
      const chatId = this.currentChatId;

      try {
        const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
        if (messageIndex === -1) return;
        const targetMessage = this.currentChatMessages[messageIndex];

        const assistantPlaceholder = await prepareRegenerate(chatId, messageId);

        if (targetMessage.role === 'assistant') {
          this.currentChatMessages.splice(messageIndex);
        } else {
          this.currentChatMessages.splice(messageIndex + 1);
        }
        this.currentChatMessages.push(assistantPlaceholder);

        this._subscribeToMessageStream(assistantPlaceholder);
      } catch (error) {
        console.error('Failed to prepare regeneration:', error);
        ElMessage.error('重新生成失败，请重试。');
      }
    },

    async stopGeneration(messageId: string) {
      const controller = this.activeSubscriptions.get(messageId);
      const messageToUpdate = this.currentChatMessages.find(m => m.id === messageId);

      if (controller && messageToUpdate) {
        // 1. 立即中止前端的长连接
        controller.abort();
        // 2. 立即从 activeSubscriptions 中移除以更新全局UI状态
        this.activeSubscriptions.delete(messageId);
        // 3. 立即更新消息的本地状态，以修复UI（如操作菜单）
        messageToUpdate.status = 'completed';
      } else if (messageToUpdate && messageToUpdate.status === 'generating') {
        // 兜底逻辑：如果订阅不存在但消息状态错误，也进行修正
        messageToUpdate.status = 'completed';
        this.activeSubscriptions.delete(messageId);
      }

      // 4. 异步地向后端发送停止请求，不阻塞UI
      try {
        await stopGenerationAPI(messageId);
      } catch (error) {
        console.error(`Failed to send stop request for message ${messageId}:`, error);
        ElMessage.error('停止请求发送失败');
      }
    },

    stopAllGenerations() {
        this.activeSubscriptions.forEach((_controller, messageId) => {
            this.stopGeneration(messageId);
        });
    },

    // --- 内部辅助方法 ---
    _subscribeToMessageStream(assistantMessage: Message) {
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;
      const assistantMessageId = assistantMessage.id;

      if (this.activeSubscriptions.has(assistantMessageId)) {
        this.stopGeneration(assistantMessageId);
      }

      const controller = new AbortController();
      this.activeSubscriptions.set(assistantMessageId, controller);

      const url = `/api/chats/${chatId}/stream-response/${assistantMessageId}`;

      fetchEventSource(url, {
        method: 'GET',
        signal: controller.signal,
        openWhenHidden: true,
        onmessage: (event) => {
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessageId);
          if (messageToUpdate) {
            try {
              const data = JSON.parse(event.data);
              if (data.type === 'replace') {
                messageToUpdate.content = data.content;
              } else if (data.type === 'append') {
                messageToUpdate.content += data.content;
              }
            } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
          }
        },
        onclose: () => {
          console.log(`[ChatStore] SSE stream closed for messageId: "${assistantMessageId}".`);
          // 确保即使 onclose 先于 stopGeneration 的 delete 调用，也能正确清理
          if (this.activeSubscriptions.has(assistantMessageId)) {
              this.activeSubscriptions.delete(assistantMessageId);
          }
          getChatWithMessages(chatId).then(res => {
              const finalMessage = res.messages.find(m => m.id === assistantMessageId);
              const localMessage = this.currentChatMessages.find(m => m.id === assistantMessageId);
              if (finalMessage && localMessage) {
                  localMessage.status = finalMessage.status;
              }
          });
        },
        onerror: (err) => {
          if (err.name === 'AbortError') {
            console.log(`[ChatStore] Stream aborted by user for messageId: "${assistantMessageId}".`);
            // AbortError 是预期的，当用户点击停止时发生，此时不需要做任何事，onclose会处理后续
          } else {
            console.error(`[ChatStore] SSE stream error for messageId: "${assistantMessageId}". Error:`, err);
          }
        },
      });
    },
  }
});
