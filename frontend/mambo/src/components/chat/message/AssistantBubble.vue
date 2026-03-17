<template>
  <div class="assistant-bubble-container" :class="{ 'is-collapsed': isBubbleCollapsed }">

    <!-- 大气泡头部控制栏 -->
    <div class="bubble-global-header">
      <div class="header-left">
        <el-icon><Cpu /></el-icon>
        <span class="bubble-title">{{$t("chat.message.ai_assistant")}}</span>
      </div>
      <div class="header-right">
        <el-tooltip v-if="reasoningSection" :content="isReasoningMinimized ? $t('chat.message.expandReasoning') : $t('chat.message.minimizeReasoning')" placement="top">
          <el-button :icon="isReasoningMinimized ? FullScreen : Minus" circle text size="small" @click="toggleReasoningMinimize" :disabled="isGenerating && !hasPendingReviews" />
        </el-tooltip>
        <el-tooltip :content="isBubbleCollapsed ? $t('common.action.expand') : $t('common.action.collapse')" placement="top">
          <el-button :icon="isBubbleCollapsed ? ArrowDownBold : ArrowUpBold" circle text size="small" @click="isBubbleCollapsed = !isBubbleCollapsed" />
        </el-tooltip>
      </div>
    </div>

    <!-- 气泡主体内容 -->
    <div class="bubble-body" v-show="!isBubbleCollapsed">

      <!-- 思考区域 (Reasoning) -->
      <div class="bubble-section reasoning-section" v-if="reasoningSection">
        <!-- 最小化态 -->
        <div v-if="isReasoningMinimized" class="reasoning-minimized-block" @click="toggleReasoningMinimize">
          <el-icon>
            <Loading v-if="isGenerating && !hasPendingReviews" class="is-loading" />
            <Warning v-else-if="hasPendingReviews" />
            <Check v-else />
          </el-icon>
          <span>{{ $t('chat.message.reasoningCollapsed') }}</span>
        </div>

        <!-- 展开态 -->
        <div v-else class="reasoning-expanded">
          <div class="section-title" @click="toggleReasoningMinimize">
            {{ $t('chat.message.reasoning') }}
          </div>
          <div class="section-content">
            <BubbleSectionGroup
              v-for="group in reasoningSection.groups"
              :key="group.id"
              :group="group"
              :parent-message="message"
              :is-generating="isGenerating"
              :is-inactive="isInactive(group)"
              is-reasoning
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
import { Cpu, Minus, FullScreen, ArrowUpBold, ArrowDownBold, Loading, Warning, Check, Opportunity } from '@element-plus/icons-vue';

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
/* ========== 大气泡容器 ========== */
.assistant-bubble-container {
  width: 100%;
  background-color: var(--el-bg-color); /* 白色底 */
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: max-height 0.3s ease;
}

.assistant-bubble-container.is-collapsed {
  max-height: 40px;
}

/* ========== 头部控制栏 ========== */
.bubble-global-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 12px;
  background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, transparent 60%);
  border-bottom: 1px solid var(--el-border-color-lighter);
  height: 36px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ========== 气泡主体 ========== */
.bubble-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  background-color: #ffffff; /* 确保主体是纯白 */
}

/* ========== 思考区域（极浅白色背景） ========== */
.reasoning-section {
  position: relative;
}

.reasoning-minimized-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  background-color: #fafafa; /* 极浅的灰白 */
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-primary); /* 深色文字 */
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.reasoning-minimized-block:hover {
  background-color: #f5f5f5;
  border-color: var(--el-border-color);
}
.reasoning-minimized-block .is-loading {
  animation: rotating 2s linear infinite;
}

.reasoning-expanded {
  padding: 12px 16px;
  border-left: 3px solid var(--el-border-color); /* 中性灰竖线 */
  background-color: #fafafa; /* 极浅的灰白，区别于纯白正文 */
  border-radius: 0 8px 8px 0;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-weight: bold;
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
}
.section-title:hover {
  color: var(--el-text-color-primary);
}

/* 思考区域文字强制深色 */
.reasoning-section :deep(.message-content) {
  color: var(--el-text-color-primary) !important;
}
.reasoning-section :deep(.content-block strong),
.reasoning-section :deep(.content-block b) {
  color: var(--el-text-color-primary) !important;
}

/* ========== 正文区域（纯白背景） ========== */
.normal-section {
  /* 继承主体的白色背景即可 */
}

.normal-section :deep(.message-content) {
  color: var(--el-text-color-primary);
}

/* ========== 加载动画 ========== */
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
  background-color: var(--el-color-primary-light-3);
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
