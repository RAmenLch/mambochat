// frontend/mambo/src/stores/chatStore.ts

import { defineStore } from 'pinia';
import {
  getChats,
  createChat,
  getChatWithMessages,
  deleteChat,
  updateChatSettings,
  reorderChats, // 新增导入
} from '@/api/chatService';
import type { Chat, Message, ChatCreate, ChatUpdate, ChatReorderItem } from '@/api/types';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import apiClient from '@/api';

// 临时模拟 API 函数
const generateResponseNonStream = (chatId: string, content: string): Promise<Message> => {
    return apiClient.post(`/chats/${chatId}/generate-non-stream`, { content }).then(res => res.data);
};
const regenerateResponseNonStream = (chatId: string, content: string): Promise<Message> => {
    return apiClient.post(`/chats/${chatId}/regenerate-non-stream`, { content }).then(res => res.data);
};


interface ChatState {
  chatList: Chat[];
  currentChatId: string | null;
  currentChatMessages: Message[];
  isChatListLoading: boolean;
  isChatHistoryLoading: boolean;
  isGenerating: boolean;
  currentRequestController: AbortController | null;
  // --- 新增状态，用于缓存各会话的输入草稿 ---
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
      // 确保返回的是会话而不是文件夹
      return chat?.itemType === 'chat' ? chat : null;
    }
  },

  actions: {
    async fetchChatList() {
      this.isChatListLoading = true;
      try {
        // 后端已按 sortOrder 排序，前端直接使用
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
      // 如果选择的是文件夹，则不加载消息
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
          const { messages, ...chatDetails } = chatWithMessages;
          this.chatList[chatIndex] = { ...this.chatList[chatIndex], ...chatDetails };
        }
        this.currentChatMessages = chatWithMessages.messages;
      } catch (error) {
        console.error(`Failed to fetch messages for chat ${chatId}:`, error);
        this.currentChatId = null;
      } finally {
        this.isChatHistoryLoading = false;
      }
    },

    async createNewItem(itemData: ChatCreate): Promise<Chat | null> {
      try {
        const newItem = await createChat(itemData);
        this.chatList.push(newItem); // 直接添加到列表末尾
        return newItem;
      } catch (error) {
        console.error('Failed to create new item:', error);
        return null;
      }
    },

    async updateChatSettings(settings: ChatUpdate) {
      if (!this.currentChatId) return;
      try {
        const updatedChat = await updateChatSettings(this.currentChatId, settings);
        const index = this.chatList.findIndex(c => c.id === this.currentChatId);
        if (index !== -1) {
          this.chatList[index] = updatedChat;
        }
      } catch (error) {
        console.error('Failed to update chat settings:', error);
      }
    },

    async deleteItem(itemId: string) {
        const itemToDelete = this.chatList.find(c => c.id === itemId);
        if (!itemToDelete) return;

        try {
            await deleteChat(itemId);

            const idsToRemove = new Set<string>([itemId]);
            // 如果是文件夹，递归查找所有子项以从本地状态中一并移除
            if (itemToDelete.itemType === 'folder') {
                const findChildren = (parentId: string) => {
                    this.chatList.forEach(item => {
                        if (item.parentId === parentId) {
                            idsToRemove.add(item.id);
                            findChildren(item.id);
                        }
                    });
                };
                findChildren(itemId);
            }

            this.chatList = this.chatList.filter(c => !idsToRemove.has(c.id));

            // 如果删除的是当前选中的项，则清空选择
            if (this.currentChatId && idsToRemove.has(this.currentChatId)) {
                this.currentChatId = null;
                this.currentChatMessages = [];
            }
        } catch (error) {
            console.error(`Failed to delete item ${itemId}:`, error);
        }
    },

    async reorderChatItems(updates: ChatReorderItem[]) {
      // 乐观更新UI
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
        // 如果失败，重新从服务器获取列表以恢复状态
        await this.fetchChatList();
      }
    },

    saveDraft(content: string) {
      if (this.currentChatId) {
        this.userInputCache[this.currentChatId] = content;
      }
    },

    async sendMessage(content: string) {
      if (!this.currentChatId || !this.currentChat || this.isGenerating) return;

      // 发送后清空草稿
      delete this.userInputCache[this.currentChatId];

      const chatId = this.currentChatId;
      const useStream = this.currentChat.modelParameters?.stream ?? true;

      const userMessage: Message = { id: `temp-user-${Date.now()}`, chatId, role: 'user', content, createdAt: new Date().toISOString() };
      this.currentChatMessages.push(userMessage);

      const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
      const assistantMessagePlaceholder: Message = { id: assistantMessagePlaceholderId, chatId, role: 'assistant', content: '...', createdAt: new Date().toISOString() };
      this.currentChatMessages.push(assistantMessagePlaceholder);

      this.isGenerating = true;

      if (useStream) {
        this.currentRequestController = new AbortController();
        await fetchEventSource(`/api/chats/${chatId}/generate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content }),
          signal: this.currentRequestController.signal,
          onmessage: (event) => {
            const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
            if (messageToUpdate) {
              if (messageToUpdate.content === '...') messageToUpdate.content = '';
              try {
                messageToUpdate.content += JSON.parse(event.data);
              } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
            }
          },
          onclose: () => {
            getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages; });
            this.isGenerating = false;
            this.currentRequestController = null;
          },
          onerror: (err) => {
            this.isGenerating = false;
            this.currentRequestController = null;
            if (err.name === 'AbortError') {
              getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages; });
            } else {
               const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
               if (messageToUpdate) messageToUpdate.content += '\n\n**抱歉，请求出错。**';
               console.error("SSE error:", err);
            }
          },
        });
      } else {
        try {
          const finalMessage = await generateResponseNonStream(chatId, content);
          const messageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
          if (messageIndex !== -1) this.currentChatMessages[messageIndex] = finalMessage;
        } catch (error: any) {
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
          if (messageToUpdate) messageToUpdate.content = `**请求失败**: ${error.response?.data?.detail || error.message}`;
        } finally {
          this.isGenerating = false;
        }
      }
    },

    async regenerateLastResponse() {
        if (!this.currentChatId || !this.currentChat || this.isGenerating || this.currentChatMessages.length < 1) return;

        const chatId = this.currentChatId;
        const useStream = this.currentChat.modelParameters?.stream ?? true;
        const lastUserMessage = [...this.currentChatMessages].reverse().find(m => m.role === 'user');
        if (!lastUserMessage) return;

        if (this.currentChatMessages[this.currentChatMessages.length - 1].role === 'assistant') this.currentChatMessages.pop();

        const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
        const assistantMessagePlaceholder: Message = { id: assistantMessagePlaceholderId, chatId, role: 'assistant', content: '...', createdAt: new Date().toISOString() };
        this.currentChatMessages.push(assistantMessagePlaceholder);

        this.isGenerating = true;

        if (useStream) {
          this.currentRequestController = new AbortController();
          await fetchEventSource(`/api/chats/${chatId}/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: lastUserMessage.content }),
            signal: this.currentRequestController.signal,
            onmessage: (event) => {
              const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
              if (messageToUpdate) {
                if (messageToUpdate.content === '...') messageToUpdate.content = '';
                try {
                  messageToUpdate.content += JSON.parse(event.data);
                } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
              }
            },
            onclose: () => {
              getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages; });
              this.isGenerating = false;
              this.currentRequestController = null;
            },
            onerror: (err) => {
              this.isGenerating = false;
              this.currentRequestController = null;
              if (err.name === 'AbortError') {
                getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages; });
              } else {
                const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
                if (messageToUpdate) messageToUpdate.content += '\n\n**抱歉，重新生成时出错。**';
              }
            },
          });
        } else {
            try {
              const finalMessage = await regenerateResponseNonStream(chatId, lastUserMessage.content);
              const messageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
              if (messageIndex !== -1) this.currentChatMessages[messageIndex] = finalMessage;
            } catch (error: any) {
              const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
              if (messageToUpdate) messageToUpdate.content = `**请求失败**: ${error.response?.data?.detail || error.message}`;
            } finally {
              this.isGenerating = false;
            }
        }
    },

    stopGeneration() {
      if (this.currentRequestController) {
        this.currentRequestController.abort();
        this.isGenerating = false;
        this.currentRequestController = null;
      }
    }
  }
});
