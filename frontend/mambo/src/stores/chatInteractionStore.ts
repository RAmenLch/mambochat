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
  submitToolReview as submitToolReviewAPI,
  submitAskUserAnswer as submitAskUserAnswerAPI,
  activateMessageBranch,
  retryFailedGeneration as retryFailedGenerationAPI,
} from '@/api/chatService'
import { subscribeToMessageStream } from '@/services/sseService';
import { useChatSessionStore } from './chatSessionStore';
import { useChatListStore } from './chatListStore';
import type {
  Message,
  SubMessage,
  SubMessageCreate,
  SubMessageUpdate,
  MessageStatus,
  ReviewToolRequest,
  AskUserAnswerRequest,
} from '@/api/types'

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
        const chatWithMessages = await getChatWithMessages(chatId);
        sessionStore.currentChatMessages = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);

        const finalMessage = sessionStore.currentChatMessages.find(m => m.id === assistantMessageId);
        if (finalMessage) {
          const hasPendingReview = finalMessage.sub_messages.some(
            sm => (sm.type === 'ReviewTool' || sm.type === 'AskUser') && sm.status === 'pending_review'
          );
          if (!hasPendingReview) {
            await batchUpdateSubMessagesMinimalState(assistantMessageId, true);
          }
        }
        if (
          sessionStore.currentChat &&
            (
                sessionStore.currentChat.name === '新的会话' ||
                sessionStore.currentChat.name === 'New Chat'
            )
            &&
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
    sessionStore._spliceMessages(sliceIndex);

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

    if (payload.resend && sessionStore.isGenerating) return;

    try {
      const response = await updateMessageAndRegenerate(payload.messageId, {
        sub_messages: payload.sub_messages,
        resend: payload.resend,
      });
      const { user_message, assistant_message } = response;

      const messageIndex = sessionStore.currentChatMessages.findIndex(m => m.id === payload.messageId);
      if (messageIndex !== -1) {
        sessionStore.currentChatMessages.splice(messageIndex, 1, user_message);
      } else {
        await sessionStore.selectChat(chatId, true);
        return;
      }

      if (assistant_message) {
        sessionStore._spliceMessages(messageIndex + 1, [assistant_message]);
        if (assistant_message.status === 'generating') {
          _subscribeToMessageStream(assistant_message);
        }
      }
    } catch (error) {
      console.error('Failed to update and/or resend message:', error);
      if (chatId) await sessionStore.selectChat(chatId, true);
    }
  }


  /**
   * 更新单个子消息的元数据（如折叠状态）。
   * @param payload - 包含子消息ID和要更新的数据。
   */
  async function updateSubMessage(payload: { subMessageId: string, data: SubMessageUpdate }) {
    for (const msg of sessionStore.currentChatMessages) {
      const subMsg = msg.sub_messages.find(sm => sm.id === payload.subMessageId);
      if (subMsg) {
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
    const backup = sessionStore._removeMessage(messageId);
    if (!backup) return;

    try {
      await deleteMessageAPI(messageId);
      if (sessionStore.currentChatId) {
        await sessionStore.selectChat(sessionStore.currentChatId, true);
      }
    } catch (error) {
      console.error('Failed to delete message:', error);
      sessionStore.currentChatMessages.push(backup);
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

    const msg = sessionStore.currentChatMessages.find(m => m.id === messageId);
    if (msg && msg.status === 'generating') {
      msg.status = 'completed';
      msg.sub_messages.forEach(sm => {
        if (sm.status === 'generating') sm.status = 'completed';
      });
    }
     try {
      await stopGenerationAPI(messageId);
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
      backupZip = JSON.parse(JSON.stringify(existingZip));

      const updatedZip = { ...existingZip, status: 'generating' as MessageStatus };
      sessionStore._addOrUpdateSubMessage(messageId, updatedZip);
    } else {
      tempId = `temp_zip_${Date.now()}`;
      const optimisticSubMessage: SubMessage = {
        id: tempId,
        content: '',
        createdAt: new Date().toISOString(),
        messageId: messageId,
        sortOrder: 999,
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

      if (existingZip && backupZip) {
        sessionStore._addOrUpdateSubMessage(messageId, backupZip);
      } else if (tempId) {
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
    for (const msg of sessionStore.currentChatMessages) {
      const subMsg = msg.sub_messages.find(sm => sm.id === subMessageId);
      if (subMsg) {
        if (data.content) {
          subMsg.content = data.content;
        }
        if (data.config) {
          subMsg.config = { ...subMsg.config, ...data.config };
        }
        break;
      }
    }

    try {
      await updateSubMessageAPI(subMessageId, data);
    } catch (error) {
      console.error(`Failed to update zip history sub-message ${subMessageId}:`, error);
      if (sessionStore.currentChatId) {
        await sessionStore.selectChat(sessionStore.currentChatId, true);
      }
    }
  }

  async function submitToolReview(
    messageId: string,
    subMessageId: string,
    decision: ReviewToolRequest['decision'],
  ) {
    try {
      const updatedMessage = await submitToolReviewAPI(messageId, {
        sub_message_id: subMessageId,
        decision,
      })

      const index = sessionStore.currentChatMessages.findIndex((m) => m.id === messageId)
      if (index !== -1) {
        sessionStore.currentChatMessages.splice(index, 1, updatedMessage)

        if (updatedMessage.status === 'generating') {
          _subscribeToMessageStream(updatedMessage)
        }
        else if (updatedMessage.status === 'completed') {
          const hasPendingReview = updatedMessage.sub_messages.some(
            sm => (sm.type === 'ReviewTool' || sm.type === 'AskUser') && sm.status === 'pending_review'
          );
          if (!hasPendingReview) {
            await batchUpdateSubMessagesMinimalState(messageId, true);
          }
        }
      }
    } catch (error) {
      console.error('Failed to submit tool review:', error)
      if (sessionStore.currentChatId) {
        await sessionStore.selectChat(sessionStore.currentChatId, true)
      }
      throw error
    }
  }

  async function submitAskUserAnswer(
    messageId: string,
    subMessageId: string,
    answers: string[],
    askStatus: string = 'answered',
  ) {
    try {
      const updatedMessage = await submitAskUserAnswerAPI(messageId, {
        sub_message_id: subMessageId,
        answers,
        ask_status: askStatus,
      })

      const index = sessionStore.currentChatMessages.findIndex((m) => m.id === messageId)
      if (index !== -1) {
        sessionStore.currentChatMessages.splice(index, 1, updatedMessage)

        if (updatedMessage.status === 'generating') {
          _subscribeToMessageStream(updatedMessage)
        }
        else if (updatedMessage.status === 'completed') {
          const hasPendingReview = updatedMessage.sub_messages.some(
            sm => (sm.type === 'ReviewTool' || sm.type === 'AskUser') && sm.status === 'pending_review'
          );
          if (!hasPendingReview) {
            await batchUpdateSubMessagesMinimalState(messageId, true);
          }
        }
      }
    } catch (error) {
      console.error('Failed to submit ask_user answer:', error)
      if (sessionStore.currentChatId) {
        await sessionStore.selectChat(sessionStore.currentChatId, true)
      }
      throw error
    }
  }

  async function batchUpdateSubMessagesMinimalState(messageId: string, isMinimal: boolean) {
    const message = sessionStore.currentChatMessages.find(m => m.id === messageId);
    if (!message) return;

    const reasoningSubMessages = message.sub_messages.filter(sm => sm.type === 'Reasoning');
    if (reasoningSubMessages.length === 0) return;

    let hasChanges = false;

    reasoningSubMessages.forEach(sm => {
      if (sm.config.is_minimal !== isMinimal) {
        sm.config = { ...sm.config, is_minimal: isMinimal };
        hasChanges = true;
      }
    });

    if (!hasChanges) return;

    try {
      const updatePromises = reasoningSubMessages.map(sm =>
        updateSubMessageAPI(sm.id, { config: { ...sm.config, is_minimal: isMinimal } })
      );
      await Promise.all(updatePromises);
    } catch (error) {
      console.error(`Failed to batch update minimal state for message ${messageId}:`, error);
      if (sessionStore.currentChatId) {
        await sessionStore.selectChat(sessionStore.currentChatId, true);
      }
    }
  }

  /**
   * 激活指定消息分支
   * @param messageId - 目标消息ID
   */
  async function activateBranch(messageId: string) {
    const chatId = sessionStore.currentChatId;
    if (!chatId || sessionStore.isGenerating) return;

    try {
      const messages = await activateMessageBranch(chatId, messageId);
      sessionStore.currentChatMessages = messages.sort((a, b) => a.sortOrder - b.sortOrder);
    } catch (error) {
      console.error(`Failed to activate branch for message ${messageId}:`, error);
      if (chatId) await sessionStore.selectChat(chatId, true);
    }
  }

  /**
   * 重试失败的生成任务（从错误中恢复）
   * @param messageId - 失败的 assistant 消息ID
   */
  async function retryFailedGeneration(messageId: string) {
    const chatId = sessionStore.currentChatId;
    if (!chatId || sessionStore.isGenerating) return;

    const msgIndex = sessionStore.currentChatMessages.findIndex(m => m.id === messageId);
    if (msgIndex === -1) return;

    try {
      const updatedMessage = await retryFailedGenerationAPI(messageId);
      sessionStore.currentChatMessages.splice(msgIndex, 1, updatedMessage);

      if (updatedMessage.status === 'generating') {
        _subscribeToMessageStream(updatedMessage);
      }
    } catch (error) {
      console.error(`Failed to retry generation for message ${messageId}:`, error);
      if (chatId) await sessionStore.selectChat(chatId, true);
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
    _subscribeToMessageStream,
    batchUpdateSubMessagesMinimalState,
    submitToolReview,
    submitAskUserAnswer,
    activateBranch,
    retryFailedGeneration,
  }
});
