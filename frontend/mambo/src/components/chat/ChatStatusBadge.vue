<!-- frontend/mambo/src/components/chat/ChatStatusBadge.vue -->
<template>
  <el-tooltip v-if="kind" :content="label" placement="right" :show-after="300">
    <span class="chat-status-badge" :class="`is-${kind}`" role="status" :aria-label="label">
      <span class="shape" />
    </span>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ChatStatusFlags } from '@/api/types';

const props = defineProps<{
  status?: ChatStatusFlags;
}>();

const { t } = useI18n();

// 显示优先级：中断(待审核) > 生成中 > 未读
const kind = computed<'review' | 'generating' | 'unread' | null>(() => {
  const s = props.status;
  if (!s) return null;
  if (s.pendingReview) return 'review';
  if (s.generating) return 'generating';
  if (s.unread) return 'unread';
  return null;
});

const label = computed(() => {
  if (kind.value === 'review') return t('chat.sidebar.status.pendingReview');
  if (kind.value === 'generating') return t('chat.sidebar.status.generating');
  return t('chat.sidebar.status.unread');
});
</script>

<style scoped>
.chat-status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

.shape {
  display: block;
  box-sizing: border-box;
}

/* 未读：实心圆点 */
.is-unread .shape {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background-color: var(--el-color-primary);
}

/* 生成中：呼吸圆环 */
.is-generating .shape {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 2px solid var(--el-color-primary);
  background-color: transparent;
  animation: chat-status-pulse 1.2s ease-in-out infinite;
}

/* 中断（待审核 / 待回答）：三角 */
.is-review .shape {
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 8px solid var(--el-color-warning);
}

@keyframes chat-status-pulse {
  0%,
  100% {
    transform: scale(0.7);
    opacity: 0.45;
  }
  50% {
    transform: scale(1);
    opacity: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .is-generating .shape {
    animation: none;
    opacity: 1;
  }
}
</style>
