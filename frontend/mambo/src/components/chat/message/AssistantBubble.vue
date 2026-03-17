<!-- frontend/mambo/src/components/chat/message/AssistantBubble.vue -->
<template>
  <div class="assistant-bubble-container" :class="{ 'is-collapsed': isBubbleCollapsed }">

    <!-- 大气泡头部控制栏 -->
    <div class="bubble-global-header">
      <div class="header-left">
        <el-icon><Cpu /></el-icon>
        <span class="bubble-title">AI Assistant</span>
      </div>
      <div class="header-right">
        <el-tooltip v-if="reasoningSection" :content="isReasoningMinimized ? $t('chat.message.expandReasoning', '展开思考') : $t('chat.message.minimizeReasoning', '最小化思考')" placement="top">
          <el-button :icon="isReasoningMinimized ? FullScreen : Minus" circle text size="small" @click="toggleReasoningMinimize" :disabled="isGenerating && !hasPendingReviews" />
        </el-tooltip>
        <el-tooltip :content="isBubbleCollapsed ? $t('common.action.expand', '展开气泡') : $t('common.action.collapse', '折叠气泡')" placement="top">
          <el-button :icon="isBubbleCollapsed ? ArrowDownBold : ArrowUpBold" circle text size="small" @click="isBubbleCollapsed = !isBubbleCollapsed" />
        </el-tooltip>
      </div>
    </div>

    <!-- 气泡主体内容 -->
    <div class="bubble-body" v-show="!isBubbleCollapsed">

      <!-- 思考区域 (Reasoning) -->
      <div class="bubble-section reasoning-section" v-if="reasoningSection">
        <!-- 最小化态 (已改为圆角矩形) -->
        <div v-if="isReasoningMinimized" class="reasoning-minimized-block" @click="toggleReasoningMinimize">
          <el-icon>
            <Loading v-if="isGenerating && !hasPendingReviews" class="is-loading" />
            <Warning v-else-if="hasPendingReviews" style="color: var(--el-color-warning)" />
            <Check v-else style="color: var(--el-color-success)" />
          </el-icon>
          <span>{{ $t('chat.message.reasoningCollapsed', '思考过程 (已折叠)') }}</span>
        </div>

        <!-- 展开态 -->
        <div v-else class="reasoning-expanded">
          <div class="section-title" @click="toggleReasoningMinimize">
            {{ $t('chat.message.reasoning', '思考过程') }} ▼
          </div>
          <div class="section-content">
            <BubbleSectionGroup
              v-for="group in reasoningSection.groups"
              :key="group.id"
              :group="group"
              :parent-message="message"
              :is-generating="isGenerating"
              :is-inactive="isInactive(group)"
              @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
              @copy="(subMsg) => $emit('copy', subMsg)"
              @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
            />
          </div>
        </div>
      </div>

      <!-- 正文区域 (Normal) -->
      <div class="bubble-section normal-section" v-if="normalSection || isGenerating">
        <div class="section-content">
          <BubbleSectionGroup
            v-if="normalSection"
            v-for="group in normalSection.groups"
            :key="group.id"
            :group="group"
            :parent-message="message"
            :is-generating="isGenerating"
            :is-inactive="isInactive(group)"
            @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
            @copy="(subMsg) => $emit('copy', subMsg)"
            @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
          />

          <div v-if="isGenerating && (!normalSection || normalSection.groups.length === 0)" class="typing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import type { Message, SubMessage } from '@/api/types';
import { useAssistantTimeline, type BubbleSectionGroup } from '@/composables/useAssistantTimeline';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import BubbleSectionGroupComponent from './BubbleSectionGroup.vue';
import { Cpu, Minus, FullScreen, ArrowUpBold, ArrowDownBold, Loading, Warning, Check } from '@element-plus/icons-vue';

const BubbleSectionGroup = BubbleSectionGroupComponent;

const props = defineProps<{
  message: Message;
  isGenerating: boolean;
  currentMessageRank: number;
}>();

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void;
  (e: 'copy', subMessage: SubMessage): void;
  (e: 'open-tool-dialog', subMessageId: string): void;
}>();

const interactionStore = useChatInteractionStore();
const messageRef = computed(() => props.message);

const {
  reasoningSection,
  normalSection,
  isReasoningMinimized,
  hasPendingReviews
} = useAssistantTimeline(messageRef);

const isBubbleCollapsed = ref(false);

function toggleReasoningMinimize() {
  const newState = !isReasoningMinimized.value;
  interactionStore.batchUpdateSubMessagesMinimalState(props.message.id, newState);
}

function isInactive(group: BubbleSectionGroupComponent): boolean {
  if (props.isGenerating) return false;
  const cpl = group.textSubMessage?.config?.context_participation_length;
  if (cpl === undefined || cpl === null) return false;
  if (cpl === 0) return true;
  if (cpl > 0) return props.currentMessageRank > cpl;
  return false;
}
</script>

<style scoped>
.assistant-bubble-container {
  width: 100%;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.assistant-bubble-container.is-collapsed {
  max-height: 40px;
}

.bubble-global-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  background-color: rgba(0, 0, 0, 0.03);
  border-bottom: 1px solid var(--el-border-color-lighter);
  height: 36px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.bubble-body {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.reasoning-section {
  position: relative;
}

/* 已修正为圆角矩形 */
.reasoning-minimized-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background-color: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 6px; /* 已修正为 6px 圆角矩形 */
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.reasoning-minimized-block:hover {
  background-color: var(--el-fill-color);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}
.reasoning-minimized-block .is-loading {
  animation: rotating 2s linear infinite;
}

.reasoning-expanded {
  padding-left: 12px;
  border-left: 3px solid var(--el-border-color);
}

.section-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: bold;
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
  display: inline-block;
}
.section-title:hover {
  color: var(--el-text-color-primary);
}

.normal-section {
  padding-left: 4px;
}

.typing-indicator {
  display: flex;
  align-items: center;
  height: 24px;
  padding: 8px 0;
}
.typing-indicator span {
  height: 8px;
  width: 8px;
  border-radius: 50%;
  background-color: #909399;
  margin: 0 3px;
  animation: bounce 1.4s infinite ease-in-out both;
}
.typing-indicator span:nth-of-type(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-of-type(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}
</style>
