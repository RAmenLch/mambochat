// frontend/mambo/src/stores/chatListStore.ts

import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getChats, createChat, deleteChat, updateChatSettings as updateChatSettingsAPI,
  reorderChats, duplicateChat as duplicateChatAPI, generateChatTitle as generateChatTitleAPI
} from '@/api/chatService';
import { subscribeToGlobalNotifications } from '@/services/notificationService';
import type { Chat, ChatCreate, ChatUpdate, ChatReorderItem, GlobalNotification } from '@/api/types';
import { useChatSessionStore } from './chatSessionStore';

/**
 * 管理会话列表（包括文件夹和聊天）的全局状态。
 * 这是应用中所有会话元数据的唯一事实来源。
 */
export const useChatListStore = defineStore('chatList', () => {
  // --- State ---
  const chatList = ref<Chat[]>([]);
  const isChatListLoading = ref(false);
  const refreshingTitleChatId = ref<string | null>(null);

  // --- Actions ---

  /**
   * 从服务器获取完整的会话列表。
   */
  async function fetchChatList() {
    isChatListLoading.value = true;
    try {
      chatList.value = await getChats();
    } catch (error) {
      console.error('Failed to fetch chat list:', error);
      ElMessage.error('获取会话列表失败');
    } finally {
      isChatListLoading.value = false;
    }
  }

  /**
   * 创建一个新的会话或文件夹。
   * @param itemData - 创建项所需的数据。
   * @returns 创建成功后的新项，或在失败时返回null。
   */
  async function createNewItem(itemData: ChatCreate): Promise<Chat | null> {
    try {
      const newItem = await createChat(itemData);
      chatList.value.push(newItem);
      return newItem;
    } catch (error) {
      console.error('Failed to create new item:', error);
      ElMessage.error('创建失败');
      return null;
    }
  }

  /**
   * 更新会话或文件夹的设置（例如名称）。
   * @param itemId - 要更新的项的ID。
   * @param settings - 要更新的设置。
   */
  async function updateChatSettings(itemId: string, settings: ChatUpdate) {
    try {
      const updatedChat = await updateChatSettingsAPI(itemId, settings);
      const index = chatList.value.findIndex(c => c.id === itemId);
      if (index !== -1) {
        // 使用Object.assign确保响应性
        Object.assign(chatList.value[index], updatedChat);
      }
    } catch (error) {
      console.error(`Failed to update settings for item ${itemId}:`, error);
      ElMessage.error('更新设置失败');
    }
  }

  /**
   * 删除一个会话或文件夹。
   * 如果删除的是当前打开的会话，则会清空会话状态。
   * @param itemId - 要删除的项的ID。
   */
  async function deleteItem(itemId: string) {
    try {
      await deleteChat(itemId);
      // 重新获取整个列表以确保数据一致性，特别是子项也被删除的情况
      await fetchChatList();

      const sessionStore = useChatSessionStore();
      if (sessionStore.currentChatId === itemId || !chatList.value.some(c => c.id === sessionStore.currentChatId)) {
        sessionStore.clearSession();
      }
    } catch (error) {
      console.error(`Failed to delete item ${itemId}:`, error);
      ElMessage.error('删除失败');
    }
  }

  /**
   * 对会话列表项进行重新排序（例如拖拽后）。
   * @param updates - 包含排序更新信息的数组。
   */
  async function reorderChatItems(updates: ChatReorderItem[]) {
    // 乐观更新UI
    updates.forEach(update => {
      const item = chatList.value.find(c => c.id === update.id);
      if (item) {
        Object.assign(item, { parentId: update.parentId, sortOrder: update.sortOrder });
      }
    });
    // 重新排序以反映UI
    chatList.value.sort((a, b) => a.sortOrder - b.sortOrder);

    try {
      await reorderChats(updates);
    } catch (error) {
      console.error('Failed to reorder items:', error);
      ElMessage.error('排序失败，正在恢复...');
      // 如果API调用失败，则重新获取列表以回滚更改
      await fetchChatList();
    }
  }

  /**
   * 复制一个现有的会话。
   * @param itemId - 要复制的会话ID。
   * @returns 复制成功后的新会话，或在失败时返回null。
   */
  async function duplicateChat(itemId: string): Promise<Chat | null> {
    try {
      const newChat: Chat = await duplicateChatAPI(itemId);
      chatList.value.push(newChat);
      return newChat;
    } catch (error) {
      console.error(`Failed to duplicate chat ${itemId}:`, error);
      ElMessage.error('复制失败');
      return null;
    }
  }

  /**
   * 请求后端为指定会话自动生成标题。
   * @param chatId - 目标会话的ID。
   */
  async function refreshChatTitle(chatId: string) {
    refreshingTitleChatId.value = chatId;
    try {
      await generateChatTitleAPI(chatId);
      // 成功后，标题的更新将通过SSE通知来处理，届时会清除refreshingTitleChatId
    } catch (error) {
      console.error(`Failed to initiate title generation for chat ${chatId}:`, error);
      ElMessage.error('刷新标题失败');
      // 如果请求本身失败，立即清除加载状态
      if (refreshingTitleChatId.value === chatId) {
        refreshingTitleChatId.value = null;
      }
    }
  }

  /**
   * 初始化并监听来自服务器的全局通知（SSE）。
   * 主要用于实时更新会话标题等。
   */
  function initializeNotificationListener() {
    subscribeToGlobalNotifications({
      onNotification: (notification: GlobalNotification) => {
        if (notification.type === 'chat_update') {
          const { id, name } = notification.payload;
          const chatInList = chatList.value.find(c => c.id === id);
          if (chatInList) {
            chatInList.name = name;
          }
          // 无论是否在列表中找到，都清除加载状态
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
    // State
    chatList,
    isChatListLoading,
    refreshingTitleChatId,

    // Actions
    fetchChatList,
    createNewItem,
    updateChatSettings,
    deleteItem,
    reorderChatItems,
    duplicateChat,
    refreshChatTitle,
    initializeNotificationListener,
  };
});
