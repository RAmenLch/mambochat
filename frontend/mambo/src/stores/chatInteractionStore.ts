// frontend/mambo/src/stores/chatInteractionStore.ts

import { defineStore } from 'pinia';
import {
  updateMessageAndRegenerate,
  updateSubMessage as updateSubMessageAPI,
  deleteMessage as deleteMessageAPI,
  prepareGenerate,
  prepareRegenerate,
  stopGeneration as stopGenerationAPI,
  getChatWithMessages,
  initiateHistoryCompression as initiateHistoryCompressionAPI,
} from '@/api/chatService';
import { subscribeToMessageStream } from '@/services/sseService';
import { useChatSessionStore } from './chatSessionStore';
import { useChatListStore } from './chatListStore';
import type { Message, SubMessage, SubMessageCreate, SubMessageUpdate, MessageStatus } from '@/api/types';

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
   * @param attachedResourceIds - 附加的SubMessage模板资源ID数组。
   */
  async function sendMessage(sub_messages: SubMessageCreate[], attachedResourceIds?: string[]) {
    const chatId = sessionStore.currentChatId;
    if (!chatId || sessionStore.isGenerating) return;

    try {
      const { user_message, assistant_message } = await prepareGenerate(chatId, {
        sub_messages,
        attachedSubmessageResourceIds: attachedResourceIds,
      });
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

    // 如果是重新生成，则检查是否已有其他任务在运行
    if (payload.resend && sessionStore.isGenerating) return;

    try {
      // 调用更新后的API, 它会返回更新后的用户消息和可能的助手消息占位符
      const response = await updateMessageAndRegenerate(payload.messageId, {
        sub_messages: payload.sub_messages,
        resend: payload.resend,
      });
      const { user_message, assistant_message } = response;

      // 使用API返回的权威数据更新前端状态
      const messageIndex = sessionStore.currentChatMessages.findIndex(m => m.id === user_message.id);
      if (messageIndex !== -1) {
        // 直接替换整个消息对象，确保所有字段（包括sub_messages）都是最新的
        sessionStore.currentChatMessages.splice(messageIndex, 1, user_message);
      } else {
        // 如果找不到，作为后备方案，刷新整个会话
        await sessionStore.selectChat(chatId, true);
        return;
      }

      // 如果有助手消息占位符 (即 resend: true)
      if (assistant_message) {
        // 从用户消息之后移除所有旧消息, 并插入新的助手消息占位符
        sessionStore._spliceMessages(messageIndex + 1, [assistant_message]);
        if (assistant_message.status === 'generating') {
          _subscribeToMessageStream(assistant_message);
        }
      }
    } catch (error) {
      console.error('Failed to update and/or resend message:', error);
      // 发生任何错误时，都强制刷新会话以保证数据一致性
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
        // 合并config对象而不是直接替换
        if (payload.data.config) {
          subMsg.config = { ...subMsg.config, ...payload.data.config };
        }
        if (payload.data.content) {
          subMsg.content = payload.data.content;
        }
        if (payload.data.status) {
          subMsg.status = payload.data.status;
        }
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
    const parentMessage = sessionStore.currentChatMessages.find(m => m.id === messageId);
    if (!parentMessage) return;

    const existingZip = parentMessage.sub_messages.find(sm => sm.type === 'ZipHistory');
    let backupZip: SubMessage | null = null;
    let tempId: string | null = null;

    if (existingZip) {
      // 1. 如果已存在，备份并乐观更新状态为 generating
      // 使用 JSON.parse/stringify 进行深拷贝备份
      backupZip = JSON.parse(JSON.stringify(existingZip));

      const updatedZip = { ...existingZip, status: 'generating' as MessageStatus };
      sessionStore._addOrUpdateSubMessage(messageId, updatedZip);
    } else {
      // 2. 如果不存在，创建临时占位符
      tempId = `temp_zip_${Date.now()}`;
      const optimisticSubMessage: SubMessage = {
        id: tempId,
        content: '',
        createdAt: new Date().toISOString(),
        messageId: messageId,
        sortOrder: 999, // 临时赋予一个较大的排序值
        type: 'ZipHistory',
        config: {
          is_collapsed: false,
          zip_enable: false
        },
        status: 'generating'
      };
      sessionStore._addOrUpdateSubMessage(messageId, optimisticSubMessage);
    }

    try {
      await initiateHistoryCompressionAPI(messageId);
    } catch (error) {
      console.error(`Failed to initiate history compression for message ${messageId}:`, error);

      // 回滚逻辑
      if (existingZip && backupZip) {
        // 恢复原有的子消息状态
        sessionStore._addOrUpdateSubMessage(messageId, backupZip);
      } else if (tempId) {
        // 移除临时创建的消息
        const currentParent = sessionStore.currentChatMessages.find(m => m.id === messageId);
        if (currentParent) {
          const index = currentParent.sub_messages.findIndex(sm => sm.id === tempId);
          if (index !== -1) {
            currentParent.sub_messages.splice(index, 1);
          }
        }
      }
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
