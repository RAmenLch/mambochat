// frontend/mambo/src/stores/chatSessionStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { getChatWithMessages } from '@/api/chatService';
import { useChatListStore } from './chatListStore';
import { useChatInteractionStore } from './chatInteractionStore';
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
   * 包含系统提示和经过`context_participation_length`规则筛选的最近消息历史。
   *
   * 逻辑：
   * 1. 优先寻找最后一个已启用的 ZipHistory 子消息作为锚点。
   * 2. 如果找到锚点，上下文 = SystemPrompt + ZipContent + 锚点之后且符合CPL规则的消息。
   * 3. 如果未找到，上下文 = SystemPrompt + 所有符合CPL规则的消息 (受 max_context_messages 限制)。
   * 4. CPL规则：对每条历史消息计算其“新旧程度排名”，并根据其子消息的CPL值决定是否包含其内容。
   */
  const contextForTokenEstimation = computed((): string => {
    const chat = currentChat.value;
    if (!chat) return '';
    const systemPrompt = chat.systemPrompt || '';

    let anchorIndex = -1;
    let anchorContent = '';

    // 倒序遍历寻找有效的历史摘要锚点
    for (let i = currentChatMessages.value.length - 1; i >= 0; i--) {
      const msg = currentChatMessages.value[i];
      const zipSub = msg.sub_messages.find(
        sm => sm.type === 'ZipHistory' && sm.status === 'completed' && sm.config?.zip_enable === true
      );

      if (zipSub) {
        anchorIndex = i;
        anchorContent = zipSub.content;
        break;
      }
    }

    let messagesToInclude: Message[] = [];

    if (anchorIndex !== -1) {
      // 方案 A: 存在历史摘要锚点
      messagesToInclude = currentChatMessages.value.slice(anchorIndex + 1);
    } else {
      // 方案 B: 无历史摘要锚点，使用原有逻辑
      const maxContext = chat.modelParameters?.max_context_messages ?? 0;
      messagesToInclude = maxContext > 0 ? currentChatMessages.value.slice(-maxContext) : currentChatMessages.value;
    }

    // 提取消息文本内容，并根据 context_participation_length (CPL) 规则进行过滤
    const history = messagesToInclude.flatMap((msg, msgIndex) => {
      // +1 是因为要算上当前正在输入、还未发送的新消息
      const totalPotentialMessages = messagesToInclude.length + 1;
      // 新旧程度排名: 1=最新, 2=次新...
      // 最终发送给LLM的消息列表是 [messagesToInclude..., newMessage]
      // 所以 msg 在该列表中的索引就是 msgIndex, 其排名为 total - index
      const messageRecencyRank = totalPotentialMessages - msgIndex;

      return msg.sub_messages
        .filter(sm => {
          // 始终从历史记录中排除非文本内容和特殊类型
          if (sm.type !== 'Normal' && sm.type !== 'File') { // 假设File类型是文本文件
            return false;
          }

          const cpl = sm.config?.context_participation_length;

          // 规则1: cpl 为 0, 则此 sub-message 不参与上下文
          if (cpl === 0) {
            return false;
          }

          // 规则2: cpl 是正整数, 检查当前 message 是否在指定的“新”范围内
          if (typeof cpl === 'number' && cpl > 0) {
            return messageRecencyRank <= cpl;
          }

          // 规则3: cpl 未定义或为其他值, 按默认逻辑(参与上下文)处理
          return true;
        })
        .map(sm => sm.content);
    }).join('\n');


    // 组装最终上下文
    const parts = [systemPrompt];
    if (anchorIndex !== -1) {
      parts.push(anchorContent);
    }
    parts.push(history);

    return parts.filter(Boolean).join('\n');
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
    const interactionStore = useChatInteractionStore();
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
      currentChatMessages.value.forEach(msg => {
        if (msg.status === 'generating') {
          interactionStore._subscribeToMessageStream(msg);
        }
      });
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
   * (内部) 在指定消息中添加或更新一个子消息。
   * 用于处理如历史压缩摘要生成等实时通知。
   * @param messageId - 父消息的ID。
   * @param subMessage - 要添加或更新的子消息。
   * @private
   */
  function _addOrUpdateSubMessage(messageId: string, subMessage: SubMessage) {
    const parentMessage = currentChatMessages.value.find(m => m.id === messageId);
    if (!parentMessage) {
      console.warn(`[chatSessionStore] 未找到ID为 ${messageId} 的父消息以添加/更新子消息。`);
      return;
    }

    // 冲突处理：如果接收到的是正式的 ZipHistory 消息（非临时ID），
    // 则先移除该消息下所有临时的 ZipHistory 占位符，防止出现重复。
    if (subMessage.type === 'ZipHistory' && !subMessage.id.startsWith('temp_zip_')) {
      const tempIndex = parentMessage.sub_messages.findIndex(
        sm => sm.type === 'ZipHistory' && sm.id.startsWith('temp_zip_')
      );
      if (tempIndex !== -1) {
        parentMessage.sub_messages.splice(tempIndex, 1);
      }
    }

    const subMessageIndex = parentMessage.sub_messages.findIndex(sm => sm.id === subMessage.id);

    if (subMessageIndex !== -1) {
      // 替换现有的子消息以确保响应性
      parentMessage.sub_messages.splice(subMessageIndex, 1, subMessage);
    } else {
      // 添加新的子消息
      parentMessage.sub_messages.push(subMessage);
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
      case 'content_update': {
        const subMsg = msgToUpdate.sub_messages.find(sm => sm.id === data.sub_message_id);
        if (subMsg) {
          subMsg.content = data.content;
        }
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
    _addOrUpdateSubMessage,
    _processStreamChunk,
  };
});
