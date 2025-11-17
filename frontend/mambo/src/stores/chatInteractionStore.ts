// frontend/mambo/src/stores/chatInteractionStore.ts

import { defineStore } from 'pinia';
import {
  updateMessageAndRegenerate, updateSubMessage as updateSubMessageAPI,
  deleteMessage as deleteMessageAPI, prepareGenerate, prepareRegenerate,
  stopGeneration as stopGenerationAPI, getChatWithMessages,
  initiateHistoryCompression as initiateHistoryCompressionAPI,
} from '@/api/chatService';
import { subscribeToMessageStream } from '@/services/sseService';
import { useChatSessionStore } from './chatSessionStore';
import { useChatListStore } from './chatListStore';
import type { Message, SubMessageCreate, SubMessageUpdate, SubMessage } from '@/api/types';

/**
 * 处理所有与当前会话的交互动作。
 * 这是一个业务逻辑协调器，负责调用API、处理响应，并委托 chatSessionStore 更新状态。
 */
export const useChatInteractionStore = defineStore('chatInteraction', () => {
  const sessionStore = useChatSessionStore();
  const listStore = useChatListStore();

  /**
   * 订阅指定助手消息的SSE流。
   * @param assistantMessage - 正在生成内容的助手消息对象。
   */
  function _subscribeToMessageStream(assistantMessage: Message) {
    const chatId = sessionStore.currentChatId;
    if (!chatId) return;

    const assistantMessageId = assistantMessage.id;
    if (sessionStore.activeSubscriptions.has(assistantMessageId)) {
      sessionStore.activeSubscriptions.get(assistantMessageId)?.abort();
    }

    const finalize = async () => {
      sessionStore.activeSubscriptions.delete(assistantMessageId);
      try {
        // 流结束后，从服务器获取最终权威状态
        const chatWithMessages = await getChatWithMessages(chatId);
        sessionStore.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);

        // 检查是否需要触发自动标题生成
        if (
          sessionStore.currentChat &&
          sessionStore.currentChat.name === '新的会话' &&
          sessionStore.currentChatMessages.length === 2
        ) {
          listStore.refreshChatTitle(chatId);
        }
      } catch (err) {
        console.error("Failed to fetch final message state, performing a full refresh:", err);
        if (sessionStore.currentChatId) {
          sessionStore.selectChat(sessionStore.currentChatId, true);
        }
      }
    };

    const controller = subscribeToMessageStream({
      chatId,
      assistantMessageId,
      onMessage: (data) => sessionStore._processStreamChunk(assistantMessageId, data),
      onClose: finalize,
      onError: (err) => {
        console.error(`SSE stream error for msg ${assistantMessageId}:`, err);
        finalize();
      }
    });
    sessionStore.activeSubscriptions.set(assistantMessageId, controller);
  }

  /**
   * 发送新消息。
   * @param sub_messages - 用户创建的子消息数组。
   */
  async function sendMessage(sub_messages: SubMessageCreate[]) {
    const chatId = sessionStore.currentChatId;
    if (!chatId || sessionStore.isGenerating) return;

    try {
      const { user_message, assistant_message } = await prepareGenerate(chatId, { sub_messages });
      sessionStore._addMessage(user_message);
      sessionStore._addMessage(assistant_message);

      if (assistant_message.status === 'generating') {
        _subscribeToMessageStream(assistant_message);
      }
    } catch (error) {
      console.error('Failed to prepare generation:', error);
      // If the API call fails, refresh the chat to ensure a consistent state.
      if (sessionStore.currentChatId) await sessionStore.selectChat(sessionStore.currentChatId, true);
    }
  }

  /**
   * 从指定消息开始重新生成对话。
   * @param messageId - 作为重新生成起点的消息ID。
   */
  async function regenerateFrom(messageId: string) {
    const chatId = sessionStore.currentChatId;
    if (!chatId || sessionStore.isGenerating) return;

    const baseMessageIndex = sessionStore.currentChatMessages.findIndex(m => m.id === messageId);
    if (baseMessageIndex === -1) return;
    const baseMessage = sessionStore.currentChatMessages[baseMessageIndex];

    const sliceIndex = baseMessage.role === 'assistant' ? baseMessageIndex : baseMessageIndex + 1;
    sessionStore._spliceMessages(sliceIndex); // 乐观地移除后续消息

    try {
      const assistantPlaceholder = await prepareRegenerate(chatId, messageId);
      sessionStore._addMessage(assistantPlaceholder);
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare regeneration:', error);
      if (sessionStore.currentChatId) await sessionStore.selectChat(sessionStore.currentChatId, true);
    }
  }

  /**
   * 编辑消息内容并可选择重新生成。
   * @param payload - 包含消息ID、新的子消息和是否重新发送的标志。
   */
  async function editMessageAndRegenerate(payload: { messageId: string, sub_messages: SubMessageCreate[], resend?: boolean }) {
    const chatId = sessionStore.currentChatId;
    if (!chatId) return;

    // Case 1: 仅更新消息内容，不重新生成
    if (!payload.resend) {
      try {
        await updateMessageAndRegenerate(payload.messageId, { sub_messages: payload.sub_messages, resend: false });
        await sessionStore.selectChat(chatId, true); // 强制刷新以获取最新内容
      } catch (error) {
        console.error('Failed to update message:', error);
        if (chatId) await sessionStore.selectChat(chatId, true);
      }
      return;
    }

    // Case 2: 更新内容并重新生成
    if (sessionStore.isGenerating) return;
    const baseMessageIndex = sessionStore.currentChatMessages.findIndex(m => m.id === payload.messageId);
    if (baseMessageIndex === -1) return;

    try {
      const assistantPlaceholder = await updateMessageAndRegenerate(payload.messageId, { sub_messages: payload.sub_messages, resend: true });

      // 乐观更新UI
      const userMessage = sessionStore.currentChatMessages[baseMessageIndex];
      sessionStore._updateSubMessages(userMessage.id, payload.sub_messages as SubMessage[]);
      sessionStore._spliceMessages(baseMessageIndex + 1, [assistantPlaceholder]);

      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to update and resend:', error);
      if (chatId) await sessionStore.selectChat(chatId, true);
    }
  }

  /**
   * 更新单个子消息的元数据（如折叠状态）。
   * @param payload - 包含子消息ID和要更新的数据。
   */
  async function updateSubMessage(payload: { subMessageId: string, data: SubMessageUpdate }) {
    // 乐观更新UI
    for (const msg of sessionStore.currentChatMessages) {
      const subMsg = msg.sub_messages.find(sm => sm.id === payload.subMessageId);
      if (subMsg) {
        Object.assign(subMsg, payload.data);
        break;
      }
    }
    try {
      await updateSubMessageAPI(payload.subMessageId, payload.data);
    } catch (error) {
      console.error(`Failed to update sub-message ${payload.subMessageId}:`, error);
      if (sessionStore.currentChatId) await sessionStore.selectChat(sessionStore.currentChatId, true);
    }
  }

  /**
   * 删除一条消息及其所有子消息。
   * @param messageId - 要删除的消息ID。
   */
  async function deleteMessage(messageId: string) {
    const backup = sessionStore._removeMessage(messageId); // 乐观更新UI
    if (!backup) return;

    try {
      await deleteMessageAPI(messageId);
    } catch (error) {
      console.error('Failed to delete message:', error);
      sessionStore.currentChatMessages.push(backup); // 回滚
      sessionStore.currentChatMessages.sort((a,b) => a.sortOrder - b.sortOrder);
    }
  }

  /**
   * 取消正在进行的消息生成。
   * @param messageId - 正在生成的消息ID。
   */
  async function cancelGeneration(messageId: string) {
    sessionStore.activeSubscriptions.get(messageId)?.abort();
    sessionStore.activeSubscriptions.delete(messageId);

    // 乐观更新UI状态
    const msg = sessionStore.currentChatMessages.find(m => m.id === messageId);
    if (msg && msg.status === 'generating') {
      msg.status = 'completed';
      msg.sub_messages.forEach(sm => {
        if (sm.status === 'generating') sm.status = 'completed';
      });
    }
     try {
      await stopGenerationAPI(messageId);
      // 停止后，强制刷新以获取最终一致状态
    } catch (error) {
      console.error(`Failed to process stop request for ${messageId}:`, error);
    }
  }

  /**
   * 发起一个后台对话历史压缩任务。
   * @param messageId - 作为压缩起点的助手消息ID。
   */
  async function initiateHistoryCompression(messageId: string) {
    try {
      await initiateHistoryCompressionAPI(messageId);
    } catch (error) {
      console.error(`Failed to initiate history compression for message ${messageId}:`, error);
      // 错误消息将由全局API拦截器显示
    }
  }

  /**
   * 更新历史压缩子消息（内容或启用状态）。
   * @param subMessageId - 'ZipHistory' 类型子消息的ID。
   * @param data - 要更新的数据。
   */
  async function updateZipHistorySubMessage(subMessageId: string, data: SubMessageUpdate) {
    // 乐观更新UI
    for (const msg of sessionStore.currentChatMessages) {
      const subMsg = msg.sub_messages.find(sm => sm.id === subMessageId);
      if (subMsg) {
        if (data.content) {
          subMsg.content = data.content;
        }
        if (data.config) {
          // 合并config对象，而不是直接替换
          subMsg.config = { ...subMsg.config, ...data.config };
        }
        break;
      }
    }

    try {
      await updateSubMessageAPI(subMessageId, data);
    } catch (error) {
      console.error(`Failed to update zip history sub-message ${subMessageId}:`, error);
      // 发生错误时，强制刷新整个会话以确保数据一致性
      if (sessionStore.currentChatId) {
        await sessionStore.selectChat(sessionStore.currentChatId, true);
      }
    }
  }

  return {
    sendMessage,
    regenerateFrom,
    editMessageAndRegenerate,
    updateSubMessage,
    deleteMessage,
    cancelGeneration,
    initiateHistoryCompression,
    updateZipHistorySubMessage,
    _subscribeToMessageStream
  };
});
