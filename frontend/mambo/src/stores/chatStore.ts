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
        // 创建后不自动选择，而是让 ChatList 组件处理跳转和选择
        // await this.selectChat(newChat.id);
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

    /**
     * 发送消息并处理流式响应
     */
    async sendMessage(content: string) {
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;

      // 1. 立即在UI上显示用户消息
      const userMessage: Message = {
        id: `temp-user-${Date.now()}`,
        chatId: chatId,
        role: 'user',
        content: content,
        createdAt: new Date().toISOString(),
      };
      this.currentChatMessages.push(userMessage);

      // 2. 创建一个空的助手消息占位符，用于接收流式内容
      const assistantMessage: Message = {
        id: `temp-assistant-${Date.now()}`,
        chatId: chatId,
        role: 'assistant',
        content: '...', // 初始显示加载状态
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
          if (isFirstChunk) {
            assistantMessage.content = ''; // 收到第一个数据块时，清空 '...'
            isFirstChunk = false;
          }
          // 【重要更正】: 后端发送的是JSON编码的字符串，需要解析
          assistantMessage.content += JSON.parse(event.data);
        },
        onclose: async () => {
          // 流结束时，重新从后端获取最新的消息列表，确保数据最终一致
          this.isGenerating = false;
          try {
            const chatWithMessages = await getChatWithMessages(chatId);
            // 仅当用户仍在当前会话时才更新消息列表
            if (this.currentChatId === chatId) {
              this.currentChatMessages = chatWithMessages.messages;
            }
          } catch (error) {
            console.error(`Failed to refresh messages for chat ${chatId}:`, error);
          }
        },
        onerror: (err) => {
          console.error('EventSource failed:', err);
          assistantMessage.content += '\n\n**抱歉，请求出错，请检查网络或联系管理员。**';
          this.isGenerating = false;
          // 必须 re-throw 错误，否则 onclose 仍然会被调用
          throw err;
        },
      });
    }
  }
});
