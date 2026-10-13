<!-- frontend/mambo/src/components/chat/group/GroupMemberPanel.vue -->
<template>
  <div class="group-member-panel">
    <div class="panel-title">{{ $t('groupChat.member.title') }}</div>
    <div v-for="member in members" :key="member.chatId" class="member-item">
      <div class="member-main">
        <div class="member-alias">{{ member.memberAlias }}</div>
        <div class="member-agent">{{ member.agentName || member.name }}</div>
      </div>
      <div class="member-actions">
        <el-tag v-if="member.unreadCount > 0" size="small" type="warning">
          {{ $t('groupChat.member.unread') }} {{ member.unreadCount }}
        </el-tag>
        <el-tag v-if="member.pendingCount > 0" size="small" type="info">
          {{ $t('groupChat.member.pending') }} {{ member.pendingCount }}
        </el-tag>
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
        <el-tooltip :content="$t('groupChat.member.openSubSession')" placement="top">
          <el-button text size="small" @click="emit('open-sub-session', member.chatId)">
            <el-icon><Right /></el-icon>
          </el-button>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Message, Right } from '@element-plus/icons-vue';
import type { GroupMember } from '@/api/types/groupChatTypes';

defineProps<{ members: GroupMember[] }>();

const emit = defineEmits<{
  (e: 'open-sub-session', chatId: string): void;
  (e: 'process-unread', chatId: string): void;
}>();
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
