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
        // 后端负责处理级联删除逻辑，前端只需发送请求
        await deleteChat(itemId);

        // 删除成功后，重新获取列表以确保前后端状态一致
        await this.fetchChatList();

        // 检查当前选中的会话是否已被删除
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

      const originalContent = this.currentChatMessages[messageIndex].content;
      this.currentChatMessages[messageIndex].content = content;

      if (!resend) {
        try {
          await updateMessage(messageId, { content });
        } catch (error) {
          console.error('Failed to update message:', error);
          this.currentChatMessages[messageIndex].content = originalContent;
          ElMessage.error('编辑消息失败');
        }
      } else {
        this.currentChatMessages.splice(messageIndex + 1);
        this._startStreamGeneration(`/api/messages/${messageId}`, 'PUT', { content, resend: true });
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

      const userMessage: Message = { id: `temp-user-${Date.now()}`, chatId, role: 'user', content, createdAt: new Date().toISOString(), sortOrder: 99999 };
      this.currentChatMessages.push(userMessage);

      const useStream = this.currentChat.modelParameters?.stream ?? true;
      if (useStream) {
        this._startStreamGeneration(`/api/chats/${chatId}/generate`, 'POST', { content });
      } else {
        this.isGenerating = true;
        const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
        const assistantMessagePlaceholder: Message = { id: assistantMessagePlaceholderId, chatId, role: 'assistant', content: '', createdAt: new Date().toISOString(), sortOrder: 99999 };
        this.currentChatMessages.push(assistantMessagePlaceholder);

        try {
          const finalMessage = await generateResponseNonStream(chatId, content);

          const messageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
          if (messageIndex !== -1) {
            this.currentChatMessages[messageIndex] = finalMessage;
          }
          const chatWithMessages = await getChatWithMessages(chatId);
          if (this.currentChatId === chatId) {
            this.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);
          }
        } catch (error: unknown) {
          let errorMessage = '请求失败';
          if (typeof error === 'object' && error !== null && 'response' in error) {
            const errResponse = error.response as { data?: { detail?: string } };
            if (errResponse.data?.detail) {
              errorMessage = errResponse.data.detail;
            }
          } else if (error instanceof Error) {
            errorMessage = error.message;
          }
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
          if (messageToUpdate) messageToUpdate.content = `**${errorMessage}**`;
        } finally {
          this.isGenerating = false;
        }
      }
    },

    async regenerateFrom(messageId: string) {
      if (!this.currentChatId || this.isGenerating) return;
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const targetMessage = this.currentChatMessages[messageIndex];

      if (targetMessage.role === 'assistant') {
        this.currentChatMessages.splice(messageIndex);
      } else {
        this.currentChatMessages.splice(messageIndex + 1);
      }

      this._startStreamGeneration(`/api/chats/${this.currentChatId}/regenerate-from/${messageId}`, 'POST', {});
    },

    stopGeneration() {
      if (this.currentRequestController) {
        this.currentRequestController.abort();
        this.isGenerating = false;
        this.currentRequestController = null;
      }
    },

    // --- 内部辅助方法 ---
    _startStreamGeneration(url: string, method: string, body: object) {
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;

      const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
      const assistantMessagePlaceholder: Message = { id: assistantMessagePlaceholderId, chatId, role: 'assistant', content: '', createdAt: new Date().toISOString(), sortOrder: 99999 };
      this.currentChatMessages.push(assistantMessagePlaceholder);

      this.isGenerating = true;
      this.currentRequestController = new AbortController();

      fetchEventSource(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: this.currentRequestController.signal,
        onmessage: (event) => {
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
          if (messageToUpdate) {
            try {
              messageToUpdate.content += JSON.parse(event.data);
            } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
          }
        },
        onclose: () => {
          getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder); });
          this.isGenerating = false;
          this.currentRequestController = null;
        },
        onerror: (err) => {
          this.isGenerating = false;
          this.currentRequestController = null;
          if (err.name === 'AbortError') {
            // 立即移除临时占位符，防止用户操作一个无效的消息
            const tempMessageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
            if (tempMessageIndex !== -1) {
              this.currentChatMessages.splice(tempMessageIndex, 1);
            }
            // 然后从后端同步权威的消息列表
            getChatWithMessages(chatId).then(chat => {
              if (this.currentChatId === chatId) {
                this.currentChatMessages = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder);
              }
            });
          } else {
             const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
             if (messageToUpdate) {
               if (messageToUpdate.content === '') {
                 messageToUpdate.content = '**抱歉，请求出错。**';
               } else {
                 messageToUpdate.content += '\n\n**抱歉，请求出错。**';
               }
             }
             console.error("SSE error:", err);
          }
        },
      });
    },
  }
});
