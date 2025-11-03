// frontend/mambochat/src/stores/chatStore.ts

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getChats, createChat, getChatWithMessages, deleteChat, updateChatSettings as updateChatSettingsAPI,
  reorderChats, updateMessageAndRegenerate, updateSubMessage as updateSubMessageAPI,
  deleteMessage as deleteMessageAPI,
  duplicateChat as duplicateChatAPI,
  prepareGenerate, prepareRegenerate, stopGeneration as stopGenerationAPI,
} from '@/api/chatService';
import { subscribeToMessageStream } from '@/services/sseService';
import type { StreamedChunk } from '@/services/sseService';
import type { Chat, Message, ChatCreate, ChatUpdate, ChatReorderItem, SubMessageCreate, SubMessageUpdate, SubMessage } from '@/api/types';
import { useProviderStore } from './providerStore';
import { useUndoRedoHistory } from '@/composables/useUndoRedoHistory';

export const useChatStore = defineStore('chat', () => {
  // --- State ---
  const chatList = ref<Chat[]>([]);
  const currentChatId = ref<string | null>(null);
  const currentChatMessages = ref<Message[]>([]);
  const isChatListLoading = ref(false);
  const isChatHistoryLoading = ref(false);
  const activeSubscriptions = new Map<string, AbortController>();

  // --- Composables ---
  const { saveDraft, undo, redo, currentDraft } = useUndoRedoHistory(currentChatId);

  // --- Getters ---
  const currentChat = computed((): Chat | null => {
    if (!currentChatId.value) return null;
    const chat = chatList.value.find(c => c.id === currentChatId.value);
    return chat?.itemType === 'chat' ? chat : null;
  });

  /**
   * 全局生成状态。如果任何消息的状态为 'generating'，则为 true。
   * 这是UI中禁用输入、显示停止按钮等的单一事实来源。
   */
  const isGenerating = computed((): boolean =>
    currentChatMessages.value.some(msg => msg.status === 'generating')
  );

  const contextForTokenEstimation = computed((): string => {
    const chat = currentChat.value;
    if (!chat) return '';
    const systemPrompt = chat.systemPrompt || '';
    const maxContext = chat.modelParameters?.max_context_messages ?? 0;
    const messages = maxContext > 0 ? currentChatMessages.value.slice(-maxContext) : currentChatMessages.value;
    const history = messages.map(msg => msg.sub_messages.map(sm => sm.content).join('\n')).join('\n');
    return [systemPrompt, history].filter(Boolean).join('\n');
  });

  // --- Internal Methods ---
  function _subscribeToMessageStream(assistantMessage: Message, editedUserMessageId?: string) {
    if (!currentChatId.value) return;
    const chatId = currentChatId.value;
    const assistantMessageId = assistantMessage.id;
    if (activeSubscriptions.has(assistantMessageId)) {
      _unsubscribeClientSide(assistantMessageId);
    }

    const onMessage = (data: StreamedChunk) => {
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
    };

    const finalizeMessageState = async () => {
      activeSubscriptions.delete(assistantMessageId);
      try {
        const chatWithMessages = await getChatWithMessages(chatId);

        // 同步最终的AI助手消息状态
        const finalAssistantMsg = chatWithMessages.messages.find(m => m.id === assistantMessageId);
        const localAssistantMsg = currentChatMessages.value.find(m => m.id === assistantMessageId);
        if (finalAssistantMsg && localAssistantMsg) {
          localAssistantMsg.sub_messages = finalAssistantMsg.sub_messages;
          localAssistantMsg.status = finalAssistantMsg.status;
        }

        // 如果是通过编辑用户消息触发的，则同步该用户消息的状态，以替换临时ID
        if (editedUserMessageId) {
          const finalUserMsg = chatWithMessages.messages.find(m => m.id === editedUserMessageId);
          const localUserMsg = currentChatMessages.value.find(m => m.id === editedUserMessageId);
          if (finalUserMsg && localUserMsg) {
            localUserMsg.sub_messages = finalUserMsg.sub_messages;
          }
        }
      } catch (err) { console.error("Failed to fetch final message state:", err); }
    };

    const controller = subscribeToMessageStream({
      chatId, assistantMessageId, onMessage,
      onClose: finalizeMessageState,
      onError: (err) => {
        console.error(`[ChatStore] SSE stream error for msg ${assistantMessageId}:`, err);
        finalizeMessageState();
      }
    });
    activeSubscriptions.set(assistantMessageId, controller);
  }

  function _unsubscribeClientSide(messageId: string) {
    activeSubscriptions.get(messageId)?.abort();
    activeSubscriptions.delete(messageId);
  }

  // --- Actions ---
  async function fetchChatList() {
    isChatListLoading.value = true;
    try {
      chatList.value = await getChats();
    } catch (error) { console.error('Failed to fetch chat list:', error); }
    finally { isChatListLoading.value = false; }
  }

  async function selectChat(chatId: string, forceRefresh: boolean = false) {
    if (currentChatId.value === chatId && !forceRefresh) return;
    activeSubscriptions.forEach(controller => controller.abort());
    activeSubscriptions.clear();

    const item = chatList.value.find(i => i.id === chatId);
    if (!item || item.itemType === 'folder') {
      currentChatId.value = item ? chatId : null;
      currentChatMessages.value = [];
      return;
    }

    currentChatId.value = chatId;
    isChatHistoryLoading.value = true;
    currentChatMessages.value = [];
    try {
      const chat = await getChatWithMessages(chatId);
      const chatIndex = chatList.value.findIndex(c => c.id === chatId);
      if (chatIndex !== -1) {
        Object.assign(chatList.value[chatIndex], chat);
      }
      currentChatMessages.value = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder);
      currentChatMessages.value.forEach(msg => {
        if (msg.status === 'generating') {
          _subscribeToMessageStream(msg);
        }
      });
    } catch (error) {
      console.error(`Failed to fetch messages for chat ${chatId}:`, error);
      currentChatId.value = null;
    } finally { isChatHistoryLoading.value = false; }
  }

  async function createNewItem(itemData: ChatCreate): Promise<Chat | null> {
    try {
      if (itemData.itemType === 'chat' && !itemData.aiModelId) {
        const providerStore = useProviderStore();
        itemData.aiModelId = providerStore.globalSettings.default_model_id;
      }
      const newItem = await createChat(itemData);
      chatList.value.push(newItem);
      return newItem;
    } catch (error) {
      console.error('Failed to create new item:', error);
      return null;
    }
  }

  async function updateChatSettings(itemId: string, settings: ChatUpdate) {
    try {
      const updatedChat = await updateChatSettingsAPI(itemId, settings);
      const index = chatList.value.findIndex(c => c.id === itemId);
      if (index !== -1) {
        Object.assign(chatList.value[index], updatedChat);
      }
    } catch (error) { console.error(`Failed to update settings for item ${itemId}:`, error); }
  }

  async function deleteItem(itemId: string) {
    try {
      await deleteChat(itemId);
      await fetchChatList();
      if (!chatList.value.some(c => c.id === currentChatId.value)) {
        currentChatId.value = null;
        currentChatMessages.value = [];
      }
    } catch (error) {
      console.error(`Failed to delete item ${itemId}:`, error);
      ElMessage.error('删除失败');
    }
  }

  async function reorderChatItems(updates: ChatReorderItem[]) {
    updates.forEach(update => {
      const item = chatList.value.find(c => c.id === update.id);
      if (item) Object.assign(item, { parentId: update.parentId, sortOrder: update.sortOrder });
    });
    try { await reorderChats(updates); }
    catch (error) {
      console.error('Failed to reorder items:', error);
      await fetchChatList();
    }
  }

  async function duplicateChat(itemId: string): Promise<Chat | null> {
    try {
      const newChat: Chat = await duplicateChatAPI(itemId);
      chatList.value.push(newChat);
      return newChat;
    } catch (error) {
      console.error(`Failed to duplicate chat ${itemId}:`, error);
      return null;
    }
  }

  async function editMessageAndRegenerate(payload: { messageId: string, sub_messages: SubMessageCreate[], resend?: boolean }) {
    if (!currentChatId.value) return;
    const { resend = false } = payload;

    // "仅保存" 逻辑：更新消息内容，然后全量刷新以保证状态同步
    if (!resend) {
        try {
            await updateMessageAndRegenerate(payload.messageId, { sub_messages: payload.sub_messages, resend: false });
            await selectChat(currentChatId.value, true);
        } catch (error) {
            console.error('Failed to update message:', error);
            if (currentChatId.value) await selectChat(currentChatId.value, true);
        }
        return;
    }

    // "保存并重新发送" 逻辑：使用乐观更新，避免全量刷新
    if (isGenerating.value) return;

    const baseMessageIndex = currentChatMessages.value.findIndex(m => m.id === payload.messageId);
    if (baseMessageIndex === -1) {
      console.error("Cannot find message to edit and regenerate.");
      return;
    }

    try {
      // API调用现在会返回新生成的AI助手消息占位符
      const assistantPlaceholder = await updateMessageAndRegenerate(payload.messageId, {
        sub_messages: payload.sub_messages,
        resend: true
      });

      // 乐观更新UI：
      // 1. 更新被编辑的用户消息的本地内容
      const userMessageToUpdate = currentChatMessages.value[baseMessageIndex];
      const now = new Date().toISOString();
      userMessageToUpdate.sub_messages = payload.sub_messages.map((sm, index): SubMessage => ({
        id: `temp-edited-${Date.now()}-${index}`,
        messageId: userMessageToUpdate.id,
        createdAt: now,
        content: sm.content,
        sortOrder: sm.sortOrder,
        status: 'completed',
        type: sm.type ?? 'Normal',
        config: sm.config ?? { is_collapsed: false },
      }));

      // 2. 截断被编辑消息之后的所有消息
      currentChatMessages.value.splice(baseMessageIndex + 1);

      // 3. 将API返回的AI助手占位符添加到消息列表
      currentChatMessages.value.push(assistantPlaceholder);

      // 4. 直接基于占位符开始监听SSE流，并传入被编辑的用户消息ID以供后续同步
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder, payload.messageId);
      }
    } catch (error) {
      console.error('Failed to update and resend:', error);
      ElMessage.error('操作失败，正在同步最新状态...');
      // 发生错误时，回退到全量刷新以保证数据一致性
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    }
  }

  async function updateSubMessage(payload: { subMessageId: string, data: SubMessageUpdate }) {
    for (const msg of currentChatMessages.value) {
      const subMsg = msg.sub_messages.find(sm => sm.id === payload.subMessageId);
      if (subMsg) { Object.assign(subMsg, payload.data); break; }
    }
    try { await updateSubMessageAPI(payload.subMessageId, payload.data); }
    catch (error) {
      console.error(`Failed to update sub-message ${payload.subMessageId}:`, error);
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    }
  }

  async function deleteMessage(messageId: string) {
    const index = currentChatMessages.value.findIndex(m => m.id === messageId);
    if (index === -1) return;
    const deleted = currentChatMessages.value.splice(index, 1)[0];
    try { await deleteMessageAPI(messageId); }
    catch (error) {
      console.error('Failed to delete message:', error);
      currentChatMessages.value.splice(index, 0, deleted);
    }
  }

  async function sendMessage(sub_messages: SubMessageCreate[]) {
    if (!currentChatId.value || isGenerating.value) return;
    const chatId = currentChatId.value;

    saveCurrentDraft('');

    // 乐观地在UI中创建并添加用户消息以获得即时反馈
    const now = new Date().toISOString();
    const tempUserMessageId = `temp-user-${Date.now()}`;
    const userMessageForDisplay: Message = {
      id: tempUserMessageId,
      role: 'user',
      status: 'completed',
      chatId: chatId,
      createdAt: now,
      sortOrder: (currentChatMessages.value[currentChatMessages.value.length - 1]?.sortOrder ?? 0) + 1,
      sub_messages: sub_messages.map((sm, index): SubMessage => ({
        id: `temp-sub-user-${Date.now()}-${index}`,
        messageId: tempUserMessageId,
        createdAt: now,
        content: sm.content,
        sortOrder: sm.sortOrder,
        status: 'completed',
        type: sm.type ?? 'Normal',
        config: sm.config ?? { is_collapsed: false },
      })),
    };
    currentChatMessages.value.push(userMessageForDisplay);

    try {
      // 后端保存用户消息并返回一个AI助手占位符
      const assistantPlaceholder = await prepareGenerate(chatId, { sub_messages });

      // 将真实的AI助手占位符添加到UI中，这将触发加载动画
      currentChatMessages.value.push(assistantPlaceholder);

      // 开始为新的AI助手消息订阅SSE流
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare generation:', error);
      ElMessage.error('发送失败，正在同步最新状态...');

      // 失败时，移除乐观创建的用户消息，并回退到完全刷新以确保数据一致性
      const index = currentChatMessages.value.findIndex(m => m.id === userMessageForDisplay.id);
      if (index > -1) {
        currentChatMessages.value.splice(index, 1);
      }
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    }
  }

  async function regenerateFrom(messageId: string) {
    if (!currentChatId.value || isGenerating.value) return;
    const chatId = currentChatId.value;

    const baseMessageIndex = currentChatMessages.value.findIndex(m => m.id === messageId);
    if (baseMessageIndex === -1) return;
    const baseMessage = currentChatMessages.value[baseMessageIndex];

    // 乐观地从UI中移除后续消息
    const sliceIndex = baseMessage.role === 'assistant' ? baseMessageIndex : baseMessageIndex + 1;
    currentChatMessages.value.splice(sliceIndex);

    try {
      const assistantPlaceholder = await prepareRegenerate(chatId, messageId);

      // 将新的AI助手占位符添加到UI并开始监听流
      currentChatMessages.value.push(assistantPlaceholder);
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare regeneration:', error);
      ElMessage.error('重新生成失败，正在同步最新状态...');
      // 失败时，回退到完全刷新以确保数据一致性
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    }
  }

  async function cancelGeneration(messageId: string) {
    // 1. 停止客户端的SSE流监听
    _unsubscribeClientSide(messageId);

    // 2. 乐观更新UI，立即给用户反馈
    const msg = currentChatMessages.value.find(m => m.id === messageId);
    if (msg && msg.status === 'generating') {
      msg.status = 'completed';
      msg.sub_messages.forEach(sm => {
        if (sm.status === 'generating') {
          sm.status = 'completed';
        }
      });
    }

    try {
      // 3. 通知后端停止生成任务
      await stopGenerationAPI(messageId);

      // 4. 手动同步最终状态。
      // 这是必需的，因为手动中止SSE流会阻止正常的finalizeMessageState回调，
      // 可能导致前端的临时ID（如新发送的用户消息）无法更新为真实的ID。
      if (currentChatId.value) {
        const chat = await getChatWithMessages(currentChatId.value);
        currentChatMessages.value = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder);
      }
    } catch(error) {
      console.error(`Failed to process stop request for ${messageId}:`, error);
      ElMessage.error('停止操作失败，正在尝试同步状态...');
      // 即使停止失败，也尝试刷新状态以修复潜在的不一致
      if (currentChatId.value) {
        await selectChat(currentChatId.value, true);
      }
    }
  }

  function saveCurrentDraft(content: string) {
    if (currentChatId.value) {
        saveDraft(currentChatId.value, content);
    }
  }

  function undoCurrentDraft() {
    if (currentChatId.value) {
        undo(currentChatId.value);
    }
  }

  function redoCurrentDraft() {
    if (currentChatId.value) {
        redo(currentChatId.value);
    }
  }

  return {
    chatList, currentChatId, currentChatMessages, isChatListLoading, isChatHistoryLoading,
    currentChat, isGenerating, currentDraft, contextForTokenEstimation,
    fetchChatList, selectChat, createNewItem, updateChatSettings, deleteItem, reorderChatItems,
    duplicateChat, editMessageAndRegenerate, updateSubMessage, deleteMessage, sendMessage,
    regenerateFrom, cancelGeneration,
    saveDraft: saveCurrentDraft,
    undo: undoCurrentDraft,
    redo: redoCurrentDraft,
  };
});
