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
import type { Chat, Message, ChatCreate, ChatUpdate, ChatReorderItem, SubMessageCreate, SubMessageUpdate } from '@/api/types';
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

  /**
   * 标志是否正在等待后端准备生成（API调用阶段），用于立即更新UI。
   * 在调用 prepareGenerate/prepareRegenerate API 和接收到SSE流的第一个数据块之间，这个状态为 true。
   */
  const isPreparingGeneration = ref(false);

  // --- Composables ---
  const { saveDraft, undo, redo, currentDraft } = useUndoRedoHistory(currentChatId);

  // --- Getters ---
  const currentChat = computed((): Chat | null => {
    if (!currentChatId.value) return null;
    const chat = chatList.value.find(c => c.id === currentChatId.value);
    return chat?.itemType === 'chat' ? chat : null;
  });

  const isGenerating = computed((): boolean =>
    isPreparingGeneration.value || // 立即反映发送意图
    currentChatMessages.value.some(msg =>
      msg.sub_messages.some(sm => sm.status === 'generating')
    )
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
        if (msg.role === 'assistant' && msg.sub_messages.some(sm => sm.status === 'generating')) {
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

    // 如果不重新生成，则这是一个简单的更新操作
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

    // 如果需要重新生成，则走包含状态管理的完整流程
    isPreparingGeneration.value = true;
    try {
      const placeholder = await updateMessageAndRegenerate(payload.messageId, { sub_messages: payload.sub_messages, resend: true });
      await selectChat(currentChatId.value, true);
      const latestMessage = currentChatMessages.value[currentChatMessages.value.length - 1];
      if (latestMessage?.id === placeholder.id && latestMessage.role === 'assistant') {
        _subscribeToMessageStream(latestMessage);
      }
    } catch (error) {
      console.error('Failed to update and resend:', error);
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    } finally {
        isPreparingGeneration.value = false;
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

    isPreparingGeneration.value = true;
    saveCurrentDraft('');

    try {
      const assistantPlaceholder = await prepareGenerate(chatId, { sub_messages });
      await selectChat(chatId, true);
      const msgToStream = currentChatMessages.value.find(m => m.id === assistantPlaceholder.id);
      if (msgToStream) {
        _subscribeToMessageStream(msgToStream);
      }
    } catch (error) {
      console.error('Failed to prepare generation:', error);
      ElMessage.error('发送失败');
      if (currentChatId.value) await selectChat(currentChatId.value, true);
    } finally {
      isPreparingGeneration.value = false;
    }
  }

  async function regenerateFrom(messageId: string) {
    if (!currentChatId.value || isGenerating.value) return;
    const chatId = currentChatId.value;

    isPreparingGeneration.value = true;

    try {
      const placeholder = await prepareRegenerate(chatId, messageId);

      const index = currentChatMessages.value.findIndex(m => m.id === messageId);
      if (index === -1) return;
      const targetMsg = currentChatMessages.value[index];
      const sliceIndex = targetMsg.role === 'assistant' ? index : index + 1;
      currentChatMessages.value.splice(sliceIndex);
      currentChatMessages.value.push(placeholder);

      _subscribeToMessageStream(placeholder);
    } catch (error) {
      console.error('Failed to prepare regeneration:', error);
       if (currentChatId.value) await selectChat(currentChatId.value, true);
    } finally {
      isPreparingGeneration.value = false;
    }
  }

  async function cancelGeneration(messageId: string) {
    _unsubscribeClientSide(messageId);
    const msg = currentChatMessages.value.find(m => m.id === messageId);
    if (msg) {
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
