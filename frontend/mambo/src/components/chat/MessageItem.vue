<template>
  <div
    class="message-item-container"
    :class="roleClass"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <!-- 头像 -->
    <div class="message-avatar">
      <el-avatar>
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <!-- 消息主体 (现在是子消息的容器) -->
    <div class="message-body">
      <!-- 循环渲染每个子消息分区 -->
      <SubMessageItem
        v-for="subMessage in message.sub_messages"
        :key="subMessage.id"
        :sub-message="subMessage"
        :parent-message="message"
      />

      <!-- 针对整个消息的悬浮操作菜单 -->
      <div
        class="message-actions"
        :class="{ 'is-visible': showActions && !isGenerating }"
      >
        <!-- AI消息: 重新回答 -->
        <el-tooltip content="重新回答" placement="top" :show-after="500">
          <el-button
            v-if="message.role === 'assistant'"
            :icon="Refresh"
            circle
            size="small"
            @click="handleRegenerate"
          />
        </el-tooltip>
        <!-- 用户消息: 在下方重新回答 -->
        <el-tooltip content="在下方重新回答" placement="top" :show-after="500">
          <el-button
            v-if="message.role === 'user'"
            :icon="RefreshLeft"
            circle
            size="small"
            @click="handleRegenerate"
          />
        </el-tooltip>

        <!-- 删除整个消息 -->
        <el-tooltip content="删除" placement="top" :show-after="500">
          <el-button
            :icon="Delete"
            circle
            size="small"
            type="danger"
            plain
            @click="handleDelete"
          />
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { Message } from '@/api/types';
import { useChatStore } from '@/stores/chatStore';
import { ElMessageBox } from 'element-plus';
import { User, Cpu, Refresh, RefreshLeft, Delete } from '@element-plus/icons-vue';
import SubMessageItem from './SubMessageItem.vue';

const props = defineProps<{
  message: Message;
  isLastMessage: boolean;
}>();

const chatStore = useChatStore();
const showActions = ref(false);

const isGenerating = computed(
  () => props.message.role === 'assistant' && props.message.status === 'generating'
);

const handleRegenerate = () => {
  chatStore.regenerateFrom(props.message.id);
};

const handleDelete = () => {
  ElMessageBox.confirm('确定要删除这条消息吗？（包含所有分区）', '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(() => {
      chatStore.deleteMessage(props.message.id);
    })
    .catch(() => {});
};

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}));
</script>

<style scoped>
.message-item-container {
  display: flex;
  align-items: flex-start;
  margin-bottom: 20px;
  max-width: 90%;
}

.message-avatar {
  flex-shrink: 0;
  margin-right: 12px;
  margin-top: 2px;
}

.message-body {
  display: flex;
  flex-direction: column;
  gap: 4px; /* 子消息之间的间距 */
  min-width: 80px;
  width: 100%;
}

.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  opacity: 0;
  visibility: hidden;
  height: 24px;
  transition: opacity 0.2s, visibility 0.2s;
}
.message-actions.is-visible {
  opacity: 1;
  visibility: visible;
}

/* -- 用户消息样式 -- */
.is-user {
  flex-direction: row-reverse;
  margin-left: auto;
}
.is-user .message-avatar {
  margin-right: 0;
  margin-left: 12px;
}

.is-user .message-body {
  align-items: flex-end;
}
.is-assistant .message-body {
  align-items: flex-start;
}
</style>
