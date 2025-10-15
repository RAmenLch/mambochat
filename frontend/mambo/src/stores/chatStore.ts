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
  stopGeneration as stopGenerationAPI, // 保持原有的API导入名称，方便区分
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

interface ChatState {
  chatList: Chat[];
  currentChatId: string | null;
  currentChatMessages: Message[];
  isChatListLoading: boolean;
  isChatHistoryLoading: boolean;
  activeSubscriptions: Map<string, AbortController>; // messageId -> AbortController
  userInputCache: Record<string, string>; // 用于简单输入模式的草稿
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
      // 检查任何子消息的状态是否为 'generating'
      return state.currentChatMessages.some(msg =>
        msg.sub_messages.some(sm => sm.status === 'generating')
      );
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

      // 在切换会话时，仅取消所有前端SSE订阅，不发送后端停止请求。
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

        // 检查是否有未完成的生成任务，并重新订阅
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
        // 调用API, API会完成DB的更新 (包括替换SubMessages) 和后续消息的删除
        await updateMessageAndRegenerate(messageId, { sub_messages, resend });

        // 从服务器获取最新的、完全同步的消息列表，确保前端拥有最新的消息和子消息ID
        const chatWithMessages = await getChatWithMessages(chatId);
        this.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);

        // 如果触发了重新生成, 需要为新的占位符消息启动流式订阅
        if (resend) {
          const assistantPlaceholder = this.currentChatMessages[this.currentChatMessages.length - 1];
          if (assistantPlaceholder && assistantPlaceholder.role === 'assistant' && assistantPlaceholder.sub_messages.some(sm => sm.status === 'generating')) {
            this._subscribeToMessageStream(assistantPlaceholder);
          }
        }
      } catch (error) {
        console.error('Failed to update message and resend:', error);
        ElMessage.error('操作失败，正在尝试恢复会话状态...');
        // 如果失败, 也通过重新拉取数据来确保状态一致性
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

    // --- 对话生成 ---
    saveDraft(content: string) {
      if (this.currentChatId) {
        this.userInputCache[this.currentChatId] = content;
      }
    },

    async sendMessage(sub_messages: SubMessageCreate[]) {
      if (!this.currentChatId || this.isGenerating) return;

      const chatId = this.currentChatId;
      delete this.userInputCache[chatId];

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

    /**
     * 【新增】私有辅助方法：仅取消前端SSE订阅，不通知后端停止任务。
     * 用于切换会话或在`cancelGeneration`中被调用。
     */
    _unsubscribeClientSide(messageId: string) {
        const controller = this.activeSubscriptions.get(messageId);
        if (controller) {
            controller.abort(); // 终止前端SSE连接
        }
        this.activeSubscriptions.delete(messageId);
        // 不修改 UI 状态，因为后端任务可能仍在运行
    },

    /**
     * 【新增】取消所有活跃的前端SSE订阅。
     * 在切换会话时调用，以避免资源泄露。
     */
    unsubscribeAllClientSide() {
        this.activeSubscriptions.forEach((_controller, messageId) => {
            this._unsubscribeClientSide(messageId);
        });
    },

    /**
     * 【重命名】用户明确点击“停止”按钮时调用，会通知后端停止生成任务。
     * 同时会乐观更新前端UI状态。
     */
    async cancelGeneration(messageId: string) {
      // 1. 先取消前端订阅
      this._unsubscribeClientSide(messageId);

      // 2. 乐观更新 UI 状态为 completed
      const messageToUpdate = this.currentChatMessages.find(m => m.id === messageId);
      if (messageToUpdate) {
        const subMessageToUpdate = messageToUpdate.sub_messages.find(sm => sm.status === 'generating');
        if (subMessageToUpdate) {
            subMessageToUpdate.status = 'completed';
        }
      }

      // 3. 通知后端停止生成任务
      try {
        await stopGenerationAPI(messageId);
      } catch (error) {
        console.error(`Failed to send stop request for message ${messageId}:`, error);
      }
    },

    /**
     * 停止所有正在进行的AI生成任务（包括通知后端）。
     * 此方法在`cancelGeneration`重命名后，会自然地调用`cancelGeneration`。
     */
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

      // 如果已经有订阅，先取消旧的订阅
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
          // 连接关闭时，从 activeSubscriptions 移除
          this.activeSubscriptions.delete(assistantMessageId);
          // 重新从后端获取消息的最终状态，确保 UI 与数据库一致
          getChatWithMessages(chatId).then(res => {
              const finalMessage = res.messages.find(m => m.id === assistantMessageId);
              const localMessage = this.currentChatMessages.find(m => m.id === assistantMessageId);
              if (finalMessage && localMessage) {
                  // 替换整个 sub_messages 数组，以确保状态（如 'completed' 或 'failed'）同步
                  localMessage.sub_messages = finalMessage.sub_messages;
              }
          }).catch(err => console.error("Failed to fetch final message state on close:", err));
        },
        onerror: (err) => {
          if (err.name !== 'AbortError') { // AbortError 是主动取消时的预期错误
            console.error(`[ChatStore] SSE stream error for messageId: "${assistantMessageId}". Error:`, err);
          }
          // 确保在出错时也从 activeSubscriptions 移除
          this.activeSubscriptions.delete(assistantMessageId);
          // 同样，尝试获取最终状态
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
