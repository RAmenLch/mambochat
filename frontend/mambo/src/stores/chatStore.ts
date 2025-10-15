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
  updateMessageAndRegenerate,
  updateSubMessage as updateSubMessageAPI,
  deleteMessage,
  duplicateChat,
  prepareGenerate,
  prepareRegenerate,
  stopGeneration as stopGenerationAPI,
} from '@/api/chatService';
import type {
  Chat,
  Message,
  ChatCreate,
  ChatUpdate,
  ChatReorderItem,
  SubMessageCreate,
  SubMessageUpdate,
} from '@/api/types';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { useProviderStore } from './providerStore';

// --- 常量定义 ---
const GLOBAL_HISTORY_LIMIT = 200;
const CHAT_HISTORY_LIMIT = 50;

// --- 内部类型定义 ---
interface HistoryEntry {
  chatId: string;
  content: string;
}

interface ChatState {
  chatList: Chat[];
  currentChatId: string | null;
  currentChatMessages: Message[];
  isChatListLoading: boolean;
  isChatHistoryLoading: boolean;
  activeSubscriptions: Map<string, AbortController>; // messageId -> AbortController
  history: {
    stack: HistoryEntry[];
    pointer: number;
  };
}

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    chatList: [],
    currentChatId: null,
    currentChatMessages: [],
    isChatListLoading: false,
    isChatHistoryLoading: false,
    activeSubscriptions: new Map(),
    history: {
      stack: [],
      pointer: -1,
    },
  }),

  getters: {
    currentChat: (state): Chat | null => {
      if (!state.currentChatId) return null;
      const chat = state.chatList.find(chat => chat.id === state.currentChatId);
      return chat?.itemType === 'chat' ? chat : null;
    },
    isGenerating(state): boolean {
      return state.currentChatMessages.some(msg =>
        msg.sub_messages.some(sm => sm.status === 'generating')
      );
    },
    currentDraft(state): string {
      if (!state.currentChatId || state.history.pointer < 0) return '';
      // 从当前指针位置向后查找属于当前会话的最新草稿
      for (let i = state.history.pointer; i >= 0; i--) {
        const entry = state.history.stack[i];
        if (entry.chatId === state.currentChatId) {
          return entry.content;
        }
      }
      return '';
    },
    /**
     * 获取用于Token估算的上下文内容, 包括System Prompt和历史消息。
     */
    contextForTokenEstimation(state): string {
      const chat = this.currentChat;
      if (!chat) return '';

      const systemPrompt = chat.systemPrompt || '';

      const maxContext = chat.modelParameters?.max_context_messages ?? 0;
      const messagesToConsider = maxContext > 0
        ? state.currentChatMessages.slice(-maxContext)
        : state.currentChatMessages;

      const historyContent = messagesToConsider
        .map(msg => msg.sub_messages.map(sm => sm.content).join('\n'))
        .join('\n');

      return [systemPrompt, historyContent].filter(Boolean).join('\n');
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

      this.unsubscribeAllClientSide();

      const selectedItem = this.chatList.find(item => item.id === chatId);
      if (!selectedItem || selectedItem.itemType === 'folder') {
        this.currentChatId = selectedItem ? chatId : null;
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
            if (msg.role === 'assistant' && msg.sub_messages.some(sm => sm.status === 'generating')) {
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
    async editMessageAndRegenerate(payload: { messageId: string, sub_messages: SubMessageCreate[], resend?: boolean }) {
      if (!this.currentChatId) return;
      const { messageId, sub_messages, resend = false } = payload;
      const messageIndex = this.currentChatMessages.findIndex(m => m.id === messageId);
      if (messageIndex === -1) return;

      const chatId = this.currentChatId;

      try {
        await updateMessageAndRegenerate(messageId, { sub_messages, resend });
        const chatWithMessages = await getChatWithMessages(chatId);
        this.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);

        if (resend) {
          const assistantPlaceholder = this.currentChatMessages[this.currentChatMessages.length - 1];
          if (assistantPlaceholder && assistantPlaceholder.role === 'assistant' && assistantPlaceholder.sub_messages.some(sm => sm.status === 'generating')) {
            this._subscribeToMessageStream(assistantPlaceholder);
          }
        }
      } catch (error) {
        console.error('Failed to update message and resend:', error);
        ElMessage.error('操作失败，正在尝试恢复会话状态...');
        await this.selectChat(chatId);
      }
    },

    async updateSubMessage(payload: { subMessageId: string, data: SubMessageUpdate }) {
      const { subMessageId, data } = payload;
      for (const message of this.currentChatMessages) {
        const subMessage = message.sub_messages.find(sm => sm.id === subMessageId);
        if (subMessage) {
          if (data.content !== undefined) subMessage.content = data.content;
          if (data.config !== undefined) subMessage.config = data.config;
          if (data.status !== undefined) subMessage.status = data.status;
          break;
        }
      }

      try {
        await updateSubMessageAPI(subMessageId, data);
      } catch (error) {
        console.error(`Failed to update sub-message ${subMessageId}:`, error);
        ElMessage.error('更新失败');
        if (this.currentChatId) await this.selectChat(this.currentChatId);
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

    // --- 对话生成与草稿历史 ---
    _pushToHistory(entry: HistoryEntry) {
      // 如果指针不在栈顶,说明进行过撤销操作,此时新的输入会覆盖掉“未来”的历史
      if (this.history.pointer < this.history.stack.length - 1) {
        this.history.stack.splice(this.history.pointer + 1);
      }

      this.history.stack.push(entry);

      // 应用单个会话的历史限制
      const chatEntries = this.history.stack.filter(e => e.chatId === entry.chatId);
      if (chatEntries.length > CHAT_HISTORY_LIMIT) {
        const oldestIndex = this.history.stack.findIndex(e => e.chatId === entry.chatId);
        if (oldestIndex !== -1) {
          this.history.stack.splice(oldestIndex, 1);
        }
      }

      // 应用全局历史限制
      if (this.history.stack.length > GLOBAL_HISTORY_LIMIT) {
        this.history.stack.shift();
      }

      // 更新指针到栈顶
      this.history.pointer = this.history.stack.length - 1;
    },

    saveDraft(content: string) {
      if (!this.currentChatId) return;

      const latestEntry = this.history.stack[this.history.pointer];
      // 避免连续存入完全相同的草稿
      if (latestEntry && latestEntry.chatId === this.currentChatId && latestEntry.content === content) {
        return;
      }

      this._pushToHistory({ chatId: this.currentChatId, content });
    },

    undo() {
      if (!this.currentChatId || this.history.pointer < 0) return;

      // 从当前指针的前一个位置开始,向后查找属于当前会话的记录
      for (let i = this.history.pointer - 1; i >= 0; i--) {
        if (this.history.stack[i].chatId === this.currentChatId) {
          this.history.pointer = i;
          return;
        }
      }
    },

    redo() {
      if (!this.currentChatId || this.history.pointer >= this.history.stack.length - 1) return;

      // 从当前指针的后一个位置开始,向前查找属于当前会话的记录
      for (let i = this.history.pointer + 1; i < this.history.stack.length; i++) {
        if (this.history.stack[i].chatId === this.currentChatId) {
          this.history.pointer = i;
          return;
        }
      }
    },

    async sendMessage(sub_messages: SubMessageCreate[]) {
      if (!this.currentChatId || this.isGenerating) return;

      const chatId = this.currentChatId;
      this.saveDraft(''); // 发送后清空草稿

      try {
        const lastMessage = this.currentChatMessages[this.currentChatMessages.length - 1];
        const tempUserMessage: Message = {
          id: `temp-user-${Date.now()}`,
          chatId,
          role: 'user',
          sub_messages: sub_messages.map((sm, index) => ({
            ...sm,
            id: `temp-sub-${index}`,
            createdAt: new Date().toISOString(),
            messageId: `temp-user-${Date.now()}`,
            type: sm.type || 'Normal',
            config: sm.config || { is_collapsed: false },
            status: 'completed',
          })),
          createdAt: new Date().toISOString(),
          sortOrder: (lastMessage?.sortOrder ?? -1) + 1,
        };
        this.currentChatMessages.push(tempUserMessage);

        const assistantPlaceholder = await prepareGenerate(chatId, { sub_messages });

        const chatWithMessages = await getChatWithMessages(chatId);
        const realUserMessage = chatWithMessages.messages[chatWithMessages.messages.length - 2];
        const tempMsgIndex = this.currentChatMessages.findIndex(m => m.id === tempUserMessage.id);
        if (tempMsgIndex > -1 && realUserMessage) {
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

    _unsubscribeClientSide(messageId: string) {
        const controller = this.activeSubscriptions.get(messageId);
        if (controller) {
            controller.abort();
        }
        this.activeSubscriptions.delete(messageId);
    },

    unsubscribeAllClientSide() {
        this.activeSubscriptions.forEach((_controller, messageId) => {
            this._unsubscribeClientSide(messageId);
        });
    },

    async cancelGeneration(messageId: string) {
      this._unsubscribeClientSide(messageId);

      const messageToUpdate = this.currentChatMessages.find(m => m.id === messageId);
      if (messageToUpdate) {
        const subMessageToUpdate = messageToUpdate.sub_messages.find(sm => sm.status === 'generating');
        if (subMessageToUpdate) {
            subMessageToUpdate.status = 'completed';
        }
      }

      try {
        await stopGenerationAPI(messageId);
      } catch (error) {
        console.error(`Failed to send stop request for message ${messageId}:`, error);
      }
    },

    stopAllGenerations() {
        this.activeSubscriptions.forEach((_controller, messageId) => {
            this.cancelGeneration(messageId);
        });
    },

    // --- 内部辅助方法 ---
    _subscribeToMessageStream(assistantMessage: Message) {
      if (!this.currentChatId) return;
      const chatId = this.currentChatId;
      const assistantMessageId = assistantMessage.id;

      if (this.activeSubscriptions.has(assistantMessageId)) {
        this._unsubscribeClientSide(assistantMessageId);
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
          if (!messageToUpdate) return;

          try {
            const data = JSON.parse(event.data);
            if (data.type === 'replace') {
              messageToUpdate.sub_messages = data.sub_messages;
            } else if (data.type === 'append') {
              const subMessageToUpdate = messageToUpdate.sub_messages.find(sm => sm.id === data.sub_message_id);
              if (subMessageToUpdate) {
                subMessageToUpdate.content += data.content;
              }
            }
          } catch (e) { console.error("Failed to parse SSE data chunk:", event.data, e); }
        },
        onclose: () => {
          this.activeSubscriptions.delete(assistantMessageId);
          getChatWithMessages(chatId).then(res => {
              const finalMessage = res.messages.find(m => m.id === assistantMessageId);
              const localMessage = this.currentChatMessages.find(m => m.id === assistantMessageId);
              if (finalMessage && localMessage) {
                  localMessage.sub_messages = finalMessage.sub_messages;
              }
          }).catch(err => console.error("Failed to fetch final message state on close:", err));
        },
        onerror: (err) => {
          if (err.name !== 'AbortError') {
            console.error(`[ChatStore] SSE stream error for messageId: "${assistantMessageId}". Error:`, err);
          }
          this.activeSubscriptions.delete(assistantMessageId);
          getChatWithMessages(chatId).then(res => {
              const finalMessage = res.messages.find(m => m.id === assistantMessageId);
              const localMessage = this.currentChatMessages.find(m => m.id === assistantMessageId);
              if (finalMessage && localMessage) {
                  localMessage.sub_messages = finalMessage.sub_messages;
              }
          }).catch(err => console.error("Failed to fetch final message state on error:", err));
        },
      });
    },
  }
});
