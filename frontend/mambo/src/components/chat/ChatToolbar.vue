<template>
  <div class="chat-toolbar">
    <div class="toolbar-left">
      <div class="model-display">
        <el-icon><Cpu /></el-icon>
        <span>当前模型: <strong>{{ displayModelName }}</strong></span>
      </div>
      <div class="token-counter" v-if="estimatedTokens > 0">
        <el-icon><Tickets /></el-icon>
        <span>预估 Tokens: <strong>{{ estimatedTokens }}</strong></span>
      </div>
    </div>
    <div class="actions">
      <el-button
        :icon="Files"
        circle
        title="聊天分区"
        @click="$emit('toggleMultiPartMode')"
      />
      <el-button
        :icon="Setting"
        circle
        title="会话设置"
        @click="$emit('openSettings')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useProviderStore } from '@/stores/providerStore';
import type { Chat } from '@/api/types';
import type { PropType } from 'vue';
import { Cpu, Setting, Files, Tickets } from '@element-plus/icons-vue';

const props = defineProps({
  currentChat: {
    type: Object as PropType<Chat>,
    required: true,
  },
  estimatedTokens: {
    type: Number,
    default: 0,
  },
});

defineEmits(['openSettings', 'toggleMultiPartMode']);

const providerStore = useProviderStore();

const displayModelName = computed(() => {
  if (!props.currentChat?.aiModelId) {
    return '未指定';
  }
  const model = providerStore.allModels.find(m => m.id === props.currentChat.aiModelId);
  return model ? model.name : '未知模型';
});
</script>

<style scoped>
.chat-toolbar {
  flex-shrink: 0;
  padding: 8px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--color-border);
  background-color: var(--color-background-soft);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 24px;
}

.model-display,
.token-counter {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.model-display .el-icon,
.token-counter .el-icon {
  margin-right: 8px;
}

.model-display strong,
.token-counter strong {
  color: var(--el-text-color-primary);
  font-weight: 600;
  margin-left: 4px;
}

.actions {
  display: flex;
  gap: 8px;
}
</style>
