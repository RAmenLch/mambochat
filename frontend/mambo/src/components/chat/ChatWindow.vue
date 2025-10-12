<template>
  <div class="chat-window-container">
    <!-- 当没有选中会话时，显示欢迎/引导界面 -->
    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <!-- 当选中会话后，显示聊天界面 -->
    <template v-else>
      <!-- 1. 顶部标题栏 -->
      <div class="chat-window-header">
        <h3 class="chat-title">{{ currentChat.name }}</h3>
      </div>

      <!-- 2. 消息列表区域 -->
      <el-scrollbar
        ref="scrollbarRef"
        class="message-list-scrollbar"
        v-loading="isChatHistoryLoading"
      >
        <div class="message-list-wrapper">
          <MessageItem
            v-for="(message, index) in currentChatMessages"
            :key="message.id"
            :message="message"
            :is-last-message="index === currentChatMessages.length - 1"
            :is-generating="isGenerating"
          />
        </div>
      </el-scrollbar>

      <!-- 3. 中部工具栏 -->
      <ChatToolbar
        v-if="currentChat"
        :current-chat="currentChat"
        @open-settings="openSettingsDrawer"
      />

      <!-- 4. 底部输入区域 -->
      <div class="chat-input-area">
        <el-input
          ref="inputRef"
          v-model="userInput"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="输入消息... (Shift + Enter 换行)"
          :disabled="isGenerating"
          @keydown.enter="handleEnterKey"
        />
        <el-button
          v-if="!isGenerating"
          type="primary"
          class="action-button"
          :disabled="userInput.trim() === ''"
          @click="handleSendMessage"
        >
          <el-icon><Promotion /></el-icon>
        </el-button>
        <el-button
          v-else
          type="warning"
          class="action-button"
          @click="chatStore.stopGeneration()"
        >
          <el-icon><VideoPause /></el-icon>
        </el-button>
      </div>
    </template>

    <!-- 会话设置抽屉 -->
    <el-drawer
      v-model="settingsDrawerVisible"
      title="会话设置"
      direction="rtl"
      size="450px"
    >
      <div class="drawer-content">
        <el-form :model="chatSettingsForm" label-position="top">
          <el-form-item label="会话名称">
            <el-input
              v-model="chatSettingsForm.name"
              placeholder="请输入会话名称"
            />
          </el-form-item>
          <el-form-item label="AI 模型">
            <el-select
              v-model="chatSettingsForm.aiModelId"
              placeholder="请选择一个AI模型"
              style="width: 100%"
            >
              <el-option-group
                v-for="group in groupedModels"
                :key="group.label"
                :label="group.label"
              >
                <el-option
                  v-for="item in group.options"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id"
                />
              </el-option-group>
            </el-select>
          </el-form-item>
          <el-form-item label="System Prompt (系统提示词)">
            <el-input
              v-model="chatSettingsForm.systemPrompt"
              type="textarea"
              :rows="8"
              placeholder="定义AI的角色和行为"
            />
          </el-form-item>
          <el-divider>模型参数</el-divider>
          <el-form-item>
            <template #label>
              <span>上下文消息数量 (Context)</span>
              <el-tooltip
                effect="dark"
                content="每次请求时携带的最近历史消息数量。0 代表不限制（发送全部历史）。"
                placement="top"
              >
                <el-icon style="margin-left: 8px; color: #909399;"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input-number
              v-model="chatSettingsForm.modelParameters.max_context_messages"
              :min="0"
              :step="2"
              controls-position="right"
              style="width: 100%;"
            />
          </el-form-item>
          <el-form-item label="Temperature (温度)">
            <el-slider
              v-model="chatSettingsForm.modelParameters.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              show-input
            />
          </el-form-item>
          <el-form-item label="Top P">
            <el-slider
              v-model="chatSettingsForm.modelParameters.top_p"
              :min="0"
              :max="1"
              :step="0.01"
              show-input
            />
          </el-form-item>
          <el-form-item label="流式对话 (Stream)">
             <el-switch v-model="chatSettingsForm.modelParameters.stream" />
             <el-tooltip
                class="box-item"
                effect="dark"
                content="关闭后, AI将一次性返回完整回复, 可能会增加等待时间。"
                placement="top"
              >
                <el-icon style="margin-left: 8px; color: #909399;"><QuestionFilled /></el-icon>
              </el-tooltip>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <div style="flex: auto">
          <el-button @click="settingsDrawerVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSaveSettings"
            >保存</el-button
          >
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, reactive, computed } from 'vue';
import { useChatStore } from '@/stores/chatStore';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElInput, ElMessage } from 'element-plus';
import { Promotion, VideoPause, QuestionFilled } from '@element-plus/icons-vue';
import MessageItem from './MessageItem.vue';
import ChatToolbar from './ChatToolbar.vue';
import type { ChatUpdate } from '@/api/types';

interface ChatSettingsForm extends ChatUpdate {
  name: string | null;
  modelParameters: {
    temperature: number;
    top_p: number;
    stream: boolean;
    max_context_messages: number;
  };
}

const chatStore = useChatStore();
const providerStore = useProviderStore();

const {
  currentChat,
  currentChatId,
  currentChatMessages,
  isChatHistoryLoading,
  isGenerating,
  userInputCache,
} = storeToRefs(chatStore);
const { providers } = storeToRefs(providerStore);

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const inputRef = ref<InstanceType<typeof ElInput>>();

// --- Input Caching Logic ---
const userInput = computed({
  get: () => currentChatId.value ? (userInputCache.value[currentChatId.value] || '') : '',
  set: (value) => {
    if (currentChatId.value) {
      chatStore.saveDraft(value);
    }
  }
});

// --- Settings Drawer Logic ---
const settingsDrawerVisible = ref(false);
const chatSettingsForm = reactive<ChatSettingsForm>({
  name: '',
  aiModelId: null,
  systemPrompt: null,
  modelParameters: { temperature: 0.7, top_p: 0.9, stream: true, max_context_messages: 0 },
});

const groupedModels = computed(() => providers.value.map(p => ({ label: p.name, options: p.models })));

const openSettingsDrawer = () => {
  if (!currentChat.value) return;
  chatSettingsForm.name = currentChat.value.name;
  chatSettingsForm.aiModelId = currentChat.value.aiModelId;
  chatSettingsForm.systemPrompt = currentChat.value.systemPrompt;
  const params = currentChat.value.modelParameters;
  chatSettingsForm.modelParameters.temperature = params?.temperature ?? 0.7;
  chatSettingsForm.modelParameters.top_p = params?.top_p ?? 0.9;
  chatSettingsForm.modelParameters.stream = params?.stream ?? true;
  chatSettingsForm.modelParameters.max_context_messages = params?.max_context_messages ?? 0;
  settingsDrawerVisible.value = true;
};

const handleSaveSettings = async () => {
  if (!currentChat.value) {
    ElMessage.error('没有活动的会话，无法保存设置。');
    return;
  }
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning('会话名称不能为空');
    return;
  }

  // --- 核心修正 ---
  // 调用 store action 时，必须传入当前会话的 ID
  await chatStore.updateChatSettings(currentChat.value.id, {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: chatSettingsForm.modelParameters,
  });

  settingsDrawerVisible.value = false;
  ElMessage.success('设置已保存');
};

// --- Message Sending Logic ---
const handleSendMessage = async () => {
  if (userInput.value.trim() === '' || isGenerating.value) return;
  const content = userInput.value;
  // The store action will handle clearing the cache, so we don't clear it here.
  await chatStore.sendMessage(content);
};

const handleEnterKey = (event: Event) => {
  // 使用类型守卫确保事件是 KeyboardEvent
  if (!(event instanceof KeyboardEvent)) return;

  if (event.shiftKey) {
    // 当 Shift 被按下时，允许默认的换行行为
    return;
  }
  // 否则，阻止默认的换行行为，并发送消息
  event.preventDefault();
  handleSendMessage();
};

// --- Auto-Scrolling and Focus ---
const scrollToBottom = () => {
  nextTick(() => {
    scrollbarRef.value?.setScrollTop(scrollbarRef.value.wrapRef!.scrollHeight);
  });
};

watch(currentChatMessages, scrollToBottom, { deep: true });

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
.action-button {
  height: 54px;
  width: 54px;
  font-size: 20px;
}
.drawer-content {
  padding: 0 20px;
}
.el-form-item .el-switch {
  margin-right: 8px;
}
</style>
