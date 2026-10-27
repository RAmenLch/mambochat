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
  archiveChats as archiveChatsAPI, checkTasksStatus, getChatWithMessages,
  getChatStatuses, touchChatRead
} from '@/api/chatService';
import { subscribeToGlobalNotifications } from '@/services/notificationService';
import type { Chat, ChatCreate, ChatUpdate, MoveRequest, GlobalNotification, ChatArchiveRequest, ChatStatusFlags } from '@/api/types';
import type { GroupCreatedResponse } from '@/api/types/groupChatTypes';
import { useChatSessionStore } from './chatSessionStore';
import { useGroupChatStore } from './groupChatStore';
import { useTreeStoreActions } from '@/composables/useTreeStoreActions';
import { isDefaultChatName } from '@/utils/chatName';

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
  // 会话实时状态（生成中 / 待审核 / 未读），仅保存已加载节点
  const chatStatusMap = reactive<Record<string, ChatStatusFlags>>({});
  // 状态查询批次号：用于丢弃过期响应
  let statusRequestSeq = 0;
  // 每个会话最近一次收到 SSE 状态事件的序号：避免对账响应覆盖更新的实时事件
  const statusEventVersions = new Map<string, number>();
  let statusEventTick = 0;

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
      removeChatStatus(deletedItem.id);
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
    refreshChatStatuses();
  }

  /**
   * 包装 fetchChildren 以集成预测加载逻辑。
   * 组件应调用此方法而非直接调用 composable 的 fetchChildren。
   */
  async function fetchChatChildren(parentId: string) {
    await fetchChildren(parentId);
    // 加载成功后，触发预测加载
    prefetchSubFolders(parentId);
    // 新加载的节点补一次状态对账（未展开的文件夹内部不查询）
    refreshChatStatuses(
      chatList.value
        .filter(c => (c.parentId ?? 'root') === parentId && _isDisplayableChat(c))
        .map(c => c.id)
    );
  }

  // --- 会话实时状态（生成中 / 待审核 / 未读） ---

  /**
   * 包装 resolvePath：回溯链路会加载文件夹子节点，完成后补一次状态对账。
   */
  async function resolveChatPath(targetId: string) {
    await resolvePath(targetId);
    refreshChatStatuses();
  }

  function _defaultStatusFlags(): ChatStatusFlags {
    return { generating: false, pendingReview: false, unread: false };
  }

  /**
   * 群父节点(folder)与群成员子会话不参与徽标展示。
   */
  function _isDisplayableChat(node: Chat): boolean {
    return node.itemType === 'chat' && !node.memberAlias;
  }

  /**
   * 合并式更新单个会话的状态（支持后端增量事件）。
   */
  function applyChatStatus(chatId: string, patch: Partial<ChatStatusFlags>) {
    const prev = chatStatusMap[chatId] ?? _defaultStatusFlags();
    chatStatusMap[chatId] = { ...prev, ...patch };
  }

  /**
   * 仅在本地清除未读标记（不产生网络请求）。
   */
  function clearLocalUnread(chatId: string) {
    const current = chatStatusMap[chatId];
    if (current) current.unread = false;
  }

  function removeChatStatus(chatId: string) {
    delete chatStatusMap[chatId];
  }

  /**
   * 推进会话已读水位：本地清除未读 + 服务端持久化。
   */
  async function markChatRead(chatId: string) {
    clearLocalUnread(chatId);
    try {
      await touchChatRead(chatId);
    } catch (err) {
      console.warn(`[ChatStatus] Failed to touch chat ${chatId}:`, err);
    }
  }

  function _loadedDisplayableChatIds(): string[] {
    return chatList.value.filter(_isDisplayableChat).map(c => c.id);
  }

  /**
   * 批量对账会话状态。不传 ids 时刷新所有已加载的可展示会话。
   */
  async function refreshChatStatuses(ids?: string[]) {
    const targetIds = (ids ?? _loadedDisplayableChatIds()).filter(Boolean);
    if (targetIds.length === 0) return;

    const seq = ++statusRequestSeq;
    // 记录请求发起时各会话的事件版本，响应回来时跳过期间被实时事件更新过的会话
    const eventSnapshot = new Map<string, number>();
    targetIds.forEach(chatId => eventSnapshot.set(chatId, statusEventVersions.get(chatId) ?? 0));

    try {
      const { statuses } = await getChatStatuses(targetIds);
      // 已有更新的一次对账发起，丢弃本次过期结果
      if (seq !== statusRequestSeq) return;

      Object.keys(chatStatusMap).forEach(chatId => {
        if (!chatList.value.some(c => c.id === chatId)) delete chatStatusMap[chatId];
      });

      targetIds.forEach(chatId => {
        if ((statusEventVersions.get(chatId) ?? 0) !== eventSnapshot.get(chatId)) return;
        const flags = statuses[chatId];
        chatStatusMap[chatId] = flags ? { ...flags } : _defaultStatusFlags();
      });
    } catch (err) {
      console.warn('[ChatStatus] Failed to fetch chat statuses:', err);
    }
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
   * 原子建群结果合并：把群父节点与全部成员子会话写入列表，
   * 并标记父级与群节点为已加载，避免"新建文件夹默认已加载且为空"的误判。
   */
  function mergeCreatedGroup(detail: GroupCreatedResponse) {
    const now = new Date().toISOString();
    const groupNode: Chat = {
      id: detail.groupId,
      name: detail.name,
      createdAt: now,
      systemPrompt: null,
      modelParameters: null,
      aiModelId: null,
      itemType: 'folder',
      parentId: detail.parentId ?? null,
      sortOrder: 0,
      lastOpenedAt: null,
      folderType: 'group',
      memberAlias: null,
    };
    const groupIndex = chatList.value.findIndex(c => c.id === detail.groupId);
    if (groupIndex === -1) chatList.value.push(groupNode);
    else Object.assign(chatList.value[groupIndex], groupNode);

    for (const m of detail.members) {
      const memberNode: Chat = {
        id: m.chatId,
        name: m.name,
        createdAt: now,
        systemPrompt: null,
        modelParameters: null,
        aiModelId: null,
        itemType: 'chat',
        parentId: detail.groupId,
        sortOrder: m.sortOrder,
        lastOpenedAt: null,
        chatMode: 'agent',
        agentId: m.agentId ?? null,
        folderType: null,
        memberAlias: m.memberAlias,
      };
      const mi = chatList.value.findIndex(c => c.id === m.chatId);
      if (mi === -1) chatList.value.push(memberNode);
      else Object.assign(chatList.value[mi], memberNode);
    }

    loadedFolderIds.value.add(detail.groupId);
    const parentKey = detail.parentId ?? 'root';
    loadedFolderIds.value.add(parentKey);
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

          // 重连后对已加载会话做一次状态对账（SSE 断线期间的事件可能丢失）
          refreshChatStatuses();

          // 对所有正在刷新标题的会话做重连对账
          const pendingTitleChatIds = Array.from(refreshingTitleChatIds);
          pendingTitleChatIds.forEach(id => {
            tasksToCheck.push(`title-gen-${id}`);
          });

          // [增强] 自动标题生成完成后，若 SSE 通知在断线期间丢失，且会话已不在
          // refreshingTitleChatIds（页面停留列表页场景），重连时对仍为默认标题的
          // 会话做一次对账，避免列表长期显示默认名。_reconcileChatName 仅在
          // 名字确实变化时写回，幂等安全。
          chatList.value
            .filter(c => c.itemType === 'chat' && isDefaultChatName(c.name))
            .forEach(c => _reconcileChatName(c.id));

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

            // 群组：断线期间 group_* 通知可能丢失，重连后对当前打开中的群做一次对账
            const openedGroupId = sessionStore.currentGroupId;
            if (openedGroupId) {
              useGroupChatStore()
                .refresh(openedGroupId)
                .catch(err => console.error('Failed to reconcile opened group after reconnect:', err));
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
        } else if (notification.type === 'chat_status') {
          const { chat_id: statusChatId, status, ...flags } = notification.payload;
          statusEventVersions.set(statusChatId, ++statusEventTick);
          applyChatStatus(statusChatId, flags);

          const sessionStore = useChatSessionStore();
          if (
            status === 'unread' &&
            statusChatId === sessionStore.currentChatId &&
            document.visibilityState === 'visible'
          ) {
            // 用户正停留在该会话，立即推进已读水位，避免误报未读
            markChatRead(statusChatId);
          }
        } else if (notification.type === 'notification' && notification.category === 'title_generation_error') {
          const errorChatId = notification.context.chat_id;
          _clearTitleRefresh(errorChatId);
          ElMessage.error(notification.message);
        } else if (
          notification.type === 'notification' &&
          (notification.category === 'group_created' ||
            notification.category === 'group_state_changed' ||
            notification.category === 'group_task_changed' ||
            notification.category === 'group_mail_sent' ||
            notification.category === 'group_deleted')
        ) {
          const groupStore = useGroupChatStore();
          if (notification.category === 'group_deleted') {
            const gid = notification.context.groupId;
            const idx = chatList.value.findIndex(c => c.id === gid);
            if (idx !== -1) chatList.value.splice(idx, 1);
            removeChatStatus(gid);
            return;
          }
          await groupStore.applyNotification(notification.context, notification.category);
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
    chatStatusMap,

    // Actions
    initializeList,
    fetchChatChildren, // Exposed wrapper with prefetch
    createNewItem,
    updateChatSettings,
    deleteItem,
    moveChatItem,
    duplicateChat,
    resolvePath: resolveChatPath,
    archiveItems,
    mergeCreatedGroup,

    // Store-specific Actions
    refreshChatTitle,
    initializeNotificationListener,

    // 会话实时状态
    applyChatStatus,
    refreshChatStatuses,
    markChatRead,
    clearLocalUnread,
    removeChatStatus,
  };
});
