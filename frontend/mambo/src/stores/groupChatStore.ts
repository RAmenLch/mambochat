// frontend/mambo/src/stores/groupChatStore.ts

import { defineStore } from 'pinia';
import { ref } from 'vue';
import * as groupApi from '@/api/groupChatService';
import type {
  GroupDetail,
  GroupMail,
  GroupTask,
  GroupNotificationContext,
} from '@/api/types/groupChatTypes';

/**
 * 按 groupId 保存群状态、邮件游标与任务队列。
 * 不覆盖 currentChatMessages —— 群页面只显示已投递的成员邮件。
 */
export const useGroupChatStore = defineStore('groupChat', () => {
  const details = ref<Record<string, GroupDetail>>({});
  const mails = ref<Record<string, GroupMail[]>>({});
  const mailCursor = ref<Record<string, number | null>>({});
  const mailHasMore = ref<Record<string, boolean>>({});
  const tasks = ref<Record<string, GroupTask[]>>({});
  const loading = ref<Record<string, boolean>>({});

  function ensure(groupId: string) {
    if (!mails.value[groupId]) mails.value[groupId] = [];
    if (!tasks.value[groupId]) tasks.value[groupId] = [];
  }

  async function loadDetail(groupId: string): Promise<GroupDetail | null> {
    const detail = await groupApi.getGroupDetail(groupId);
    details.value[groupId] = detail;
    return detail;
  }

  async function loadMails(groupId: string, reset = false): Promise<void> {
    ensure(groupId);
    if (reset) {
      mails.value[groupId] = [];
      mailCursor.value[groupId] = null;
      mailHasMore.value[groupId] = true;
    }
    if (mailHasMore.value[groupId] === false) return;
    const after = mailCursor.value[groupId] ?? null;
    const page = await groupApi.listGroupMails(groupId, after);
    // 去重合并，维持 sequence 稳定顺序
    const existing = new Map(mails.value[groupId].map((m) => [m.id, m]));
    for (const mail of page.items) existing.set(mail.id, mail);
    mails.value[groupId] = Array.from(existing.values()).sort(
      (a, b) => (a.sequence ?? 0) - (b.sequence ?? 0),
    );
    mailCursor.value[groupId] = page.nextAfterSequence ?? null;
    mailHasMore.value[groupId] = page.hasMore;
  }

  async function loadTasks(groupId: string): Promise<void> {
    ensure(groupId);
    const res = await groupApi.listGroupTasks(groupId);
    tasks.value[groupId] = res.items;
  }

  async function refresh(groupId: string, resetMails = false): Promise<void> {
    loading.value[groupId] = true;
    try {
      await Promise.all([loadDetail(groupId), loadMails(groupId, resetMails), loadTasks(groupId)]);
    } finally {
      loading.value[groupId] = false;
    }
  }

  async function sendMessage(
    groupId: string,
    content: string,
    recipientNames: string[] = [],
    requestId?: string,
  ) {
    const res = await groupApi.sendGroupMessage(groupId, {
      content,
      recipientNames,
      requestId: requestId ?? null,
    });
    await loadTasks(groupId);
    return res;
  }

  async function pause(groupId: string) {
    const res = await groupApi.pauseGroup(groupId);
    await loadDetail(groupId);
    return res;
  }

  async function resume(groupId: string) {
    const res = await groupApi.resumeGroup(groupId);
    await loadDetail(groupId);
    return res;
  }

  async function retryTask(groupId: string, taskId: string) {
    const res = await groupApi.retryGroupTask(groupId, taskId);
    await refresh(groupId);
    return res;
  }

  async function cancelTask(groupId: string, taskId: string) {
    const res = await groupApi.cancelGroupTask(groupId, taskId);
    await loadTasks(groupId);
    return res;
  }

  async function discardTask(groupId: string, taskId: string) {
    const res = await groupApi.discardGroupTask(groupId, taskId);
    await refresh(groupId);
    return res;
  }

  async function processUnread(groupId: string, memberChatId: string) {
    const res = await groupApi.processMemberUnread(groupId, memberChatId);
    await loadTasks(groupId);
    return res;
  }

  /** 全局通知对账：仅轻量刷新受影响群，不重复广播邮件正文。 */
  async function applyNotification(ctx: GroupNotificationContext): Promise<void> {
    if (!ctx?.groupId) return;
    const current = details.value[ctx.groupId];
    if (ctx.version !== undefined && current && ctx.version <= current.version) {
      return;
    }
    await Promise.all([loadDetail(ctx.groupId), loadMails(ctx.groupId), loadTasks(ctx.groupId)]);
  }

  return {
    details,
    mails,
    mailCursor,
    mailHasMore,
    tasks,
    loading,
    loadDetail,
    loadMails,
    loadTasks,
    refresh,
    sendMessage,
    pause,
    resume,
    retryTask,
    cancelTask,
    discardTask,
    processUnread,
    applyNotification,
  };
});
