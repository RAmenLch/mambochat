<!-- frontend/mambo/src/components/chat/group/GroupChatWindow.vue -->
<template>
  <div class="group-window">
    <div class="group-header">
      <div class="header-left">
        <el-icon class="group-icon"><UserFilled /></el-icon>
        <span class="group-name">{{ detail?.name || $t('groupChat.create.title') }}</span>
        <el-tag :type="statusTagType" size="small">{{ statusText }}</el-tag>
        <span v-if="pauseReasonText" class="pause-reason">{{ pauseReasonText }}</span>
      </div>
      <div class="header-right">
        <span class="round-info">
          {{ detail?.autoRoundCount ?? 0 }} / {{ detail?.autoRoundLimit ?? '-' }}
        </span>
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
        <el-button size="small" :icon="Refresh" @click="onRefresh" />
      </div>
    </div>

    <div class="group-body">
      <div class="mail-column">
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
          @open-sub-session="onOpenSubSession"
          @process-unread="onProcessUnread"
        />
      </div>
    </div>

    <GroupChatComposer :members="members" @send="onSend" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Refresh, UserFilled } from '@element-plus/icons-vue';
import { useI18n } from 'vue-i18n';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useGroupChatStore } from '@/stores/groupChatStore';
import GroupMailList from './GroupMailList.vue';
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
const pauseReasonText = computed(() => {
  const reason = detail.value?.pauseReason;
  return reason ? t(`groupChat.pauseReason.${reason}`) : '';
});

watch(
  groupId,
  (gid) => {
    if (gid) groupStore.refresh(gid, true);
  },
  { immediate: true },
);

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
    if (!payload.recipientNames.length) {
      ElMessage.success(t('common.msg.operationSuccess'));
    } else {
      ElMessage.success(t('common.msg.operationSuccess'));
    }
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
    await groupStore.resume(groupId.value);
  } catch (error) {
    console.error('Failed to resume group:', error);
  }
}

async function onProcessUnread(memberChatId: string) {
  if (!groupId.value) return;
  try {
    await groupStore.processUnread(groupId.value, memberChatId);
  } catch (error) {
    console.error('Failed to process unread:', error);
  }
}

function onOpenSubSession(memberChatId: string) {
  router.push(`/chat/${memberChatId}`);
}
</script>

<style scoped>
.group-window {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px 16px;
  box-sizing: border-box;
  gap: 12px;
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
</style>
