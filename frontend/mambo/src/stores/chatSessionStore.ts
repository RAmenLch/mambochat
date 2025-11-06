// frontend/mambo/src/stores/chatSessionStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getChatWithMessages } from '@/api/chatService';
import { useChatListStore } from './chatListStore';
import type { Chat, Message, SubMessage } from '@/api/types';
import type { StreamedChunk } from '@/services/sseService';

/**
 * 管理当前激活会话的数据状态。
 * 这个 Store 扮演着当前会话的响应式“数据库”角色，
 * 它只负责存储和管理数据，不直接处理复杂的业务交互逻辑。
 */
export const useChatSessionStore = defineStore('chatSession', () => {
  // --- State ---
  const currentChatId = ref<string | null>(null);
  const currentChatMessages = ref<Message[]>([]);
  const isChatHistoryLoading = ref(false);
  const activeSubscriptions = new Map<string, AbortController>();

  // --- Getters ---

  /**
   * 获取当前激活的会话对象。
   * 数据来源于 chatListStore，确保了单一数据源。
   */
  const currentChat = computed((): Chat | null => {
    const chatListStore = useChatListStore();
    if (!currentChatId.value) return null;
    const chat = chatListStore.chatList.find(c => c.id === currentChatId.value);
    return chat?.itemType === 'chat' ? chat : null;
  });

  /**
   * 判断当前会话是否正在生成消息。
   */
  const isGenerating = computed((): boolean =>
    currentChatMessages.value.some(msg => msg.status === 'generating')
  );

  /**
   * 为 Token 估算器提供上下文。
   * 包含系统提示和最近的消息历史。
   */
  const contextForTokenEstimation = computed((): string => {
    const chat = currentChat.value;
    if (!chat) return '';
    const systemPrompt = chat.systemPrompt || '';
    const maxContext = chat.modelParameters?.max_context_messages ?? 0;
    const messages = maxContext > 0 ? currentChatMessages.value.slice(-maxContext) : currentChatMessages.value;
    const history = messages.map(msg => msg.sub_messages.map(sm => sm.content).join('\n')).join('\n');
    return [systemPrompt, history].filter(Boolean).join('\n');
  });

  // --- Actions ---

  /**
   * 选择并加载一个会话。
   * 这是设置当前会话状态的唯一入口。
   * @param chatId - 要加载的会话ID。
   * @param forceRefresh - 是否强制刷新，即使ID未变。
   */
  async function selectChat(chatId: string, forceRefresh: boolean = false) {
    if (currentChatId.value === chatId && !forceRefresh) return;

    // 停止所有正在进行的SSE订阅
    _clearAllSubscriptions();

    const chatListStore = useChatListStore();
    const item = chatListStore.chatList.find(i => i.id === chatId);

    // 如果选择的是文件夹或无效项，则清空会话
    if (!item || item.itemType === 'folder') {
      clearSession();
      // 仍然设置ID以保持列表高亮
      currentChatId.value = item ? chatId : null;
      return;
    }

    currentChatId.value = chatId;
    isChatHistoryLoading.value = true;
    currentChatMessages.value = [];
    try {
      const chatWithMessages = await getChatWithMessages(chatId);
      // 更新chatListStore中的会话数据，以同步最新信息
      const chatIndex = chatListStore.chatList.findIndex(c => c.id === chatId);
      if (chatIndex !== -1) {
        Object.assign(chatListStore.chatList[chatIndex], chatWithMessages);
      }
      currentChatMessages.value = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);
    } catch (error) {
      console.error(`Failed to fetch messages for chat ${chatId}:`, error);
      clearSession();
    } finally {
      isChatHistoryLoading.value = false;
    }
  }

  /**
   * 清空当前会话的状态。
   */
  function clearSession() {
    currentChatId.value = null;
    currentChatMessages.value = [];
    isChatHistoryLoading.value = false;
    _clearAllSubscriptions();
  }

  // --- Internal Methods (供 chatInteractionStore 调用) ---

  /**
   * (内部) 清理所有活动的SSE订阅。
   * @private
   */
  function _clearAllSubscriptions() {
    activeSubscriptions.forEach(controller => controller.abort());
    activeSubscriptions.clear();
  }

  /**
   * (内部) 向消息列表中添加一条消息。
   * @param message - 要添加的消息对象。
   * @private
   */
  function _addMessage(message: Message) {
    currentChatMessages.value.push(message);
  }

  /**
   * (内部) 从消息列表中移除一条消息。
   * @param messageId - 要移除的消息ID。
   * @returns 被移除的消息对象，如果找到的话。
   * @private
   */
  function _removeMessage(messageId: string): Message | undefined {
    const index = currentChatMessages.value.findIndex(m => m.id === messageId);
    if (index !== -1) {
      return currentChatMessages.value.splice(index, 1)[0];
    }
    return undefined;
  }

  /**
   * (内部) 替换从指定索引开始的所有消息。
   * @param startIndex - 开始替换的索引。
   * @param newMessages - 用于替换的新消息数组。
   * @private
   */
  function _spliceMessages(startIndex: number, newMessages: Message[] = []) {
     currentChatMessages.value.splice(startIndex, currentChatMessages.value.length - startIndex, ...newMessages);
  }

  /**
   * (内部) 更新指定消息的子消息。
   * @param messageId - 目标消息ID。
   * @param subMessages - 新的子消息数组。
   * @private
   */
  function _updateSubMessages(messageId: string, subMessages: SubMessage[]) {
    const message = currentChatMessages.value.find(m => m.id === messageId);
    if (message) {
      message.sub_messages = subMessages;
    }
  }

  /**
   * (内部) 处理SSE流数据块，更新消息状态。
   * @param assistantMessageId - 正在接收流数据的助手消息ID。
   * @param data - 从SSE接收的数据块。
   * @private
   */
  function _processStreamChunk(assistantMessageId: string, data: StreamedChunk) {
    const msgToUpdate = currentChatMessages.value.find(m => m.id === assistantMessageId);
    if (!msgToUpdate) return;

    switch (data.type) {
      case 'replace':
        msgToUpdate.sub_messages = data.sub_messages;
        msgToUpdate.status = data.status;
        break;
      case 'create':
        if (!msgToUpdate.sub_messages.some(sm => sm.id === data.sub_message.id)) {
          msgToUpdate.sub_messages.push(data.sub_message);
          msgToUpdate.sub_messages.sort((a, b) => a.sortOrder - b.sortOrder);
        }
        break;
      case 'append': {
        const subMsg = msgToUpdate.sub_messages.find(sm => sm.id === data.sub_message_id);
        if (subMsg) subMsg.content += data.content;
        break;
      }
      case 'status_update': {
        const subMsg = msgToUpdate.sub_messages.find(sm => sm.id === data.sub_message_id);
        if (subMsg) subMsg.status = data.status;
        break;
      }
    }
  }

  return {
    // State
    currentChatId,
    currentChatMessages,
    isChatHistoryLoading,
    activeSubscriptions,

    // Getters
    currentChat,
    isGenerating,
    contextForTokenEstimation,

    // Actions
    selectChat,
    clearSession,

    // Internal methods for friend stores
    _addMessage,
    _removeMessage,
    _spliceMessages,
    _updateSubMessages,
    _processStreamChunk,
  };
});
