<template>
  <div class="chat-window-container">
    <!-- 当没有选中会话时，显示欢迎/引导界面 -->
    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <!-- 当选中会-话后，显示聊天界面 -->
    <template v-else>
      <!-- 1. 顶部标题栏 -->
      <div class="chat-window-header">
        <h3 class="chat-title">{{ currentChat.name }}</h3>
      </div>

      <!-- 2. 消息列表区域 -->
      <el-scrollbar ref="scrollbarRef" class="message-list-scrollbar" v-loading="isChatHistoryLoading">
        <div class="message-list-wrapper">
          <MessageItem
            v-for="message in currentChatMessages"
            :key="message.id"
            :message="message"
          />
        </div>
      </el-scrollbar>

      <!-- 3. 底部输入区域 -->
      <div class="chat-input-area">
        <!-- 【修复】: 将注释移到标签外部 -->
        <el-input
          ref="inputRef"
          v-model="userInput"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入消息... (Shift + Enter 换行)"
          :disabled="isGenerating"
          @keydown.enter.prevent="handleEnterKey"
        />
        <el-button
          type="primary"
          class="send-button"
          :disabled="isGenerating || userInput.trim() === ''"
          @click="handleSendMessage"
        >
          <el-icon><Promotion /></el-icon>
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { useChatStore } from '@/stores/chatStore';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElInput } from 'element-plus';
import { Promotion } from '@element-plus/icons-vue';
import MessageItem from './MessageItem.vue';

const chatStore = useChatStore();
const {
  currentChat,
  currentChatMessages,
  isChatHistoryLoading,
  isGenerating
} = storeToRefs(chatStore);

const userInput = ref('');
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const inputRef = ref<InstanceType<typeof ElInput>>();

const handleSendMessage = async () => {
  if (userInput.value.trim() === '' || isGenerating.value) return;
  const content = userInput.value;
  userInput.value = '';
  await chatStore.sendMessage(content);
};

const handleEnterKey = (event: KeyboardEvent) => {
  if (event.shiftKey) {
    return;
  }
  handleSendMessage();
};

const scrollToBottom = () => {
  nextTick(() => {
    scrollbarRef.value?.setScrollTop(scrollbarRef.value.wrapRef!.scrollHeight);
  });
};

watch(currentChatMessages, () => {
  scrollToBottom();
}, { deep: true });

watch(
  () => currentChat.value?.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      const unwatch = watch(isChatHistoryLoading, (isLoading) => {
        if (!isLoading) {
          scrollToBottom();
          unwatch();
        }
      });
      nextTick(() => inputRef.value?.focus());
    }
  }
);
</script>

<style scoped>
/* (样式部分保持不变) */
.chat-window-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
}
.welcome-view {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100%;
}
.chat-window-header {
  flex-shrink: 0;
  padding: 0 20px;
  height: 60px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border);
}
.chat-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--color-heading);
}
.message-list-scrollbar {
  flex-grow: 1;
}
.message-list-wrapper {
  padding: 20px;
}
.chat-input-area {
  flex-shrink: 0;
  padding: 10px 20px;
  border-top: 1px solid var(--color-border);
  background-color: var(--color-background-soft);
  display: flex;
  align-items: flex-end;
}
.chat-input-area .el-textarea {
  margin-right: 10px;
}
.send-button {
  height: 54px;
  width: 54px;
  font-size: 20px;
}
</style>
