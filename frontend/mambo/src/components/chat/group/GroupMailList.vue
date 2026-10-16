<!-- frontend/mambo/src/components/chat/group/GroupMailList.vue -->
<template>
  <div class="group-mail-list">
    <div v-if="!mails.length" class="empty">{{ emptyText || $t('groupChat.window.empty') }}</div>
    <div v-for="mail in mails" :key="mail.id" class="mail-card">
      <div class="mail-head">
        <div class="mail-title">{{ mail.title || $t('groupChat.mail.noTitle') }}</div>
        <div class="mail-seq">#{{ mail.sequence ?? '-' }}</div>
      </div>
      <div class="mail-meta">
        <span class="label">{{ $t('groupChat.mail.from') }}:</span>
        <span class="sender">{{ displayName(mail.senderAliasSnapshot) }}</span>
      </div>
      <div class="mail-meta">
        <span class="label">{{ $t('groupChat.mail.to') }}:</span>
        <span class="recipients">
          {{ (mail.recipientSnapshot || []).map((r) => displayName(r.memberName)).join('，') }}
        </span>
      </div>
      <div class="mail-content">{{ mail.content }}</div>
      <div v-if="isRoundLast(mail)" class="mail-actions">
        <el-tooltip :content="$t('groupChat.duplicate.tooltip')" placement="top" :show-after="500">
          <el-button
            size="small"
            :icon="DocumentCopy"
            :disabled="duplicateDisabled"
            @click="emit('duplicate-upto', mail.id)"
          >
            {{ $t('groupChat.duplicate.button') }}
          </el-button>
        </el-tooltip>
      </div>
    </div>
    <div v-if="hasMore" class="load-more">
      <el-button text :loading="loading" @click="emit('load-more')">
        {{ $t('groupChat.window.loadMore') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { DocumentCopy } from '@element-plus/icons-vue';
import type { GroupMail } from '@/api/types/groupChatTypes';
import { MASTER_MEMBER_ALIAS } from '@/api/types/groupChatTypes';

const { t } = useI18n();

/** Master 别名在展示层标注为「用户」，避免用户对其身份产生疑惑 */
function displayName(name?: string | null): string {
  const value = name ?? '';
  return value === MASTER_MEMBER_ALIAS
    ? `${value}（${t('groupChat.member.userTag')}）`
    : value;
}

const props = defineProps<{
  mails: GroupMail[];
  loading?: boolean;
  hasMore?: boolean;
  /** 空列表提示文案（默认「还没有已发送的邮件」；筛选无结果时由父组件传入） */
  emptyText?: string;
  /** 群非空闲（有成员在处理）时禁用复制按钮 */
  duplicateDisabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'load-more'): void;
  (e: 'duplicate-upto', mailId: string): void;
}>();

/**
 * 每轮只在其最后一封邮件下展示复制按钮。
 * 同一轮（sourceTaskId 相同）的邮件在列表中按 sequence 相邻，
 * 末封即该 sourceTaskId 最后一次出现的邮件；Master 来信各自独立成轮。
 */
const lastMailIdByRound = computed(() => {
  const map = new Map<string, string>();
  for (const m of props.mails) map.set(m.sourceTaskId, m.id);
  return map;
});

function isRoundLast(mail: GroupMail): boolean {
  return lastMailIdByRound.value.get(mail.sourceTaskId) === mail.id;
}
</script>

<style scoped>
.group-mail-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.empty {
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 24px 0;
}
.mail-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-bg-color);
}
.mail-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.mail-title {
  font-weight: 600;
}
.mail-seq {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.mail-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 2px;
}
.mail-meta .label {
  margin-right: 4px;
}
.mail-content {
  margin-top: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
}
.load-more {
  text-align: center;
}
.mail-actions {
  margin-top: 8px;
  text-align: right;
}
</style>
