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
  generateChatTitle as generateChatTitleAPI,
} from '@/api/chatService';
import { subscribeToMessageStream } from '@/services/sseService';
import { subscribeToGlobalNotifications } from '@/services/notificationService';
import type { StreamedChunk } from '@/services/sseService';
import type {
  Chat, Message, ChatCreate, ChatUpdate, ChatReorderItem, SubMessageCreate,
  SubMessageUpdate, SubMessage, GlobalNotification
} from '@/api/types';
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
  const refreshingTitleChatId = ref<string | null>(null);

  // --- Composables ---
  const { saveDraft, undo, redo, currentDraft } = useUndoRedoHistory(currentChatId);

  // --- Getters ---
  const currentChat = computed((): Chat | null => {
    if (!currentChatId.value) return null;
    const chat = chatList.value.find(c => c.id === currentChatId.value);
    return chat?.itemType === 'chat' ? chat : null;
  });

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
      // 从活动订阅中移除当前流
      activeSubscriptions.delete(assistantMessageId);
      try {
        // 从服务器获取会话的完整最新消息
        const chatWithMessages = await getChatWithMessages(chatId);

        // 使用服务器的权威数据完全替换本地消息列表, 以确保数据最终一致性
        currentChatMessages.value = chatWithMessages.messages.sort((a, b) => a.sortOrder - b.sortOrder);

        // 如果是新会话的首次交互，触发标题自动生成
        if (
          currentChat.value &&
          currentChat.value.name === '新的会话' &&
          currentChatMessages.value.length === 2 // user + assistant
        ) {
          refreshChatTitle(chatId);
        }

      } catch (err) {
        console.error("Failed to fetch final message state, performing a full refresh:", err);
        // 同步失败时，强制刷新整个会话作为后备方案
        if (currentChatId.value) {
          selectChat(currentChatId.value, true);
        }
      }
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

    if (isGenerating.value) return;

    const baseMessageIndex = currentChatMessages.value.findIndex(m => m.id === payload.messageId);
    if (baseMessageIndex === -1) {
      console.error("Cannot find message to edit and regenerate.");
      return;
    }

    try {
      const assistantPlaceholder = await updateMessageAndRegenerate(payload.messageId, {
        sub_messages: payload.sub_messages,
        resend: true
      });

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

      currentChatMessages.value.splice(baseMessageIndex + 1);
      currentChatMessages.value.push(assistantPlaceholder);

      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder, payload.messageId);
      }
    } catch (error) {
      console.error('Failed to update and resend:', error);
      ElMessage.error('操作失败，正在同步最新状态...');
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
      const assistantPlaceholder = await prepareGenerate(chatId, { sub_messages });
      currentChatMessages.value.push(assistantPlaceholder);

      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare generation:', error);
      ElMessage.error('发送失败，正在同步最新状态...');

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

    const sliceIndex = baseMessage.role === 'assistant' ? baseMessageIndex : baseMessageIndex + 1;
    currentChatMessages.value.splice(sliceIndex);

    try {
      const assistantPlaceholder = await prepareRegenerate(chatId, messageId);
      currentChatMessages.value.push(assistantPlaceholder);
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare regeneration:', error);
      ElMessage.error('重新生成失败，正在同步最新状态...');
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    }
  }

  async function cancelGeneration(messageId: string) {
    _unsubscribeClientSide(messageId);

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
      await stopGenerationAPI(messageId);

      if (currentChatId.value) {
        const chat = await getChatWithMessages(currentChatId.value);
        currentChatMessages.value = chat.messages.sort((a, b) => a.sortOrder - b.sortOrder);
      }
    } catch(error) {
      console.error(`Failed to process stop request for ${messageId}:`, error);
      ElMessage.error('停止操作失败，正在尝试同步状态...');
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

  async function refreshChatTitle(chatId: string) {
    refreshingTitleChatId.value = chatId;
    try {
      await generateChatTitleAPI(chatId);
      // The success case is handled by the SSE notification, which will reset refreshingTitleChatId.
    } catch (error) {
      console.error(`Failed to initiate title generation for chat ${chatId}:`, error);
      ElMessage.error('刷新标题失败');
      // If the request fails, reset the loading state immediately.
      if (refreshingTitleChatId.value === chatId) {
        refreshingTitleChatId.value = null;
      }
    }
  }

  function initializeNotificationListener() {
    subscribeToGlobalNotifications({
      onNotification: (notification: GlobalNotification) => {
        if (notification.type === 'chat_update') {
          const { id, name } = notification.payload;
          const chatInList = chatList.value.find(c => c.id === id);
          if (chatInList) {
            chatInList.name = name;
          }
          if (refreshingTitleChatId.value === id) {
            refreshingTitleChatId.value = null;
          }
        }
      },
      onError: (error: unknown) => {
        console.error('Global notification stream error:', error);
      }
    });
  }

  return {
    chatList, currentChatId, currentChatMessages, isChatListLoading, isChatHistoryLoading,
    refreshingTitleChatId,
    currentChat, isGenerating, currentDraft, contextForTokenEstimation,
    fetchChatList, selectChat, createNewItem, updateChatSettings, deleteItem, reorderChatItems,
    duplicateChat, editMessageAndRegenerate, updateSubMessage, deleteMessage, sendMessage,
    regenerateFrom, cancelGeneration, refreshChatTitle, initializeNotificationListener,
    saveDraft: saveCurrentDraft,
    undo: undoCurrentDraft,
    redo: redoCurrentDraft,
  };
});
