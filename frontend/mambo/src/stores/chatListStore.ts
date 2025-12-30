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
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';

/**
 * 管理会话列表（包括文件夹和聊天）的全局状态。
 * 这是应用中所有会话元数据的唯一事实来源。
 */
export const useChatListStore = defineStore('chatList', () => {
  // --- State ---
  const chatList = ref<Chat[]>([]);
  const refreshingTitleChatId = ref<string | null>(null);

  // --- Actions ---

  // 使用通用 Composable 封装树形数据操作
  const {
    isLoading: isChatListLoading,
    fetchItems: fetchChatList,
    createItem: createNewItem,
    updateItem: updateChatSettings,
    deleteItem,
    reorderItems: reorderChatItems,
    duplicateItem: duplicateChat
  } = useTreeStoreActions<Chat, ChatCreate, ChatUpdate>({
    items: chatList,
    api: {
      fetchAll: getChats,
      create: createChat,
      update: updateChatSettingsAPI,
      remove: async (id: string): Promise<void> => {
        await deleteChat(id);
      },

      reorder: async (updates: ChatReorderItem[]): Promise<void> => {
        await reorderChats(updates);
      },
      duplicate: duplicateChatAPI,
    },
    onDeleteItem: (deletedItem: Chat) => {
      const sessionStore = useChatSessionStore();
      // 如果删除的是当前打开的会话，则清空会话状态。
      if (sessionStore.currentChatId === deletedItem.id) {
        sessionStore.clearSession();
      }
    },
  });

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
      // 如果请求本身失败，立即清除加载状态
      if (refreshingTitleChatId.value === chatId) {
        refreshingTitleChatId.value = null;
      }
    }
  }

  /**
   * 初始化并监听来自服务器的全局通知（SSE）。
   * 用于实时更新会话标题、接收历史压缩结果以及处理异步任务错误。
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
        } else if (notification.type === 'zip_history_update') {
          const sessionStore = useChatSessionStore();
          // 仅当通知与当前活动会话相关时，才更新会话状态
          if (sessionStore.currentChatId === notification.payload.chat_id) {
            sessionStore._addOrUpdateSubMessage(
              notification.payload.message_id,
              notification.payload.sub_message
            );
          }
        } else if (notification.type === 'notification' && notification.category === 'title_generation_error') {
          // 处理标题生成任务异常
          const errorChatId = notification.context.chat_id;

          // 如果当前正在刷新的正是这个出错的会话，停止 Loading 状态
          if (refreshingTitleChatId.value === errorChatId) {
            refreshingTitleChatId.value = null;
          }

          // 弹出错误提示，展示后端返回的具体错误信息
          ElMessage.error(notification.message);
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

    // Actions from Composable
    fetchChatList,
    createNewItem,
    updateChatSettings,
    deleteItem,
    reorderChatItems,
    duplicateChat,

    // Store-specific Actions
    refreshChatTitle,
    initializeNotificationListener,
  };
});
