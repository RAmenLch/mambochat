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
  function _subscribeToMessageStream(assistantMessage: Message) {
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
        const finalMsg = await getChatWithMessages(chatId).then(res => res.messages.find(m => m.id === assistantMessageId));
        const localMsg = currentChatMessages.value.find(m => m.id === assistantMessageId);
        if (finalMsg && localMsg) {
          localMsg.sub_messages = finalMsg.sub_messages;
          // 同步最终的聚合状态
          localMsg.status = finalMsg.status;
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

    try {
      await updateMessageAndRegenerate(payload.messageId, { sub_messages: payload.sub_messages, resend: true });
      await selectChat(currentChatId.value, true);
      const latestMessage = currentChatMessages.value[currentChatMessages.value.length - 1];
      if (latestMessage?.role === 'assistant' && latestMessage.status === 'generating') {
        _subscribeToMessageStream(latestMessage);
      }
    } catch (error) {
      console.error('Failed to update and resend:', error);
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

    // Optimistically create and add the user's message to the UI for instant feedback.
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
      // The backend saves the user message and returns an assistant placeholder.
      const assistantPlaceholder = await prepareGenerate(chatId, { sub_messages });

      // Add the real assistant placeholder to the UI, which will trigger the loading bubble.
      currentChatMessages.value.push(assistantPlaceholder);

      // Start subscribing to the stream for the new assistant message.
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare generation:', error);
      ElMessage.error('发送失败，正在同步最新状态...');

      // On failure, remove the optimistic user message and fall back to a full refresh
      // to ensure data consistency.
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

    // Optimistically remove subsequent messages from the UI.
    const sliceIndex = baseMessage.role === 'assistant' ? baseMessageIndex : baseMessageIndex + 1;
    currentChatMessages.value.splice(sliceIndex);

    try {
      const assistantPlaceholder = await prepareRegenerate(chatId, messageId);

      // Add the new assistant placeholder to the UI and start the stream.
      currentChatMessages.value.push(assistantPlaceholder);
      if (assistantPlaceholder.status === 'generating') {
        _subscribeToMessageStream(assistantPlaceholder);
      }
    } catch (error) {
      console.error('Failed to prepare regeneration:', error);
      ElMessage.error('重新生成失败，正在同步最新状态...');
      // On failure, fall back to a full refresh to ensure data consistency.
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    }
  }

  async function cancelGeneration(messageId: string) {
    _unsubscribeClientSide(messageId);
    const msg = currentChatMessages.value.find(m => m.id === messageId);
    if (msg && msg.status === 'generating') {
      // Optimistically update the local state for a responsive UI
      msg.status = 'completed';
      msg.sub_messages.forEach(sm => {
        if (sm.status === 'generating') {
          sm.status = 'completed';
        }
      });
    }
    try { await stopGenerationAPI(messageId); }
    catch(error) { console.error(`Failed to send stop request for ${messageId}:`, error); }
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
