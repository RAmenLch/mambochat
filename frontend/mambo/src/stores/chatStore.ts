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
  regenerateResponseNonStream,
  updateMessage,
  deleteMessage,
} from '@/api/chatService';
import type { Chat, Message, ChatCreate, ChatUpdate, ChatReorderItem } from '@/api/types';
import { fetchEventSource } from '@microsoft/fetch-event-source';

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
          // 如果 chatList 中没有，也直接加载消息
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
        const newItem = await createChat(itemData);
        this.chatList.push(newItem);
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
            if (this.currentChatId && idsToRemove.has(this.currentChatId)) {
                this.currentChatId = null;
                this.currentChatMessages = [];
            }
        } catch (error) {
            console.error(`Failed to delete item ${itemId}:`, error);
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

    // --- 消息操作 ---
    async editMessage(payload: { messageId: string, content: string, resend?: boolean }) {
      if (!this.currentChatId) return;
      const { messageId, content, resend = false } = payload;
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      // 乐观更新UI
      const originalContent = this.currentChatMessages[messageIndex].content;
      this.currentChatMessages[messageIndex].content = content;

      if (!resend) { // 仅保存
        try {
          await updateMessage(messageId, { content });
        } catch (error) {
          console.error('Failed to update message:', error);
          this.currentChatMessages[messageIndex].content = originalContent; // 失败时回滚
          ElMessage.error('编辑消息失败');
        }
      } else { // 保存并重新发送
        this.currentChatMessages.splice(messageIndex + 1); // 删除后续所有消息
        this._startStreamGeneration(`/api/messages/${messageId}`, 'PUT', { content, resend: true });
      }
    },

    async deleteMessage(messageId: string) {
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      // 乐观删除
      const deletedMessage = this.currentChatMessages.splice(messageIndex, 1)[0];
      try {
        await deleteMessage(messageId);
      } catch (error) {
        console.error('Failed to delete message:', error);
        this.currentChatMessages.splice(messageIndex, 0, deletedMessage); // 失败时回滚
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

      delete this.userInputCache[this.currentChatId];

      const userMessage: Message = { id: `temp-user-${Date.now()}`, chatId: this.currentChatId, role: 'user', content, createdAt: new Date().toISOString(), sortOrder: 99999 };
      this.currentChatMessages.push(userMessage);

      const useStream = this.currentChat.modelParameters?.stream ?? true;
      if (useStream) {
        this._startStreamGeneration(`/api/chats/${this.currentChatId}/generate`, 'POST', { content });
      } else {
        this._startNonStreamGeneration(content, generateResponseNonStream);
      }
    },

    async regenerateLastResponse() {
      if (!this.currentChat || this.isGenerating || this.currentChatMessages.length < 1) return;
      const lastUserMessage = [...this.currentChatMessages].reverse().find(m => m.role === 'user');
      if (!lastUserMessage) return;

      if (this.currentChatMessages[this.currentChatMessages.length - 1].role === 'assistant') {
        this.currentChatMessages.pop();
      }

      const useStream = this.currentChat.modelParameters?.stream ?? true;
      if (useStream) {
        this._startStreamGeneration(`/api/chats/${this.currentChatId}/regenerate`, 'POST', { content: lastUserMessage.content });
      } else {
        this._startNonStreamGeneration(lastUserMessage.content, regenerateResponseNonStream);
      }
    },

    async regenerateFrom(messageId: string) {
      if (!this.currentChatId || this.isGenerating) return;
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const targetMessage = this.currentChatMessages[messageIndex];
      const historySlice = this.currentChatMessages.slice(0, messageIndex + 1);
      const lastUserMessage = [...historySlice].reverse().find(m => m.role === 'user');
      if (!lastUserMessage) {
        ElMessage.warning('无法找到用于重新生成的用户输入');
        return;
      }

      // 乐观UI更新
      if (targetMessage.role === 'assistant') {
        this.currentChatMessages.splice(messageIndex);
      } else {
        this.currentChatMessages.splice(messageIndex + 1);
      }

      this._startStreamGeneration(`/api/chats/${this.currentChatId}/regenerate-from/${messageId}`, 'POST', { content: lastUserMessage.content });
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
      const assistantMessagePlaceholder: Message = { id: assistantMessagePlaceholderId, chatId, role: 'assistant', content: '...', createdAt: new Date().toISOString(), sortOrder: 99999 };
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
            if (messageToUpdate.content === '...') messageToUpdate.content = '';
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
            getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder); });
          } else {
             const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
             if (messageToUpdate) messageToUpdate.content += '\n\n**抱歉，请求出错。**';
             console.error("SSE error:", err);
          }
        },
      });
    },

    async _startNonStreamGeneration(content: string, apiCall: (chatId: string, content: string) => Promise<Message>) {
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;

      const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
      const assistantMessagePlaceholder: Message = { id: assistantMessagePlaceholderId, chatId, role: 'assistant', content: '...', createdAt: new Date().toISOString(), sortOrder: 99999 };
      this.currentChatMessages.push(assistantMessagePlaceholder);
      this.isGenerating = true;

      try {
        const finalMessage = await apiCall(chatId, content);
        const messageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
        if (messageIndex !== -1) {
          this.currentChatMessages[messageIndex] = finalMessage;
        } else { // 如果占位符被意外移除，则追加
          this.currentChatMessages.push(finalMessage);
        }
        // 非流式请求也需要刷新用户消息的ID
        const userMessageIndex = this.currentChatMessages.findIndex(m => m.role === 'user' && m.id.startsWith('temp-user'));
        if(userMessageIndex !== -1) {
          getChatWithMessages(chatId).then(chat => { if (this.currentChatId === chatId) this.currentChatMessages = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder); });
        }

      } catch (error: unknown) {
        let errorMessage = '请求失败';
        if (error instanceof Error) {
          errorMessage = error.message;
        }
        // 假设是 axios 类型的错误结构
        if (typeof error === 'object' && error !== null && 'response' in error) {
            const errResponse = error.response as { data?: { detail?: string } };
            if(errResponse.data?.detail) {
                errorMessage = errResponse.data.detail;
            }
        }

        const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
        if (messageToUpdate) messageToUpdate.content = `**${errorMessage}**`;
      } finally {
        this.isGenerating = false;
      }
    },
  }
});
