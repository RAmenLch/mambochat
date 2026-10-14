<!-- frontend/mambo/src/components/chat/group/GroupMemberPanel.vue -->
<template>
  <div class="group-member-panel">
    <div class="panel-title">{{ $t('groupChat.member.title') }}</div>
    <div
      v-for="member in members"
      :key="member.chatId"
      class="member-item"
      :class="{ 'is-active': !!activeTaskOf(member.chatId), 'is-waiting': isWaitingHuman(member.chatId) }"
    >
      <div class="member-main">
        <div class="member-alias">{{ member.memberAlias }}</div>
        <div class="member-agent">{{ member.agentName || member.name }}</div>
      </div>
      <div class="member-actions">
        <el-tag v-if="member.isUser" size="small" type="success" effect="plain">
          {{ $t('groupChat.member.userTag') }}
        </el-tag>
        <el-tag
          v-if="activeTaskOf(member.chatId)"
          size="small"
          :type="stateTagType(activeTaskOf(member.chatId)?.state)"
        >
          {{ $t(`groupChat.task.state.${activeTaskOf(member.chatId)?.state}`) }}
        </el-tag>
        <el-tag v-if="(queuedCounts?.[member.chatId] ?? 0) > 0" size="small" type="info">
          {{ $t('groupChat.member.pending') }} {{ queuedCounts?.[member.chatId] }}
        </el-tag>
        <el-tag v-if="member.unreadCount > 0" size="small" type="warning">
          {{ $t('groupChat.member.unread') }} {{ member.unreadCount }}
        </el-tag>
        <template v-if="!member.isUser">
          <el-tooltip :content="$t('groupChat.member.processUnread')" placement="top">
            <el-button
              text
              size="small"
              :disabled="member.unreadCount === 0"
              @click="emit('process-unread', member.chatId)"
            >
              <el-icon><Message /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip
            :content="
              isWaitingHuman(member.chatId)
                ? $t('groupChat.recovery.openSession')
                : $t('groupChat.member.openSubSession')
            "
            placement="top"
          >
            <el-button
              text
              size="small"
              :type="isWaitingHuman(member.chatId) ? 'warning' : 'default'"
              @click="emit('open-sub-session', member.chatId)"
            >
              <el-icon><Right /></el-icon>
            </el-button>
          </el-tooltip>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Message, Right } from '@element-plus/icons-vue';
import type { GroupMember, GroupTask } from '@/api/types/groupChatTypes';

const props = defineProps<{
  members: GroupMember[];
  /** 每个成员当前的非终态任务（执行中 / 等待工具审核 / 等待用户回答） */
  activeTasks?: Record<string, GroupTask>;
  /** 每个成员真正排队中的任务数（不含执行中与等待人工） */
  queuedCounts?: Record<string, number>;
}>();

const emit = defineEmits<{
  (e: 'open-sub-session', chatId: string): void;
  (e: 'process-unread', chatId: string): void;
}>();

function activeTaskOf(chatId: string): GroupTask | undefined {
  return props.activeTasks?.[chatId];
}

function stateTagType(state?: string): 'primary' | 'warning' | 'info' {
  if (state === 'running') return 'primary';
  if (state === 'waiting_review' || state === 'waiting_user') return 'warning';
  return 'info';
}

/** 需要人介入的等待状态：等待工具审核 / 等待用户回答 */
function isWaitingHuman(chatId: string): boolean {
  const state = activeTaskOf(chatId)?.state;
  return state === 'waiting_review' || state === 'waiting_user';
}
</script>

<style scoped>
.group-member-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.panel-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.member-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--el-fill-color-lighter);
}
/* 正在执行 */
.member-item.is-active {
  background: var(--el-color-primary-light-9);
}
/* 等待工具审核 / 等待用户回答：需要人工介入，高亮提示 */
.member-item.is-waiting {
  background: var(--el-color-warning-light-9);
  box-shadow: inset 0 0 0 1px var(--el-color-warning);
}
.member-alias {
  font-weight: 500;
}
.member-agent {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.member-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
