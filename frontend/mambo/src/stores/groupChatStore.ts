// frontend/mambo/src/stores/groupChatStore.ts

import { defineStore } from 'pinia';
import { ref } from 'vue';
import * as groupApi from '@/api/groupChatService';
import type {
  GroupDetail,
  GroupMail,
  GroupTask,
  GroupNotificationContext,
  GroupSettingsUpdate,
  GroupMailReview,
  GroupMailDecision,
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
  const mailReviews = ref<Record<string, GroupMailReview>>({});
  const loading = ref<Record<string, boolean>>({});
  /** 每个群当前生效的邮件筛选条件（发信人/收信人别名 + 并集/交集组合方式） */
  interface MailFilterState {
    sender: string[];
    recipient: string[];
    combine: 'union' | 'intersection';
  }
  const mailFilters = ref<Record<string, MailFilterState>>({});

  function ensure(groupId: string) {
    if (!mails.value[groupId]) mails.value[groupId] = [];
    if (!tasks.value[groupId]) tasks.value[groupId] = [];
  }

  /** 设置某群的邮件筛选条件（调用方随后应 reset 重新拉取） */
  function setMailFilters(groupId: string, filters: MailFilterState): void {
    mailFilters.value[groupId] = {
      sender: [...filters.sender],
      recipient: [...filters.recipient],
      combine: filters.combine,
    };
  }

  async function loadDetail(groupId: string): Promise<GroupDetail | null> {
    const detail = await groupApi.getGroupDetail(groupId);
    details.value[groupId] = detail;
    return detail;
  }

  async function loadMails(groupId: string, reset = false, force = false): Promise<void> {
    ensure(groupId);
    if (reset) {
      mails.value[groupId] = [];
      mailCursor.value[groupId] = null;
      mailHasMore.value[groupId] = true;
    }
    // hasMore=false 只说明上一页未取满，不代表没有新邮件；
    // 实时对账（force=true）时必须忽略该标记，按游标继续向后拉取，
    // 否则新投递的邮件不可见，只能靠刷新页面。
    if (!force && mailHasMore.value[groupId] === false) return;
    const after = mailCursor.value[groupId] ?? null;
    const page = await groupApi.listGroupMails(groupId, after, 50, mailFilters.value[groupId]);
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

  /** 审核模式：拉取待审核邮件与已决策邮件 */
  async function loadMailReviews(groupId: string): Promise<void> {
    mailReviews.value[groupId] = await groupApi.listMailReviews(groupId);
  }

  async function refresh(groupId: string, resetMails = false): Promise<void> {
    loading.value[groupId] = true;
    try {
      await Promise.all([
        loadDetail(groupId),
        loadMails(groupId, resetMails, true),
        loadTasks(groupId),
        loadMailReviews(groupId),
      ]);
    } finally {
      loading.value[groupId] = false;
    }
  }

  async function sendMessage(
    groupId: string,
    content: string,
    recipientNames: string[] = [],
    requestId?: string,
    attachmentFileIds: string[] = [],
  ) {
    const res = await groupApi.sendGroupMessage(groupId, {
      content,
      recipientNames,
      requestId: requestId ?? null,
      attachmentFileIds,
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

  /** 修改群设置（自动轮次上限 / 重置本次额度周期的已用轮次 / 邮件投递模式） */
  async function updateSettings(groupId: string, data: GroupSettingsUpdate) {
    const res = await groupApi.updateGroupSettings(groupId, data);
    await loadDetail(groupId);
    return res;
  }

  /** 审核模式：同意投递一封待审核邮件 */
  async function approveMail(groupId: string, mailId: string): Promise<GroupMailDecision> {
    const res = await groupApi.approveMail(groupId, mailId);
    await Promise.all([loadMailReviews(groupId), loadDetail(groupId), loadTasks(groupId)]);
    return res;
  }

  /** 审核模式：拒绝投递一封待审核邮件（需填写原因） */
  async function rejectMail(
    groupId: string,
    mailId: string,
    reason: string,
  ): Promise<GroupMailDecision> {
    const res = await groupApi.rejectMail(groupId, mailId, reason);
    await Promise.all([loadMailReviews(groupId), loadDetail(groupId), loadTasks(groupId)]);
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

  /**
   * 全局通知对账：仅轻量刷新受影响群，不重复广播邮件正文。
   * `category` 用于放宽判定：邮件投递只保证 mailId/sequence，不保证 version 一定推进，
   * 因此邮件事件以及「版本未推进」的情况都要按游标补拉一次邮件。
   */
  async function applyNotification(
    ctx: GroupNotificationContext,
    category?: string,
  ): Promise<void> {
    if (!ctx?.groupId) return;
    const gid = ctx.groupId;
    const current = details.value[gid];
    const isMailEvent = category === 'group_mail_sent';
    if (!isMailEvent && ctx.version !== undefined && current && ctx.version <= current.version) {
      // 版本未推进：至少把游标之后的新邮件拉回来，避免整条事件被丢弃
      await loadMails(gid, false, true);
      return;
    }
    await Promise.all([
      loadDetail(gid),
      loadMails(gid, false, true),
      loadTasks(gid),
      loadMailReviews(gid),
    ]);
  }

  return {
    details,
    mails,
    mailCursor,
    mailHasMore,
    tasks,
    mailReviews,
    loading,
    mailFilters,
    loadDetail,
    loadMails,
    loadTasks,
    loadMailReviews,
    refresh,
    setMailFilters,
    sendMessage,
    pause,
    resume,
    updateSettings,
    approveMail,
    rejectMail,
    retryTask,
    cancelTask,
    discardTask,
    processUnread,
    applyNotification,
  };
});
