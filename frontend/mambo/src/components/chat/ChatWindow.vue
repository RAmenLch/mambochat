<template>
  <div class="chat-window-container">
    <div v-if="!currentChat" class="welcome-view">
      <el-empty description="请从左侧选择或新建一个会话开始聊天" />
    </div>

    <template v-else>
      <div class="chat-window-header">
        <h3 class="chat-title">{{ currentChat.name }}</h3>
      </div>

      <el-scrollbar ref="scrollbarRef" class="message-list-scrollbar" v-loading="isChatHistoryLoading" @scroll="handleScroll">
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
        <div class="resize-handle" @mousedown.prevent="startResizeInputArea"></div>
        <ChatToolbar
          :current-chat="currentChat"
          :estimated-tokens="estimatedTokens"
          @open-settings="settingsDrawerVisible = true"
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
            v-model="singlePartDraft"
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
          <el-button v-else type="warning" class="action-button" @click="handleStopGeneration">
            <el-icon><VideoPause /></el-icon>
          </el-button>
        </div>
      </div>
    </template>

    <ChatSettingsDrawer
      v-model:visible="settingsDrawerVisible"
      :chat-data="currentChat"
      :grouped-models="groupedModels"
      @save="handleSaveSettings"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed, reactive } from 'vue';
import { useChatStore } from '@/stores/chatStore';
import { useProviderStore } from '@/stores/providerStore';
import { storeToRefs } from 'pinia';
import { ElScrollbar, ElInput, ElMessage } from 'element-plus';
import { Promotion, VideoPause } from '@element-plus/icons-vue';
import MessageItem from './MessageItem.vue';
import ChatToolbar from './ChatToolbar.vue';
import MultiPartInput from './MultiPartInput.vue';
import ChatSettingsDrawer from './ChatSettingsDrawer.vue';
import { useResizablePanels } from '@/composables/useResizablePanels';
import { useTokenEstimator } from '@/composables/useTokenEstimator';
import type { ChatUpdate, SubMessageCreate, AIModel } from '@/api/types';
import { debounce } from 'lodash-es';

interface Partition { id: number; content: string; }
interface GroupedModels { label: string; options: AIModel[]; }

const chatStore = useChatStore();
const providerStore = useProviderStore();
const { currentChat, currentChatMessages, isChatHistoryLoading, isGenerating, currentDraft, contextForTokenEstimation } = storeToRefs(chatStore);
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]>};

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();
const inputRef = ref<InstanceType<typeof ElInput>>();
const multiPartInputRef = ref<InstanceType<typeof MultiPartInput>>();
const settingsDrawerVisible = ref(false);

const isMultiPartMode = ref(false);
const singlePartDraft = ref('');
const multiPartDraft = ref<Partition[]>([{ id: Date.now(), content: '' }]);
const chatInputModeState = reactive<Record<string, boolean>>({});

// --- Composables for UI logic ---
const inputAreaHeight = ref(150);
const { startResize: startResizeInputArea } = useResizablePanels(inputAreaHeight, {
  min: 100, max: 600, orientation: 'vertical', inverted: true
});

const currentUserInputText = computed(() => isMultiPartMode.value
  ? multiPartDraft.value.map(p => p.content).join('\n')
  : singlePartDraft.value
);
const { estimatedTokens } = useTokenEstimator(contextForTokenEstimation, currentUserInputText);

// --- Draft Management ---
const debouncedSaveDraft = debounce((content: string) => {
  chatStore.saveDraft(content);
}, 300);

watch(currentDraft, (newDraft) => {
  if (isMultiPartMode.value) {
    try {
      const parsed = JSON.parse(newDraft);
      if (Array.isArray(parsed) && JSON.stringify(parsed) !== JSON.stringify(multiPartDraft.value)) {
        multiPartDraft.value = parsed.length > 0 ? parsed : [{ id: Date.now(), content: '' }];
      }
    } catch { multiPartDraft.value = [{ id: Date.now(), content: '' }]; }
  } else {
    if (singlePartDraft.value !== newDraft) {
      singlePartDraft.value = newDraft;
    }
  }
});
watch(singlePartDraft, (newInput) => !isMultiPartMode.value && debouncedSaveDraft(newInput));
watch(multiPartDraft, (newPartitions) => isMultiPartMode.value && debouncedSaveDraft(JSON.stringify(newPartitions)), { deep: true });

// --- Send & Stop Logic ---
const isSendButtonDisabled = computed(() => isGenerating.value || currentUserInputText.value.trim() === '');

async function handleSendMessage() {
  if (isSendButtonDisabled.value) return;

  const subMessages: SubMessageCreate[] = isMultiPartMode.value
    ? (multiPartInputRef.value?.getData() || [])
    : [{ content: singlePartDraft.value, sortOrder: 0 }];

  if (subMessages.length > 0) {
    await chatStore.sendMessage(subMessages);
    if (isMultiPartMode.value) {
      multiPartInputRef.value?.reset();
    } else {
      singlePartDraft.value = '';
    }
  }
}

function handleStopGeneration() {
  const genMsg = currentChatMessages.value.find(m => m.sub_messages.some(sm => sm.status === 'generating'));
  if (genMsg) chatStore.cancelGeneration(genMsg.id);
}

// --- Input Mode Switching ---
function handleToggleMultiPartMode() {
  if (!currentChat.value) return;
  const nextMode = !isMultiPartMode.value;
  if (nextMode) {
    multiPartDraft.value = [{ id: Date.now(), content: singlePartDraft.value }];
  } else {
    singlePartDraft.value = multiPartDraft.value.map(p => p.content).join('\n--------------------------\n');
  }
  isMultiPartMode.value = nextMode;
  chatInputModeState[currentChat.value.id] = nextMode;

  debouncedSaveDraft(nextMode ? JSON.stringify(multiPartDraft.value) : singlePartDraft.value);
}

// --- Settings ---
async function handleSaveSettings(settings: ChatUpdate) {
  if (!currentChat.value) return;
  await chatStore.updateChatSettings(currentChat.value.id, settings);
  settingsDrawerVisible.value = false;
  ElMessage.success('设置已保存');
}

// --- Keyboard & Scroll ---
function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    chatStore.undo();
  } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'z') {
    event.preventDefault();
    chatStore.redo();
  }
}

function handleSingleInputKeydown(event: Event) { // 接受更通用的 Event 类型
  // 使用类型守卫确保这是一个键盘事件
  if (!(event instanceof KeyboardEvent)) return;

  // 在这个代码块之后，TypeScript 会智能地推断出 event 是 KeyboardEvent 类型
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSendMessage();
  }
}


const userHasScrolledUp = ref(false);
const handleScroll = ({ scrollTop }: { scrollTop: number }) => {
  const el = scrollbarRef.value?.wrapRef;
  if (!el) return;
  userHasScrolledUp.value = el.scrollHeight - el.clientHeight - scrollTop > 20;
};
const scrollToBottom = (force = false) => {
  if (!force && userHasScrolledUp.value && isGenerating.value) return;
  nextTick(() => scrollbarRef.value?.setScrollTop(scrollbarRef.value.wrapRef!.scrollHeight));
};

watch(
  () => currentChatMessages.value[currentChatMessages.value.length - 1]?.sub_messages.slice(-1)[0]?.content,
  (newContent, oldContent) => {
    // 只有当内容实际发生变化时才滚动，并且忽略 watch 传递的参数
    if (newContent !== oldContent) {
      scrollToBottom();
    }
  }
);

watch(() => currentChat.value?.id, (newId) => {
  if (newId) {
    userHasScrolledUp.value = false;
    isMultiPartMode.value = chatInputModeState[newId] ?? false;

    // Trigger draft update
    const draft = currentDraft.value;
    if (isMultiPartMode.value) {
      if (draft && draft.startsWith('[')) {
        try { multiPartDraft.value = JSON.parse(draft) } catch { /* ignore */ }
      } else {
        multiPartDraft.value = [{ id: Date.now(), content: draft }];
      }
    } else {
      singlePartDraft.value = (draft && draft.startsWith('[')) ? '' : draft;
    }

    // Auto scroll & focus
    const stopWatch = watch(isChatHistoryLoading, (loading) => {
      if (!loading) {
        scrollToBottom(true);
        nextTick(() => inputRef.value?.focus());
        stopWatch();
      }
    }, { immediate: true });
  }
});
</script>

<style scoped>
.chat-window-container { height: 100%; display: flex; flex-direction: column; background-color: var(--color-background); overflow: hidden; }
.welcome-view { display: flex; justify-content: center; align-items: center; height: 100%; }
.chat-window-header { flex-shrink: 0; padding: 0 20px; height: 60px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--color-border); }
.chat-title { margin: 0; font-size: 18px; font-weight: 600; color: var(--color-heading); }
.message-list-scrollbar { flex-grow: 1; }
.message-list-wrapper { padding: 20px; }
.input-container-wrapper { flex-shrink: 0; position: relative; display: flex; flex-direction: column; border-top: 1px solid var(--color-border); }
.resize-handle { position: absolute; top: -3px; left: 0; width: 100%; height: 6px; cursor: ns-resize; z-index: 10; }
.chat-input-area { flex-grow: 1; padding: 10px 20px; background-color: var(--color-background-soft); display: flex; align-items: stretch; min-height: 0; }
.input-field { flex-grow: 1; margin-right: 10px; }
.input-field:deep(.el-textarea__inner) { height: 100% !important; }
.action-button { width: 54px; font-size: 20px; flex-shrink: 0; align-self: flex-end; height: calc(100% - 2px); }
</style>
