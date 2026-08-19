// frontend/mambo/src/stores/chatListStore.ts

import { defineStore } from 'pinia';
import { ref, reactive } from 'vue';
import { ElMessage } from 'element-plus';
import {
  getChatChildren,
  createChat,
  deleteChat,
  updateChatSettings as updateChatSettingsAPI,
  moveChat,
  duplicateChat as duplicateChatAPI,
  generateChatTitle as generateChatTitleAPI,
  getChatLineage,
  archiveChats as archiveChatsAPI, checkTasksStatus, getChatWithMessages
} from '@/api/chatService';
import { subscribeToGlobalNotifications } from '@/services/notificationService';
import type { Chat, ChatCreate, ChatUpdate, MoveRequest, GlobalNotification, ChatArchiveRequest } from '@/api/types';
import { useChatSessionStore } from './chatSessionStore';
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';

/**
 * 管理会话列表（包括文件夹和聊天）的全局状态。
 * 采用增量懒加载模式管理会话数据。
 */
export const useChatListStore = defineStore('chatList', () => {
  // --- State ---
  const chatList = ref<Chat[]>([]);
  // 正在进行标题生成的会话 ID 集合（支持多会话并发）
  const refreshingTitleChatIds = reactive<Set<string>>(new Set());
  // 标题生成超时兜底定时器：chatId -> timeoutId
  const titleRefreshTimers = new Map<string, ReturnType<typeof setTimeout>>();

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
   * 清除指定会话的标题刷新状态与兜底定时器。
   */
  function _clearTitleRefresh(chatId: string) {
    refreshingTitleChatIds.delete(chatId);
    const timer = titleRefreshTimers.get(chatId);
    if (timer) {
      clearTimeout(timer);
      titleRefreshTimers.delete(chatId);
    }
  }

  /**
   * 主动拉取指定会话的最新名称并写回列表（对账）。
   */
  async function _reconcileChatName(chatId: string) {
    try {
      const chatData = await getChatWithMessages(chatId);
      const chatInList = chatList.value.find(c => c.id === chatId);
      if (chatInList && chatData.name && chatInList.name !== chatData.name) {
        chatInList.name = chatData.name;
      }
    } catch (err) {
      console.warn(`[TitleRefresh] Failed to reconcile chat name for ${chatId}:`, err);
    }
  }

  /**
   * 请求后端为指定会话自动生成标题。
   * @param chatId - 目标会话的ID。
   */
  async function refreshChatTitle(chatId: string) {
    refreshingTitleChatIds.add(chatId);

    // 启动超时兜底：15s 后若仍在刷新，则主动拉取对账，避免 SSE 通知丢失导致永久 loading
    const existingTimer = titleRefreshTimers.get(chatId);
    if (existingTimer) clearTimeout(existingTimer);
    const timer = setTimeout(async () => {
      if (refreshingTitleChatIds.has(chatId)) {
        await _reconcileChatName(chatId);
        _clearTitleRefresh(chatId);
      }
    }, 15000);
    titleRefreshTimers.set(chatId, timer);

    try {
      await generateChatTitleAPI(chatId);
      // 成功后，标题的更新将通过SSE通知来处理，届时会清除 refreshingTitleChatIds
    } catch (error) {
      console.error(`Failed to initiate title generation for chat ${chatId}:`, error);
      // 如果请求本身失败，立即清除加载状态
      _clearTitleRefresh(chatId);
    }
  }

  /**
   * 批量归档项目到新文件夹
   */
  async function archiveItems(request: ChatArchiveRequest) {
    try {
      const newFolder = await archiveChatsAPI(request);
      const parentIdToRefresh = request.parent_id || 'root';
      loadedFolderIds.value.delete(parentIdToRefresh);
      await fetchChatChildren(parentIdToRefresh);

      // [修复] 主动拉取新文件夹的内容，确保数据在前端是最新的，而不是盲目标记为已加载
      await fetchChatChildren(newFolder.id);

      return newFolder;
    } catch (error) {
      console.error('Failed to archive items:', error);
      throw error;
    }
  }

  /**
   * 初始化并监听来自服务器的全局通知（SSE）。
   * 用于实时更新会话标题、接收历史压缩结果以及处理异步任务错误。
   */
  function initializeNotificationListener() {
    subscribeToGlobalNotifications({
      onNotification: async (notification: GlobalNotification) => {

        if (notification.type === 'connected') {
          const sessionStore = useChatSessionStore();
          const tasksToCheck: string[] = [];

          // 对所有正在刷新标题的会话做重连对账
          const pendingTitleChatIds = Array.from(refreshingTitleChatIds);
          pendingTitleChatIds.forEach(id => {
            tasksToCheck.push(`title-gen-${id}`);
          });

          const pendingZipMessages = sessionStore.currentChatMessages.filter(msg =>
            msg.sub_messages.some(sm => sm.type === 'ZipHistory' && sm.status === 'generating')
          );
          pendingZipMessages.forEach(msg => {
            tasksToCheck.push(`zip-history-gen-${msg.id}`);
          });

          if (tasksToCheck.length === 0) return;

          try {
            const { running_tasks } = await checkTasksStatus(tasksToCheck);

            // 重连后，标题任务已结束（通知可能丢失）→ 主动对账每个会话
            pendingTitleChatIds.forEach(id => {
              const titleTaskId = `title-gen-${id}`;
              if (!running_tasks.includes(titleTaskId)) {
                _reconcileChatName(id).finally(() => {
                  _clearTitleRefresh(id);
                });
              }
            });

            if (pendingZipMessages.length > 0 && sessionStore.currentChatId) {
              let needRefresh = false;
              pendingZipMessages.forEach(msg => {
                const zipTaskId = `zip-history-gen-${msg.id}`;
                if (!running_tasks.includes(zipTaskId)) {
                  needRefresh = true;
                }
              });

              if (needRefresh) {
                const chatData = await getChatWithMessages(sessionStore.currentChatId);
                sessionStore.currentChatMessages = chatData.messages.sort((a, b) => a.sortOrder - b.sortOrder);
              }
            }

          } catch (error) {
            console.error('Failed to check tasks status during reconnection:', error);
          }
        }
        else if (notification.type === 'chat_update') {
          const { id, name } = notification.payload;
          const chatInList = chatList.value.find(c => c.id === id);
          if (chatInList) {
            chatInList.name = name;
          } else {
            // 会话未加载进列表（懒加载），主动对账一次，避免标题更新丢失
            _reconcileChatName(id);
          }
          _clearTitleRefresh(id);
        } else if (notification.type === 'zip_history_update') {
          const sessionStore = useChatSessionStore();
          if (sessionStore.currentChatId === notification.payload.chat_id) {
            sessionStore._addOrUpdateSubMessage(
              notification.payload.message_id,
              notification.payload.sub_message
            );
          }
        } else if (notification.type === 'notification' && notification.category === 'title_generation_error') {
          const errorChatId = notification.context.chat_id;
          _clearTitleRefresh(errorChatId);
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
    refreshingTitleChatIds,
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
    archiveItems,

    // Store-specific Actions
    refreshChatTitle,
    initializeNotificationListener,
  };
});
