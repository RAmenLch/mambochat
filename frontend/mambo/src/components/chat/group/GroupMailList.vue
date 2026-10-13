<!-- frontend/mambo/src/components/chat/group/GroupMailList.vue -->
<template>
  <div class="group-mail-list">
    <div v-if="!mails.length" class="empty">{{ $t('groupChat.window.empty') }}</div>
    <div v-for="mail in mails" :key="mail.id" class="mail-card">
      <div class="mail-head">
        <div class="mail-title">{{ mail.title || $t('groupChat.mail.noTitle') }}</div>
        <div class="mail-seq">#{{ mail.sequence ?? '-' }}</div>
      </div>
      <div class="mail-meta">
        <span class="label">{{ $t('groupChat.mail.from') }}:</span>
        <span class="sender">{{ mail.senderAliasSnapshot }}</span>
      </div>
      <div class="mail-meta">
        <span class="label">{{ $t('groupChat.mail.to') }}:</span>
        <span class="recipients">
          {{ (mail.recipientSnapshot || []).map((r) => r.memberName).join('，') }}
        </span>
      </div>
      <div class="mail-content">{{ mail.content }}</div>
    </div>
    <div v-if="hasMore" class="load-more">
      <el-button text :loading="loading" @click="emit('load-more')">
        {{ $t('groupChat.window.loadMore') }}
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { GroupMail } from '@/api/types/groupChatTypes';

defineProps<{
  mails: GroupMail[];
  loading?: boolean;
  hasMore?: boolean;
}>();

const emit = defineEmits<{ (e: 'load-more'): void }>();
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
</style>
