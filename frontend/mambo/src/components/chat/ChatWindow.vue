<template>
  <div class="chat-window-container">
    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <template v-else>
      <div class="chat-window-header">
        <h3 class="chat-title">{{ currentChat.name }}</h3>
      </div>

      <el-scrollbar
        ref="scrollbarRef"
        class="message-list-scrollbar"
        v-loading="isChatHistoryLoading"
        @scroll="handleScroll"
      >
        <div class="message-list-wrapper">
          <MessageItem
            v-for="(message, index) in currentChatMessages"
            :key="message.id"
            :message="message"
            :is-last-message="index === currentChatMessages.length - 1"
          />
        </div>
      </el-scrollbar>

      <div class="input-container-wrapper" :style="{ height: `${inputAreaHeight}px` }">
        <div class="resize-handle" @mousedown.prevent="startResize"></div>
        <ChatToolbar
          :current-chat="currentChat"
          :estimated-tokens="estimatedTokens"
          @open-settings="openSettingsDrawer"
          @toggle-multi-part-mode="handleToggleMultiPartMode"
        />
        <div class="chat-input-area" @keydown="handleGlobalKeydown">
          <MultiPartInput
            v-if="isMultiPartMode"
            ref="multiPartInputRef"
            v-model="multiPartDraft"
            class="input-field"
            @send="handleSendMessage"
          />
          <el-input
            v-else
            ref="inputRef"
            v-model="localUserInput"
            type="textarea"
            :autosize="false"
            resize="none"
            placeholder="输入消息... (Shift + Enter 换行)"
            :disabled="isGenerating"
            @keydown="handleSingleInputKeydown"
            class="input-field"
          />
          <el-button
            v-if="!isGenerating"
            type="primary"
            class="action-button"
            :disabled="isSendButtonDisabled"
            @click="handleSendMessage"
          >
            <el-icon><Promotion /></el-icon>
          </el-button>
          <el-button
            v-else
            type="warning"
            class="action-button"
            @click="handleStopGeneration"
          >
            <el-icon><VideoPause /></el-icon>
          </el-button>
        </div>
      </div>
    </template>

    <el-drawer
      v-model="settingsDrawerVisible"
      title="会话设置"
      direction="rtl"
      size="450px"
    >
      <div class="drawer-content">
        <el-form :model="chatSettingsForm" label-position="top">
          <el-form-item label="会话名称">
            <el-input v-model="chatSettingsForm.name" placeholder="请输入会话名称" />
          </el-form-item>
          <el-form-item label="AI 模型">
            <el-select v-model="chatSettingsForm.aiModelId" placeholder="请选择一个AI模型" style="width: 100%">
              <el-option-group v-for="group in groupedModels" :key="group.label" :label="group.label">
                <el-option v-for="item in group.options" :key="item.id" :label="item.name" :value="item.id" />
              </el-option-group>
            </el-select>
          </el-form-item>
          <el-form-item label="System Prompt (系统提示词)">
            <el-input v-model="chatSettingsForm.systemPrompt" type="textarea" :rows="8" placeholder="定义AI的角色和行为" />
          </el-form-item>
          <el-divider>模型参数</el-divider>
          <el-form-item>
            <template #label>
              <span>上下文消息数量 (Context)</span>
              <el-tooltip effect="dark" content="每次请求时携带的最近历史消息数量。0 代表不限制（发送全部历史）。" placement="top">
                <el-icon style="margin-left: 8px; color: #909399;"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <el-input-number v-model="chatSettingsForm.modelParameters.max_context_messages" :min="0" :step="2" controls-position="right" style="width: 100%;" />
          </el-form-item>
          <el-form-item label="Temperature (温度)">
            <el-slider v-model="chatSettingsForm.modelParameters.temperature" :min="0" :max="2" :step="0.1" show-input />
          </el-form-item>
          <el-form-item label="Top P">
            <el-slider v-model="chatSettingsForm.modelParameters.top_p" :min="0" :max="1" :step="0.01" show-input />
          </el-form-item>
          <el-form-item label="流式对话 (Stream)">
             <el-switch v-model="chatSettingsForm.modelParameters.stream" />
             <el-tooltip class="box-item" effect="dark" content="关闭后, AI将一次性返回完整回复, 可能会增加等待时间。" placement="top">
                <el-icon style="margin-left: 8px; color: #909399;"><QuestionFilled /></el-icon>
              </el-tooltip>
          </el-form-item>
        </el-form>
      </div>
      <template #footer>
        <div style="flex: auto">
          <el-button @click="settingsDrawerVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSaveSettings">保存</el-button>
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
import MultiPartInput from './MultiPartInput.vue';
import type { ChatUpdate } from '@/api/types';
import { debounce } from 'lodash-es';
import { encode } from 'gpt-tokenizer';

// --- 类型定义 ---
interface ChatSettingsForm extends ChatUpdate {
  name: string | null;
  modelParameters: {
    temperature: number;
    top_p: number;
    stream: boolean;
    max_context_messages: number;
  };
}

interface Partition {
  id: number;
  content: string;
}

// --- Store 和 Refs ---
const chatStore = useChatStore();
const providerStore = useProviderStore();

const { currentChat, currentChatMessages, isChatHistoryLoading, isGenerating, currentDraft, contextForTokenEstimation } = storeToRefs(chatStore);
const { providers } = storeToRefs(providerStore);

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const inputRef = ref<InstanceType<typeof ElInput>>();
const multiPartInputRef = ref<InstanceType<typeof MultiPartInput>>();

const isMultiPartMode = ref(false);
const localUserInput = ref('');
const multiPartDraft = ref<Partition[]>([{ id: Date.now(), content: '' }]);

// 用于持久化每个会话的输入模式
const chatInputModeState = reactive<Record<string, boolean>>({});

// --- 响应式输入区高度 ---
const inputAreaHeight = ref(150);
const MIN_INPUT_HEIGHT = 100;
const MAX_INPUT_HEIGHT = 600;

// --- Token 估算 ---
const estimatedTokens = ref(0);
const debouncedEstimateTokens = debounce((currentUserInputText: string) => {
  const fullText = [contextForTokenEstimation.value, currentUserInputText].filter(Boolean).join('\n');
  if (!fullText) {
    estimatedTokens.value = 0;
    return;
  }
  try {
    estimatedTokens.value = encode(fullText).length;
  } catch (e) {
    console.error("Token estimation failed:", e);
    estimatedTokens.value = 0;
  }
}, 500);

// --- 输入区草稿管理 (Undo/Redo & 双向同步) ---
const debouncedSaveSingleDraft = debounce((content: string) => {
  chatStore.saveDraft(content);
}, 300);

const debouncedSaveMultiPartDraft = debounce((partitions: Partition[]) => {
  const jsonString = JSON.stringify(partitions);
  chatStore.saveDraft(jsonString);
}, 300);


watch(currentDraft, (newDraft) => {
  if (isMultiPartMode.value) {
    try {
      const parsedPartitions: Partition[] = JSON.parse(newDraft);
      if (JSON.stringify(parsedPartitions) !== JSON.stringify(multiPartDraft.value)) {
        multiPartDraft.value = parsedPartitions;
      }
    } catch (e) {
      multiPartDraft.value = [{ id: Date.now(), content: '' }];
    }
  } else {
    if (localUserInput.value !== newDraft) {
      localUserInput.value = newDraft;
    }
  }
});

watch(localUserInput, (newInput) => {
  if (isMultiPartMode.value) return;
  debouncedSaveSingleDraft(newInput);
  debouncedEstimateTokens(newInput);
});

watch(multiPartDraft, (newPartitions) => {
  if (!isMultiPartMode.value) return;
  debouncedSaveMultiPartDraft(newPartitions);
  const allContent = newPartitions.map(p => p.content).join('\n');
  debouncedEstimateTokens(allContent);
}, { deep: true });

// --- 按钮与发送逻辑 ---
const isSendButtonDisabled = computed(() => {
  if (isGenerating.value) return true;
  if (isMultiPartMode.value) {
    return !multiPartDraft.value.some(p => p.content.trim() !== '');
  }
  return localUserInput.value.trim() === '';
});

const handleSendMessage = async () => {
  if (isSendButtonDisabled.value) return;

  if (isMultiPartMode.value) {
    const subMessages = multiPartInputRef.value?.getData();
    if (subMessages && subMessages.length > 0) {
      await chatStore.sendMessage(subMessages);
      multiPartInputRef.value?.reset();
    }
  } else {
    const content = localUserInput.value;
    await chatStore.sendMessage([{ content, sortOrder: 0 }]);
    localUserInput.value = '';
  }
};

// --- 输入模式切换与数据转换 ---
const handleToggleMultiPartMode = () => {
  if (!currentChat.value) return;
  const chatId = currentChat.value.id;
  const nextMode = !isMultiPartMode.value;

  if (nextMode) { // 切换到多分区
    multiPartDraft.value = [{ id: Date.now(), content: localUserInput.value }];
  } else { // 切换到单行
    localUserInput.value = multiPartDraft.value
      .map(p => p.content)
      .join('\n--------------------------\n');
  }

  isMultiPartMode.value = nextMode;
  chatInputModeState[chatId] = nextMode;

  // 切换后，立即为新模式保存一次草稿
  if (nextMode) {
    debouncedSaveMultiPartDraft(multiPartDraft.value);
  } else {
    debouncedSaveSingleDraft(localUserInput.value);
  }
};

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
  if (!currentChat.value) return;
  if (!chatSettingsForm.name?.trim()) {
    ElMessage.warning('会话名称不能为空');
    return;
  }
  await chatStore.updateChatSettings(currentChat.value.id, {
    name: chatSettingsForm.name,
    aiModelId: chatSettingsForm.aiModelId,
    systemPrompt: chatSettingsForm.systemPrompt,
    modelParameters: chatSettingsForm.modelParameters,
  });
  settingsDrawerVisible.value = false;
  ElMessage.success('设置已保存');
};


// --- 其他交互逻辑 ---
const handleStopGeneration = () => {
  const generatingMessage = currentChatMessages.value.find(m =>
    m.sub_messages.some(sm => sm.status === 'generating')
  );
  if (generatingMessage) {
    chatStore.cancelGeneration(generatingMessage.id);
  }
};

const handleGlobalKeydown = (event: KeyboardEvent) => {
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    chatStore.undo();
  } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    chatStore.redo();
  }
};

const handleSingleInputKeydown = (event: KeyboardEvent | Event) => {
  if (!(event instanceof KeyboardEvent)) return;
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSendMessage();
  }
};

const startResize = (event: MouseEvent) => {
  const startY = event.clientY;
  const startHeight = inputAreaHeight.value;
  const doResize = (e: MouseEvent) => {
    const deltaY = startY - e.clientY;
    const newHeight = startHeight + deltaY;
    inputAreaHeight.value = Math.max(MIN_INPUT_HEIGHT, Math.min(newHeight, MAX_INPUT_HEIGHT));
  };
  const stopResize = () => {
    window.removeEventListener('mousemove', doResize);
    window.removeEventListener('mouseup', stopResize);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  };
  window.addEventListener('mousemove', doResize);
  window.addEventListener('mouseup', stopResize);
  document.body.style.cursor = 'ns-resize';
  document.body.style.userSelect = 'none';
};

// --- Auto-Scrolling and Focus ---
const userHasScrolledUp = ref(false);

const handleScroll = ({ scrollTop }: { scrollTop: number }) => {
  const scrollWrapper = scrollbarRef.value?.wrapRef;
  if (!scrollWrapper) return;
  const { scrollHeight, clientHeight } = scrollWrapper;
  const isAtBottom = scrollHeight - clientHeight - scrollTop < 20;
  userHasScrolledUp.value = !isAtBottom;
};

const scrollToBottom = (force = false) => {
  if (!force && userHasScrolledUp.value && isGenerating.value) return;
  nextTick(() => {
    scrollbarRef.value?.setScrollTop(scrollbarRef.value.wrapRef!.scrollHeight);
  });
};

watch(() => {
    const lastMsg = currentChatMessages.value[currentChatMessages.value.length - 1];
    const lastSubMsg = lastMsg?.sub_messages[lastMsg.sub_messages.length - 1];
    return lastSubMsg?.content;
  },
  () => scrollToBottom()
);

// 切换会话时，加载对应的草稿和输入模式
watch(() => currentChat.value?.id, (newId, oldId) => {
    if (newId && newId !== oldId) {
      userHasScrolledUp.value = false;

      // 恢复该会话的输入模式，默认为 false (单行)
      isMultiPartMode.value = chatInputModeState[newId] ?? false;

      // 根据恢复的模式，加载和解析草稿
      if (isMultiPartMode.value) {
        try {
          const parsed = JSON.parse(currentDraft.value);
          multiPartDraft.value = Array.isArray(parsed) && parsed.length > 0 ? parsed : [{ id: Date.now(), content: '' }];
        } catch {
          multiPartDraft.value = [{ id: Date.now(), content: '' }];
        }
      } else {
        localUserInput.value = currentDraft.value;
      }

      // 滚动到底部并聚焦
      const unwatch = watch(isChatHistoryLoading, (isLoading) => {
        if (!isLoading) {
          scrollToBottom(true);
          unwatch();
        }
      });
      nextTick(() => {
        if (isMultiPartMode.value) {
          // 在多分区模式下，可能需要主动聚焦子组件的输入框
        } else {
          inputRef.value?.focus();
        }
      });
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
  overflow: hidden;
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
.input-container-wrapper {
  flex-shrink: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--color-border);
}
.resize-handle {
  position: absolute;
  top: -3px;
  left: 0;
  width: 100%;
  height: 6px;
  cursor: ns-resize;
  z-index: 10;
}
.chat-input-area {
  flex-grow: 1;
  padding: 10px 20px;
  background-color: var(--color-background-soft);
  display: flex;
  align-items: stretch;
  min-height: 0;
}
.input-field {
  flex-grow: 1;
  margin-right: 10px;
}
.input-field:deep(.el-textarea__inner) {
  height: 100% !important;
}
.action-button {
  width: 54px;
  font-size: 20px;
  flex-shrink: 0;
  align-self: flex-end;
  height: calc(100% - 2px);
}
.drawer-content {
  padding: 0 20px;
}
.el-form-item .el-switch {
  margin-right: 8px;
}
</style>
