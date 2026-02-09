// frontend/mambo/src/stores/chatListStore.ts

import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getChatChildren,
  createChat,
  deleteChat,
  updateChatSettings as updateChatSettingsAPI,
  moveChat,
  duplicateChat as duplicateChatAPI,
  generateChatTitle as generateChatTitleAPI,
  getChatLineage
} from '@/api/chatService';
import { subscribeToGlobalNotifications } from '@/services/notificationService';
import type { Chat, ChatCreate, ChatUpdate, MoveRequest, GlobalNotification } from '@/api/types';
import { useChatSessionStore } from './chatSessionStore';
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';

/**
 * 管理会话列表（包括文件夹和聊天）的全局状态。
 * 采用增量懒加载模式管理会话数据。
 */
export const useChatListStore = defineStore('chatList', () => {
  // --- State ---
  const chatList = ref<Chat[]>([]);
  const refreshingTitleChatId = ref<string | null>(null);

  // --- Actions ---

  // 使用通用 Composable 封装树形数据操作 (适配懒加载与移动接口)
  const {
    isLoading: isChatListLoading,
    loadedFolderIds,
    loadingFolders,
    initializeList: _initializeList,
    fetchChildren,
    createItem: createNewItem,
    updateItem: updateChatSettings,
    deleteItem,
    moveItem: moveChatItem,
    duplicateItem: duplicateChat,
    resolvePath
  } = useTreeStoreActions<Chat, ChatCreate, ChatUpdate>({
    items: chatList,
    api: {
      fetchChildren: getChatChildren,
      fetchLineage: getChatLineage,
      create: createChat,
      update: updateChatSettingsAPI,
      remove: async (id: string): Promise<void> => {
        await deleteChat(id);
      },
      move: async (req: MoveRequest): Promise<void> => {
        await moveChat(req);
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
   * 预测加载子文件夹内容。
   * 在父文件夹加载完成后触发，静默加载其包含的子文件夹的下一级内容。
   */
  async function prefetchSubFolders(parentId: string) {
    // 找出当前父节点下的所有子文件夹
    const subFolders = chatList.value.filter(item => {
      if (item.itemType !== 'folder') {
        return false;
      }
      // 如果是根目录加载，需要同时匹配 parentId 为 'root' 和 null 的情况
      if (parentId === 'root') {
        return item.parentId === 'root' || item.parentId === null;
      }
      return item.parentId === parentId;
    });

    if (subFolders.length === 0) return;

    // 使用 setTimeout 将预测加载放入宏任务队列，避免阻塞当前 UI 渲染
    setTimeout(() => {
      subFolders.forEach(folder => {
        // 如果该文件夹未加载且未处于加载中，则发起请求
        if (!loadedFolderIds.value.has(folder.id) && !loadingFolders.value.has(folder.id)) {
          // 调用 fetchChildren 但不等待其结果，实现静默加载
          fetchChildren(folder.id).catch(err => {
            console.warn(`[Prefetch] Failed to prefetch folder ${folder.id}:`, err);
          });
        }
      });
    }, 200);
  }

  /**
   * 初始化列表，并触发根目录下的子文件夹预加载。
   */
  async function initializeList() {
    await _initializeList();
    prefetchSubFolders('root');
  }

  /**
   * 包装 fetchChildren 以集成预测加载逻辑。
   * 组件应调用此方法而非直接调用 composable 的 fetchChildren。
   */
  async function fetchChatChildren(parentId: string) {
    await fetchChildren(parentId);
    // 加载成功后，触发预测加载
    prefetchSubFolders(parentId);
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
    loadedFolderIds,
    loadingFolders,

    // Actions
    initializeList,
    fetchChatChildren, // Exposed wrapper with prefetch
    createNewItem,
    updateChatSettings,
    deleteItem,
    moveChatItem,
    duplicateChat,
    resolvePath,

    // Store-specific Actions
    refreshChatTitle,
    initializeNotificationListener,
  };
});
