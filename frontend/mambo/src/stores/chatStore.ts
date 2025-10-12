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
  generateResponseNonStream,
  updateMessage,
  deleteMessage,
  duplicateChat,
  prepareGenerate,
  prepareRegenerate,
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
  isGenerating: boolean;
  currentRequestController: AbortController | null;
  userInputCache: Record<string, string>;
}

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    chatList: [],
    currentChatId: null,
    currentChatMessages: [],
    isChatListLoading: false,
    isChatHistoryLoading: false,
    isGenerating: false,
    currentRequestController: null,
    userInputCache: {},
  }),

  getters: {
    currentChat: (state): Chat | null => {
      if (!state.currentChatId) return null;
      const chat = state.chatList.find(chat => chat.id === state.currentChatId);
      return chat?.itemType === 'chat' ? chat : null;
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
      if (this.isGenerating) {
        this.stopGeneration();
      }

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
          this._startStreamGeneration(assistantPlaceholder);
        }
      } catch (error) {
        console.error('Failed to update message and resend:', error);
        ElMessage.error('操作失败，请重试。');
        await this.selectChat(this.currentChatId); // 失败时回滚
      }
    },

    async deleteMessage(messageId: string) {
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const deletedMessage = this.currentChatMessages.splice(messageIndex, 1)[0];
      try {
        await deleteMessage(messageId);
      } catch (error) {
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
      if (!this.currentChatId || !this.currentChat || this.isGenerating) return;

      const chatId = this.currentChatId;
      delete this.userInputCache[chatId];

      const useStream = this.currentChat.modelParameters?.stream ?? true;
      if (useStream) {
        try {
          const tempUserMessage: Message = { id: `temp-user-${Date.now()}`, chatId, role: 'user', content, createdAt: new Date().toISOString(), sortOrder: 99998 };
          this.currentChatMessages.push(tempUserMessage);

          const assistantPlaceholder = await prepareGenerate(chatId, content);

          const lastUserMessageIndex = this.currentChatMessages.length - 1;
          const lastButOneMessage = await getChatWithMessages(chatId).then(res => res.messages[res.messages.length - 2]);
          this.currentChatMessages[lastUserMessageIndex] = lastButOneMessage;

          this.currentChatMessages.push(assistantPlaceholder);
          this._startStreamGeneration(assistantPlaceholder);
        } catch (error) {
          console.error('Failed to prepare generation:', error);
          ElMessage.error('发送失败，请检查网络或服务配置。');
          const tempMsgIndex = this.currentChatMessages.findIndex(m => m.id.startsWith('temp-user-'));
          if (tempMsgIndex > -1) this.currentChatMessages.splice(tempMsgIndex, 1);
        }
      } else {
        // 非流式逻辑保持不变
        this.isGenerating = true;
        try {
          const userMessage: Message = { id: `temp-user-${Date.now()}`, chatId, role: 'user', content, createdAt: new Date().toISOString(), sortOrder: 99999 };
          this.currentChatMessages.push(userMessage);
          await generateResponseNonStream(chatId, content);
          await this.selectChat(chatId);
        } catch (error) {
            console.error('Non-stream generation failed:', error);
        } finally {
            this.isGenerating = false;
        }
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

        this._startStreamGeneration(assistantPlaceholder);
      } catch (error) {
        console.error('Failed to prepare regeneration:', error);
        ElMessage.error('重新生成失败，请重试。');
      }
    },

    stopGeneration() {
      if (this.currentRequestController) {
        // 1. 中止网络请求
        this.currentRequestController.abort();

        // 2. 立即、同步地重置所有控制UI状态的变量
        this.isGenerating = false;
        this.currentRequestController = null;
      }
    },

    // --- 内部辅助方法 ---
    _startStreamGeneration(assistantMessage: Message) {
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;
      const assistantMessageId = assistantMessage.id;

      this.isGenerating = true;
      this.currentRequestController = new AbortController();

      const url = `/api/chats/${chatId}/stream-response/${assistantMessageId}`;

      fetchEventSource(url, {
        method: 'GET',
        signal: this.currentRequestController.signal,
        onmessage: (event) => {
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessageId);
          if (messageToUpdate) {
            try {
              messageToUpdate.content += JSON.parse(event.data);
            } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
          }
        },
        onclose: () => {
          console.log(`[ChatStore DEBUG] SSE stream closed for messageId: "${assistantMessageId}".`);
          this.isGenerating = false;
          this.currentRequestController = null;
        },
        onerror: (err) => {
          // 如果 isGenerating 已经是 false，说明 stopGeneration 已被调用，这是预期的中止
          if (!this.isGenerating && err.name === 'AbortError') {
            console.log('[ChatStore DEBUG] Stream aborted by user.');
            return;
          }

          // 处理意外错误
          console.error(`[ChatStore DEBUG] SSE stream error for messageId: "${assistantMessageId}". Error:`, err);
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessageId);
          if(messageToUpdate) {
              messageToUpdate.content += '\n\n**抱歉，请求出错，请检查网络或服务配置。**';
          }
          this.isGenerating = false;
          this.currentRequestController = null;
        },
      });
    },
  }
});
