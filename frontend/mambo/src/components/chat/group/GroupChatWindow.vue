<!-- frontend/mambo/src/components/chat/group/GroupChatWindow.vue -->
<template>
  <div class="group-window">
    <div class="group-main">
      <div class="group-header">
        <div class="header-left">
          <el-icon class="group-icon"><UserFilled /></el-icon>
          <span class="group-name">{{ detail?.name || $t('groupChat.create.title') }}</span>
          <el-tag :type="statusTagType" size="small">{{ statusText }}</el-tag>
          <span v-if="pauseReasonText" class="pause-reason">{{ pauseReasonText }}</span>
        </div>
        <div class="header-right">
          <el-tooltip :content="roundInfoTip" placement="bottom">
            <span class="round-info">
              {{ $t('groupChat.window.roundThisEpisode') }}
              {{ detail?.autoRoundCount ?? 0 }} / {{ detail?.autoRoundLimit ?? '-' }}
            </span>
          </el-tooltip>
          <el-button
            v-if="detail?.status === 'ready'"
            size="small"
            @click="onPause"
          >{{ $t('groupChat.control.pause') }}</el-button>
          <el-button
            v-else-if="detail?.status === 'paused'"
            size="small"
            type="primary"
            @click="onResume"
          >{{ $t('groupChat.control.resume') }}</el-button>
          <el-button
            v-if="(detail?.autoRoundCount ?? 0) > 0"
            size="small"
            @click="onResetRoundCount"
          >{{ $t('groupChat.control.resetRoundCount') }}</el-button>
          <el-popover placement="bottom-end" :width="320" trigger="click" @show="syncSettingsDraft">
            <template #reference>
              <el-button size="small" :icon="Setting" />
            </template>
            <div class="group-settings">
              <div class="settings-title">{{ $t('groupChat.control.settings') }}</div>
              <div class="settings-row">
                <span class="settings-label">{{ $t('groupChat.create.autoRoundLimit') }}</span>
                <el-input-number
                  v-model="limitDraft"
                  :min="1"
                  :max="100000"
                  size="small"
                  controls-position="right"
                />
              </div>
              <div class="settings-row settings-row-block">
                <span class="settings-label">{{ $t('groupChat.create.mailMode') }}</span>
                <el-radio-group v-model="mailModeDraft" class="settings-radio">
                  <el-radio value="auto">{{ $t('groupChat.create.mailModeAuto') }}</el-radio>
                  <el-radio value="review">{{ $t('groupChat.create.mailModeReview') }}</el-radio>
                </el-radio-group>
              </div>
              <div class="settings-hint">{{ $t('groupChat.window.mailModeHint') }}</div>
              <div class="settings-actions">
                <el-button
                  size="small"
                  type="primary"
                  :loading="savingSettings"
                  @click="onSaveSettings"
                >
                  {{ $t('groupChat.control.save') }}
                </el-button>
              </div>
            </div>
          </el-popover>
          <el-button size="small" :icon="Refresh" @click="onRefresh" />
        </div>
      </div>

      <div v-if="stuckTask" class="recovery-bar" :class="{ 'is-warning': isWaitingHuman || canRetryTask }">
        <span class="recovery-text">{{ recoveryText }}</span>
        <div class="recovery-actions">
          <el-button
            v-if="isWaitingHuman"
            size="small"
            type="warning"
            @click="onOpenStuckSession"
          >{{ $t('groupChat.recovery.openSession') }}</el-button>
          <el-button
            v-if="canRetryTask"
            size="small"
            type="primary"
            @click="onRetryTask"
          >{{ $t('groupChat.control.retry') }}</el-button>
          <el-button v-if="canDiscardTask" size="small" @click="onDiscardTask">
            {{ $t('groupChat.control.discard') }}
          </el-button>
          <el-button v-if="canCancelTask" size="small" type="danger" plain @click="onCancelTask">
            {{ $t('groupChat.control.cancel') }}
          </el-button>
        </div>
      </div>

      <div class="group-body">
        <div class="mail-column">
          <GroupMailReviewPanel
            :pending="pendingReviewMails"
            :decided="decidedMails"
            :busy-id="reviewBusyId"
            :busy="reviewBusy"
            @approve="onApproveMail"
            @reject="onRejectMail"
            @approve-all="onApproveAllMails"
            @reject-all="onRejectAllMails"
          />
          <GroupMailList
            :mails="mails"
            :loading="isLoading"
            :has-more="hasMore"
            @load-more="onLoadMore"
          />
        </div>
        <div class="side-column">
          <GroupMemberPanel
            :members="members"
            :active-tasks="memberActiveTasks"
            :queued-counts="memberQueuedCounts"
            @open-sub-session="onOpenSubSession"
            @process-unread="onProcessUnread"
          />
        </div>
      </div>
    </div>

    <GroupChatComposer :members="members" @send="onSend" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onUnmounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Refresh, Setting, UserFilled } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useGroupChatStore } from '@/stores/groupChatStore';
import type { GroupMailMode, GroupSettingsUpdate, GroupTask } from '@/api/types/groupChatTypes';
import GroupMailList from './GroupMailList.vue';
import GroupMailReviewPanel from './GroupMailReviewPanel.vue';
import GroupMemberPanel from './GroupMemberPanel.vue';
import GroupChatComposer from './GroupChatComposer.vue';

const { t } = useI18n();
const router = useRouter();
const sessionStore = useChatSessionStore();
const groupStore = useGroupChatStore();

const { currentGroupId } = storeToRefs(sessionStore);
const { details } = storeToRefs(groupStore);

const groupId = computed(() => currentGroupId.value);
const detail = computed(() => (groupId.value ? details.value[groupId.value] : undefined));
const members = computed(() => detail.value?.members ?? []);
const mails = computed(() => (groupId.value ? groupStore.mails[groupId.value] ?? [] : []));
const hasMore = computed(() => (groupId.value ? !!groupStore.mailHasMore[groupId.value] : false));
const isLoading = computed(() => (groupId.value ? !!groupStore.loading[groupId.value] : false));

const statusText = computed(() =>
  detail.value ? t(`groupChat.status.${detail.value.status}`) : '',
);
const statusTagType = computed(() => {
  if (detail.value?.status === 'ready') return 'success';
  if (detail.value?.status === 'paused') return 'warning';
  return 'info';
});

const tasks = computed(() => (groupId.value ? groupStore.tasks[groupId.value] ?? [] : []));

// ── 审核模式：待审核 / 已决策邮件 ──
const reviews = computed(() =>
  groupId.value
    ? groupStore.mailReviews[groupId.value] ?? { pending: [], decided: [] }
    : { pending: [], decided: [] },
);
const pendingReviewMails = computed(() => reviews.value.pending);
const decidedMails = computed(() => reviews.value.decided);
const reviewBusyId = ref<string | null>(null);
const reviewBusy = ref(false);

/** 成员的“在跑/等待人工”任务：群内串行，同一成员最多一个非终态轮次 */
function activeTaskMap(): Record<string, GroupTask> {
  const map: Record<string, GroupTask> = {};
  for (const task of tasks.value) {
    if (!['running', 'waiting_review', 'waiting_user'].includes(task.state)) continue;
    const cur = map[task.memberChatId];
    if (!cur || task.sequence < cur.sequence) map[task.memberChatId] = task;
  }
  return map;
}
const memberActiveTasks = computed(activeTaskMap);

/** 真正排队中的任务数（不含执行中与等待人工） */
const memberQueuedCounts = computed(() => {
  const map: Record<string, number> = {};
  for (const task of tasks.value) {
    if (task.state !== 'queued') continue;
    map[task.memberChatId] = (map[task.memberChatId] ?? 0) + 1;
  }
  return map;
});

function memberAliasOf(chatId?: string | null): string {
  if (!chatId) return '';
  return members.value.find((m) => m.chatId === chatId)?.memberAlias ?? '';
}

/** 非正常结束、需要人工处理的轮次状态 */
const RECOVERABLE_STATES = ['failed', 'interrupted', 'cancelled'];

/**
 * 当前“卡住”的轮次：优先执行中/等待人工的轮次；若群因异常结束而暂停，则取最近一个失败/中断/取消的轮次。
 * 群内串行，因此最多只有一个这样的轮次。
 */
const stuckTask = computed<GroupTask | null>(() => {
  const live = tasks.value
    .filter((t) => ['running', 'waiting_review', 'waiting_user'].includes(t.state))
    .sort((a, b) => a.sequence - b.sequence)[0];
  if (live) return live;
  const reason = detail.value?.pauseReason;
  if (!reason || !['failure', 'cancelled', 'restart'].includes(reason)) return null;
  const broken = tasks.value
    .filter((t) => RECOVERABLE_STATES.includes(t.state))
    .sort((a, b) => b.sequence - a.sequence)[0];
  return broken ?? null;
});

const stuckAlias = computed(() => memberAliasOf(stuckTask.value?.memberChatId));
const canRetryTask = computed(
  () => !!stuckTask.value && RECOVERABLE_STATES.includes(stuckTask.value.state),
);
const canDiscardTask = computed(() => !!stuckTask.value && stuckTask.value.state !== 'running');
const canCancelTask = computed(() => stuckTask.value?.state === 'running');
const isWaitingHuman = computed(
  () => !!stuckTask.value && ['waiting_review', 'waiting_user'].includes(stuckTask.value.state),
);
const recoveryText = computed(() => {
  const task = stuckTask.value;
  if (!task) return '';
  return t('groupChat.recovery.taskLine', {
    alias: memberAliasOf(task.memberChatId) || '-',
    kind: t(`groupChat.task.kind.${task.kind}`),
    state: t(`groupChat.task.state.${task.state}`),
  });
});

const pauseReasonText = computed(() => {
  const reason = detail.value?.pauseReason;
  if (!reason) return '';
  const text = t(`groupChat.pauseReason.${reason}`);
  return stuckAlias.value
    ? t('groupChat.window.pauseReasonWithMember', { reason: text, alias: stuckAlias.value })
    : text;
});
const roundInfoTip = computed(() =>
  t('groupChat.window.roundInfoTip', {
    used: detail.value?.autoRoundCount ?? 0,
    limit: detail.value?.autoRoundLimit ?? 0,
    total: detail.value?.totalAutoRoundCount ?? 0,
  }),
);

// SSE 通知可能在断线或版本未推进时漏掉，群页在有活动时做兜底轮询：
// 空闲（无排队、无未读、无本地动作）时完全不发请求。
const POLL_INTERVAL_MS = 4000;
const LOCAL_ACTIVITY_WINDOW_MS = 3 * 60 * 1000;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let localActivityUntil = 0;

/** 用户本地动作（发送/恢复/处理未读）后，短时间内无条件对账，避免首条事件丢失时卡死 */
function markLocalActivity() {
  localActivityUntil = Date.now() + LOCAL_ACTIVITY_WINDOW_MS;
}

function hasGroupActivity(): boolean {
  const d = detail.value;
  if (!d) return false;
  if (d.status !== 'ready') return Date.now() < localActivityUntil;
  return (d.queuedCount || 0) > 0 || (d.unreadCount || 0) > 0 || Date.now() < localActivityUntil;
}

async function pollGroup() {
  const gid = groupId.value;
  if (!gid || !hasGroupActivity()) return;
  try {
    await groupStore.refresh(gid);
  } catch (error) {
    console.error('Failed to poll group state:', error);
  }
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

watch(
  groupId,
  (gid) => {
    stopPolling();
    if (!gid) return;
    groupStore.refresh(gid, true);
    pollTimer = setInterval(() => {
      void pollGroup();
    }, POLL_INTERVAL_MS);
  },
  { immediate: true },
);

onUnmounted(stopPolling);

async function onRefresh() {
  if (groupId.value) await groupStore.refresh(groupId.value);
}

async function onLoadMore() {
  if (groupId.value) await groupStore.loadMails(groupId.value);
}

async function onSend(payload: { content: string; recipientNames: string[] }) {
  if (!groupId.value) return;
  try {
    await groupStore.sendMessage(groupId.value, payload.content, payload.recipientNames);
    markLocalActivity();
    ElMessage.success(t('groupChat.window.messageQueued'));
  } catch (error) {
    console.error('Failed to send group message:', error);
  }
}

async function onPause() {
  if (groupId.value) await groupStore.pause(groupId.value);
}

async function onResume() {
  if (!groupId.value) return;
  try {
    markLocalActivity();
    await groupStore.resume(groupId.value);
  } catch (error) {
    console.error('Failed to resume group:', error);
  }
}

async function onProcessUnread(memberChatId: string) {
  if (!groupId.value) return;
  try {
    markLocalActivity();
    await groupStore.processUnread(groupId.value, memberChatId);
  } catch (error) {
    console.error('Failed to process unread:', error);
  }
}

/** 重置本次沟通的自动轮次计数（达到轮次上限后可用它再放行预算） */
async function onResetRoundCount() {
  if (!groupId.value) return;
  try {
    markLocalActivity();
    await groupStore.updateSettings(groupId.value, { resetAutoRoundCount: true });
    ElMessage.success(t('groupChat.control.resetRoundCountDone'));
  } catch (error) {
    console.error('Failed to reset auto round count:', error);
  }
}

// ── 群设置：自动轮次上限 / 邮件投递模式（建群后仍可修改） ──
const limitDraft = ref(50);
const mailModeDraft = ref<GroupMailMode>('auto');
const savingSettings = ref(false);

/** 打开设置面板时用当前群状态回填，避免残留上次草稿 */
function syncSettingsDraft() {
  limitDraft.value = detail.value?.autoRoundLimit ?? 50;
  mailModeDraft.value = detail.value?.mailMode ?? 'auto';
}

/** 保存群设置：只提交发生变化的字段（无改动不发请求） */
async function onSaveSettings() {
  if (!groupId.value) return;
  const d = detail.value;
  if (!d) return;
  const payload: GroupSettingsUpdate = {};
  if (limitDraft.value !== d.autoRoundLimit) payload.autoRoundLimit = limitDraft.value;
  if (mailModeDraft.value !== (d.mailMode ?? 'auto')) payload.mailMode = mailModeDraft.value;
  if (payload.autoRoundLimit === undefined && payload.mailMode === undefined) return;
  savingSettings.value = true;
  try {
    markLocalActivity();
    await groupStore.updateSettings(groupId.value, payload);
    ElMessage.success(t('common.msg.updateSuccess'));
  } catch (error) {
    console.error('Failed to update group settings:', error);
  } finally {
    savingSettings.value = false;
  }
}

function onOpenSubSession(memberChatId: string) {
  router.push(`/chat/${memberChatId}`);
}

/** 打开卡住的那个成员的子会话（等待工具审核 / 等待用户回答时必须在那里处理） */
function onOpenStuckSession() {
  const chatId = stuckTask.value?.memberChatId;
  if (chatId) router.push(`/chat/${chatId}`);
}

/** 恢复该轮：复用原 assistant 消息重新排队执行，不新建轮次 */
async function onRetryTask() {
  if (!groupId.value || !stuckTask.value) return;
  try {
    markLocalActivity();
    await groupStore.retryTask(groupId.value, stuckTask.value.id);
  } catch (error) {
    console.error('Failed to retry group task:', error);
  }
}

/** 放弃该轮：丢弃本轮暂存邮件（不撤回已发送的），随后继续后续任务 */
async function onDiscardTask() {
  if (!groupId.value || !stuckTask.value) return;
  try {
    markLocalActivity();
    await groupStore.discardTask(groupId.value, stuckTask.value.id);
  } catch (error) {
    console.error('Failed to discard group task:', error);
  }
}

/** 停止处理：向正在生成的轮次发送取消信号 */
async function onCancelTask() {
  if (!groupId.value || !stuckTask.value) return;
  try {
    markLocalActivity();
    await groupStore.cancelTask(groupId.value, stuckTask.value.id);
  } catch (error) {
    console.error('Failed to cancel group task:', error);
  }
}

// ── 审核模式：同意 / 拒绝待投递邮件 ──

/** 同意一封 */
async function onApproveMail(mailId: string) {
  if (!groupId.value) return;
  reviewBusyId.value = mailId;
  try {
    markLocalActivity();
    const res = await groupStore.approveMail(groupId.value, mailId);
    if (res.finalized) ElMessage.success(t('groupChat.review.finalized'));
  } catch (error) {
    console.error('Failed to approve group mail:', error);
  } finally {
    reviewBusyId.value = null;
  }
}

/** 拒绝一封（原因必填） */
async function onRejectMail(mailId: string, reason: string) {
  if (!groupId.value) return;
  reviewBusyId.value = mailId;
  try {
    markLocalActivity();
    const res = await groupStore.rejectMail(groupId.value, mailId, reason);
    if (res.finalized) ElMessage.warning(t('groupChat.review.finalizedRejected'));
  } catch (error) {
    console.error('Failed to reject group mail:', error);
  } finally {
    reviewBusyId.value = null;
  }
}

/** 全部同意（逐封提交，末封定稿后自动继续后续流程） */
async function onApproveAllMails() {
  if (!groupId.value) return;
  reviewBusy.value = true;
  try {
    markLocalActivity();
    let finalized = false;
    for (const mail of [...pendingReviewMails.value]) {
      const res = await groupStore.approveMail(groupId.value, mail.id);
      finalized = finalized || res.finalized;
    }
    if (finalized) ElMessage.success(t('groupChat.review.finalized'));
  } catch (error) {
    console.error('Failed to approve all group mails:', error);
  } finally {
    reviewBusy.value = false;
  }
}

/** 全部拒绝（共用同一原因） */
async function onRejectAllMails(reason: string) {
  if (!groupId.value) return;
  reviewBusy.value = true;
  try {
    markLocalActivity();
    let finalized = false;
    for (const mail of [...pendingReviewMails.value]) {
      const res = await groupStore.rejectMail(groupId.value, mail.id, reason);
      finalized = finalized || res.finalized;
    }
    if (finalized) ElMessage.warning(t('groupChat.review.finalizedRejected'));
  } catch (error) {
    console.error('Failed to reject all group mails:', error);
  } finally {
    reviewBusy.value = false;
  }
}
</script>

<style scoped>
.group-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
/* 头部与正文保留内边距；输入区通栏，与普通会话输入区观感一致 */
.group-main {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px;
  gap: 12px;
  overflow: hidden;
}
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.group-name {
  font-weight: 600;
  font-size: 16px;
}
.pause-reason {
  font-size: 12px;
  color: var(--el-color-warning);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.round-info {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.group-body {
  flex: 1;
  display: flex;
  gap: 16px;
  overflow: hidden;
}
.mail-column {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
}
.side-column {
  width: 260px;
  flex-shrink: 0;
  overflow-y: auto;
}
/* 需要人工处理的轮次横幅 */
.recovery-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}
/* 等待人工 / 异常结束：改用警示色提示需要介入 */
.recovery-bar.is-warning {
  background: var(--el-color-warning-light-9);
  box-shadow: inset 0 0 0 1px var(--el-color-warning-light-5);
}
.recovery-text {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.recovery-bar.is-warning .recovery-text {
  color: var(--el-color-warning-dark-2);
}
.recovery-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
/* 群设置气泡：自动轮次上限 / 邮件投递模式 */
.group-settings {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.settings-title {
  font-weight: 600;
  font-size: 13px;
}
.settings-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.settings-label {
  flex: 1;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
/* 邮件投递模式：标签在上、单选竖排，避免下拉在气泡内被裁切 */
.settings-row-block {
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}
.settings-row-block .settings-label {
  flex: none;
}
.settings-row :deep(.el-input-number) {
  width: 112px;
}
.settings-radio {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.settings-radio :deep(.el-radio) {
  height: 24px;
  margin-right: 0;
}
.settings-actions {
  display: flex;
  justify-content: flex-end;
}
.settings-hint {
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-text-color-secondary);
}
</style>
