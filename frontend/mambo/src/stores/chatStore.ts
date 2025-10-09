// frontend/mambo/src/stores/chatStore.ts

import { defineStore } from 'pinia';
import {
  getChats,
  createChat,
  getChatWithMessages,
  deleteChat,
  updateChatSettings,
} from '@/api/chatService';
import type { Chat, Message, ChatCreate, ChatUpdate } from '@/api/types';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import apiClient from '@/api';

// 临时模拟 API 函数，你应该在 chatService.ts 中正式实现它们
const generateResponseNonStream = (chatId: string, content: string): Promise<Message> => {
    return apiClient.post(`/chats/${chatId}/generate-non-stream`, { content }).then(res => res.data);
};
// 注意: 你需要在后端为非流式重新生成创建一个新接口
const regenerateResponseNonStream = (chatId: string, content: string): Promise<Message> => {
    // 假设后端创建了一个名为 /regenerate-non-stream 的新接口
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
  }),

  getters: {
    currentChat: (state): Chat | null => {
      return state.chatList.find(chat => chat.id === state.currentChatId) || null;
    }
  },

  actions: {
    async fetchChatList() {
      this.isChatListLoading = true;
      try {
        const chats = await getChats();
        this.chatList = chats.sort((a, b) =>
          new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
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
      this.currentChatId = chatId;
      this.isChatHistoryLoading = true;
      this.currentChatMessages = [];
      try {
        const chatWithMessages = await getChatWithMessages(chatId);
        // 更新 chatList 中的会话信息，因为它可能包含更新后的模型参数等
        const chatIndex = this.chatList.findIndex(c => c.id === chatId);
        if (chatIndex !== -1) {
          // 只更新 chat 级别的属性，不替换 messages 数组的引用
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

    async createNewChat(chatData: ChatCreate): Promise<Chat | null> {
      try {
        const newChat = await createChat(chatData);
        this.chatList.unshift(newChat);
        return newChat;
      } catch (error) {
        console.error('Failed to create new chat:', error);
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

    async deleteSelectedChat() {
      if (!this.currentChatId) return;
      const chatIdToDelete = this.currentChatId;
      try {
        await deleteChat(chatIdToDelete);
        this.chatList = this.chatList.filter(c => c.id !== chatIdToDelete);
        this.currentChatId = null;
        this.currentChatMessages = [];
      } catch (error) {
        console.error(`Failed to delete chat ${chatIdToDelete}:`, error);
      }
    },

    async sendMessage(content: string) {
      if (!this.currentChatId || !this.currentChat || this.isGenerating) return;

      const chatId = this.currentChatId;
      const useStream = this.currentChat.modelParameters?.stream ?? true;

      const userMessage: Message = {
        id: `temp-user-${Date.now()}`,
        chatId: chatId,
        role: 'user',
        content: content,
        createdAt: new Date().toISOString(),
      };
      this.currentChatMessages.push(userMessage);

      // AI占位消息
      const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
      const assistantMessagePlaceholder: Message = {
        id: assistantMessagePlaceholderId,
        chatId: chatId,
        role: 'assistant',
        content: '...', // 初始显示为 "正在输入"
        createdAt: new Date().toISOString(),
      };
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
              if (messageToUpdate.content === '...') {
                messageToUpdate.content = '';
              }
              try {
                const chunk = JSON.parse(event.data);
                messageToUpdate.content += chunk;
              } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
            }
          },
          onclose: () => {
            // 流正常关闭，同步最终数据
            getChatWithMessages(chatId).then(chat => {
              if (this.currentChatId === chatId) {
                this.currentChatMessages = chat.messages;
              }
            });
            this.isGenerating = false;
            this.currentRequestController = null;
          },
          onerror: (err) => {
            this.isGenerating = false;
            this.currentRequestController = null;
            // 如果是用户主动取消，则静默处理并同步部分内容
            if (err.name === 'AbortError') {
              console.log('Stream generation aborted by user.');
              getChatWithMessages(chatId).then(chat => {
                if (this.currentChatId === chatId) {
                  this.currentChatMessages = chat.messages;
                }
              });
            } else {
              // 其他错误，显示错误信息
               const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
               if (messageToUpdate) {
                  messageToUpdate.content += '\n\n**抱歉，请求出错。**';
               }
               console.error("SSE error:", err);
            }
          },
        });

      } else {
        // ... 非流式逻辑 ...
        try {
          const finalMessage = await generateResponseNonStream(chatId, content);
          const messageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
          if (messageIndex !== -1) {
            this.currentChatMessages[messageIndex] = finalMessage;
          }
        } catch (error: any) {
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
          if (messageToUpdate) {
            messageToUpdate.content = `**请求失败**: ${error.response?.data?.detail || error.message}`;
          }
          console.error('Non-stream generation failed:', error);
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

        // 移除旧的 assistant 回复
        if (this.currentChatMessages[this.currentChatMessages.length - 1].role === 'assistant') {
          this.currentChatMessages.pop();
        }

        const assistantMessagePlaceholderId = `temp-assistant-${Date.now()}`;
        const assistantMessagePlaceholder: Message = {
          id: assistantMessagePlaceholderId,
          chatId: chatId,
          role: 'assistant',
          content: '...',
          createdAt: new Date().toISOString(),
        };
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
                if (messageToUpdate.content === '...') {
                  messageToUpdate.content = '';
                }
                try {
                  const chunk = JSON.parse(event.data);
                  messageToUpdate.content += chunk;
                } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
              }
            },
            onclose: () => {
              getChatWithMessages(chatId).then(chat => {
                if (this.currentChatId === chatId) {
                  this.currentChatMessages = chat.messages;
                }
              });
              this.isGenerating = false;
              this.currentRequestController = null;
            },
            onerror: (err) => {
              this.isGenerating = false;
              this.currentRequestController = null;
              if (err.name === 'AbortError') {
                console.log('Stream regeneration aborted by user.');
                getChatWithMessages(chatId).then(chat => {
                  if (this.currentChatId === chatId) {
                    this.currentChatMessages = chat.messages;
                  }
                });
              } else {
                const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
                if (messageToUpdate) {
                  messageToUpdate.content += '\n\n**抱歉，重新生成时出错。**';
                }
                console.error("SSE error on regenerate:", err);
              }
            },
          });
        } else {
            // ... 非流式逻辑 ...
            try {
              const finalMessage = await regenerateResponseNonStream(chatId, lastUserMessage.content);
              const messageIndex = this.currentChatMessages.findIndex(m => m.id === assistantMessagePlaceholderId);
              if (messageIndex !== -1) {
                this.currentChatMessages[messageIndex] = finalMessage;
              }
            } catch (error: any) {
              const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessagePlaceholderId);
              if (messageToUpdate) {
                messageToUpdate.content = `**请求失败**: ${error.response?.data?.detail || error.message}`;
              }
              console.error('Non-stream regeneration failed:', error);
            } finally {
              this.isGenerating = false;
            }
        }
    },

    stopGeneration() {
      if (this.currentRequestController) {
        this.currentRequestController.abort();
        // --- 核心修复: 立即重置状态以快速更新UI ---
        this.isGenerating = false;
        this.currentRequestController = null;
      }
    }
  }
});
