import { defineStore } from 'pinia';
import { getChats, createChat, getChatWithMessages, deleteChat } from '@/api/chatService';
import type { Chat, Message, ChatCreate } from '@/api/types';
import { fetchEventSource } from '@microsoft/fetch-event-source';

interface ChatState {
  chatList: Chat[];
  currentChatId: string | null;
  currentChatMessages: Message[];
  isChatListLoading: boolean;
  isChatHistoryLoading: boolean;
  isGenerating: boolean;
}

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    chatList: [],
    currentChatId: null,
    currentChatMessages: [],
    isChatListLoading: false,
    isChatHistoryLoading: false,
    isGenerating: false,
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
      this.currentChatId = chatId;
      this.isChatHistoryLoading = true;
      this.currentChatMessages = [];
      try {
        const chatWithMessages = await getChatWithMessages(chatId);
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
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;

      const userMessage: Message = {
        id: `temp-user-${Date.now()}`,
        chatId: chatId,
        role: 'user',
        content: content,
        createdAt: new Date().toISOString(),
      };
      this.currentChatMessages.push(userMessage);

      // 【关键修复点 1】: 创建一个唯一的临时ID，用于后续在数组中查找
      const assistantMessageId = `temp-assistant-${Date.now()}`;
      const assistantMessage: Message = {
        id: assistantMessageId,
        chatId: chatId,
        role: 'assistant',
        content: '...',
        createdAt: new Date().toISOString(),
      };
      this.currentChatMessages.push(assistantMessage);

      let isFirstChunk = true;
      this.isGenerating = true;

      const apiUrl = `/api/chats/${chatId}/generate`;
      await fetchEventSource(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
        onmessage: (event) => {
          // 【关键修复点 2】: 每次收到消息时，都从 store 的 state 中重新查找消息对象
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessageId);

          if (messageToUpdate) {
            if (isFirstChunk) {
              messageToUpdate.content = ''; // 清空 '...'
              isFirstChunk = false;
            }
            try {
              const chunk = JSON.parse(event.data);
              if (typeof chunk === 'string') {
                // 【关键修复点 3】: 直接修改从 state 中找到的那个响应式对象的属性
                messageToUpdate.content += chunk;
              }
            } catch (e) {
              console.error("Failed to parse SSE data chunk:", event.data, e);
            }
          }
        },
        onclose: () => {
          this.isGenerating = false;
          console.log('SSE Stream closed.');
          // 【可选但推荐】流结束后，发起一次“静默”刷新，以获取后端生成的消息ID和确切时间
          // 这不会打断用户体验，但能保证数据最终一致性
          getChatWithMessages(chatId).then(chat => {
            if (this.currentChatId === chatId) {
              this.currentChatMessages = chat.messages;
            }
          }).catch(error => {
            console.error(`Failed to silently refresh messages for chat ${chatId}:`, error);
          });
        },
        onerror: (err) => {
          this.isGenerating = false;
          const messageToUpdate = this.currentChatMessages.find(m => m.id === assistantMessageId);
          if (messageToUpdate) {
            messageToUpdate.content += '\n\n**抱歉，请求出错，请检查网络或联系管理员。**';
          }
          console.error('EventSource failed:', err);
          throw err;
        },
      });
    }
  }
});
