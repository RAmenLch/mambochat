<!-- frontend/mambo/src/components/chat/message/AssistantBubble.vue -->
<template>
  <div class="assistant-bubble-container" :class="{ 'is-collapsed': isBubbleCollapsed }">

    <!-- 大气泡头部控制栏 -->
    <div class="bubble-global-header">
      <div class="header-left">
        <el-icon><Cpu /></el-icon>
        <span class="bubble-title">{{ assistantName }}</span>
      </div>
      <div class="header-right">
        <el-tooltip v-if="hasSparkMode" :content="isSparkCollapsed ? $t('chat.message.expandSpark') : $t('chat.message.collapseSpark')" placement="top">
          <el-button :icon="isSparkCollapsed ? FullScreen : Minus" circle text size="small" @click="toggleSpark" />
        </el-tooltip>
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

      <!-- ========== 堆叠模式 ========== -->
      <template v-if="messageDisplayMode === 'stacked'">
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
                :show-zip-coverage="zipCoverageGroupIds.has(group.id)"
                is-reasoning
                @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
                @copy="(subMsg) => $emit('copy', subMsg)"
                @edit-file="(file) => $emit('edit-file', file)"
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
              :show-zip-coverage="zipCoverageGroupIds.has(group.id)"
              @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
              @copy="(subMsg) => $emit('copy', subMsg)"
              @edit-file="(file) => $emit('edit-file', file)"
              @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
            />

            <div v-if="isGenerating && (!normalSection || normalSection.groups.length === 0)" class="typing-indicator">
              <span></span><span></span><span></span>
            </div>
          </div>
        </div>
      </template>

      <!-- ========== 交错模式 ========== -->
      <template v-else>
        <div
          v-for="(section, index) in interleavedSections"
          :key="section.groups[0]?.id || index"
          :class="[
            'bubble-section',
            section.type === 'reasoning' ? 'interleaved-reasoning-section' : 'interleaved-normal-section'
          ]"
        >
          <!-- Reasoning Section (折叠面板) -->
          <template v-if="section.type === 'reasoning'">
            <div class="reasoning-collapsible" :class="{ 'is-collapsed': isSectionMinimized(section) }">
              <div class="reasoning-collapse-header" @click="toggleSectionMinimize(index)">
                <el-icon class="collapse-arrow">
                  <ArrowRight v-if="isSectionMinimized(section)" />
                  <ArrowDown v-else />
                </el-icon>
                <span class="collapse-title">{{ $t('chat.message.reasoning') }}</span>
                <el-icon v-if="isGenerating && !hasPendingReviews" class="collapse-status-icon is-loading">
                  <Loading />
                </el-icon>
                <el-icon v-else-if="hasPendingReviews" class="collapse-status-icon">
                  <Warning />
                </el-icon>
              </div>
              <div class="reasoning-collapse-body" v-show="!isSectionMinimized(section)">
                <div class="section-content">
                  <BubbleSectionGroup
                    v-for="group in section.groups"
                    :key="group.id"
                    :group="group"
                    :parent-message="message"
                    :is-generating="isGenerating"
                    :is-inactive="isInactive(group)"
                    :show-zip-coverage="zipCoverageGroupIds.has(group.id)"
                    is-reasoning
                    @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
                    @copy="(subMsg) => $emit('copy', subMsg)"
                    @edit-file="(file) => $emit('edit-file', file)"
                    @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
                  />
                </div>
              </div>
            </div>

            <!-- Zip History 覆盖指示器（仅折叠时显示，展开时 BubbleSectionGroup 内部已渲染） -->
            <div v-if="sectionHasZipCoverage(section) && isSectionMinimized(section)" class="zip-coverage-indicator">
              <el-tooltip :content="$t('chat.message.zipCoverageTip')" placement="top" :show-after="300">
                <div class="zip-coverage-arrow">
                  <svg width="16" height="10" viewBox="0 0 16 10" fill="none">
                    <path d="M8 1L14 9H2L8 1Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                  </svg>
                </div>
              </el-tooltip>
            </div>
          </template>

          <!-- Normal Section -->
          <template v-else>
            <div class="section-content">
              <BubbleSectionGroup
                v-for="group in section.groups"
                :key="group.id"
                :group="group"
                :parent-message="message"
                :is-generating="isGenerating"
                :is-inactive="isInactive(group)"
                :show-zip-coverage="zipCoverageGroupIds.has(group.id)"
                @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
                @copy="(subMsg) => $emit('copy', subMsg)"
                @edit-file="(file) => $emit('edit-file', file)"
                @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
              />
            </div>
          </template>
        </div>

        <!-- 交错模式下的空态打字指示器 -->
        <div v-if="isGenerating && interleavedSections.length === 0" class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </template>

      <!-- 错误区域 (Error) -->
      <div class="bubble-section error-section" v-if="errorSubMessages.length > 0 && !isGenerating">
        <div
          v-for="errorSub in errorSubMessages"
          :key="errorSub.id"
          class="error-block"
        >
          <div class="error-header">
            <el-icon><Warning /></el-icon>
            <span class="error-title">{{ $t('chat.message.errorOccurred') }}</span>
          </div>
          <div class="error-message">{{ parseErrorMessage(errorSub.content) }}</div>
          <div class="error-actions">
            <el-button
              v-if="errorSub.content && parseErrorStackTrace(errorSub.content)"
              link
              size="small"
              @click="toggleErrorDetail(errorSub.id)"
            >
              <el-icon class="detail-icon"><View /></el-icon>
              {{ expandedErrorId === errorSub.id ? $t('chat.message.hideStack') : $t('chat.message.showStack') }}
            </el-button>
            <el-button
              link
              size="small"
              type="primary"
              @click="handleRetry"
            >
              <el-icon><RefreshRight /></el-icon>
              {{ $t('chat.message.retryFromError') }}
            </el-button>
          </div>
          <div v-if="expandedErrorId === errorSub.id && parseErrorStackTrace(errorSub.content)" class="error-detail">
            <pre>{{ parseErrorStackTrace(errorSub.content) }}</pre>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { storeToRefs } from 'pinia';
import type { Message, SubMessage, ErrorContent, FileResponse } from '@/api/types';
import { useAssistantTimeline, type BubbleSectionGroup } from '@/composables/useAssistantTimeline';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import { useAgentStore } from '@/stores/agentStore';
import { useSettingsStore } from '@/stores/settingsStore';
import BubbleSectionGroupComponent from './BubbleSectionGroup.vue';
import { Cpu, Minus, FullScreen, ArrowUpBold, ArrowDownBold, ArrowRight, ArrowDown, Loading, Warning, Check, Opportunity, View, RefreshRight } from '@element-plus/icons-vue';

const BubbleSectionGroup = BubbleSectionGroupComponent;

const props = defineProps<{
  message: Message;
  isGenerating: boolean;
  currentMessageRank: number;
}>();

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void;
  (e: 'copy', subMessage: SubMessage): void;
  (e: 'edit-file', file: FileResponse): void;
  (e: 'open-tool-dialog', subMessageId: string): void;
}>();

const { t } = useI18n();
const interactionStore = useChatInteractionStore();
const sessionStore = useChatSessionStore();
const agentStore = useAgentStore();
const settingsStore = useSettingsStore();
const { globalSettings } = storeToRefs(settingsStore);

const messageRef = computed(() => props.message);
const messageDisplayMode = computed(() => globalSettings.value.message_display_mode ?? 'interleaved');

const {
  reasoningSection,
  normalSection,
  interleavedSections,
  isSectionMinimized,
  isReasoningMinimized,
  hasPendingReviews,
  errorSubMessages,
  zipCoverageGroupIds,
  hasSparkMode,
  isSparkCollapsed,
  toggleSpark,
} = useAssistantTimeline(messageRef, messageDisplayMode);

const isBubbleCollapsed = ref(false);

const assistantName = computed(() => {
  const currentChat = sessionStore.currentChat;
  if (currentChat?.chatMode === 'agent' && currentChat.agentId) {
    const agent = agentStore.allAgents.find(a => a.id === currentChat.agentId);
    if (agent && agent.name) {
      return agent.name;
    }
  }
  return t('chat.message.ai_assistant');
});

function toggleReasoningMinimize() {
  const newState = !isReasoningMinimized.value;
  interactionStore.batchUpdateSubMessagesMinimalState(props.message.id, newState);
}

/**
 * 交错模式：切换单个 Reasoning section 的最小化状态
 * 将 section 内所有 Reasoning 子消息统一切换
 */
function toggleSectionMinimize(sectionIndex: number) {
  const section = interleavedSections.value[sectionIndex];
  if (!section || section.type !== 'reasoning') return;
  const newState = !isSectionMinimized(section);
  for (const group of section.groups) {
    if (group.textSubMessage && group.textSubMessage.type === 'Reasoning') {
      interactionStore.updateSingleSubMessageMinimalState(props.message.id, group.textSubMessage.id, newState);
    }
  }
}

function isInactive(group: BubbleSectionGroup): boolean {
  if (props.isGenerating) return false;
  const cpl = group.textSubMessage?.config?.context_participation_length;
  if (cpl === undefined || cpl === null) return false;
  if (cpl === 0) return true;
  if (cpl > 0) return props.currentMessageRank > cpl;
  return false;
}

/** 交错模式：判断 section 中是否有任何 group 需要显示 Zip 覆盖箭头 */
function sectionHasZipCoverage(section: { groups: BubbleSectionGroup[] }): boolean {
  return section.groups.some(g => zipCoverageGroupIds.value.has(g.id));
}

// --- Error Section Logic ---
const expandedErrorId = ref<string | null>(null);

const ERROR_TYPE_PREFIX = /^(?:RuntimeError|ValueError|Exception|OSError|KeyError|TypeError|AttributeError|IndexError|ConnectionError|TimeoutError):\s*/;

const ERROR_EXACT_MAP: Record<string, string> = {
  '模型未返回任何摘要内容': 'chat.message.errorZipNoSummary',
  'DDG 返回了验证码页面，请稍后重试': 'chat.message.errorWebSearchCaptcha',
  '会话未配置模型': 'chat.message.errorNoModelConfigured',
};

const ERROR_PREFIX_MATCHES: Array<{
  prefix: string;
  key: string;
  extract?: (body: string) => Record<string, string>;
}> = [
  {
    prefix: '不支持的读取策略: ',
    key: 'chat.message.errorWebSearchStrategy',
    extract: (body) => ({ strategy: body.slice('不支持的读取策略: '.length).split('，')[0] }),
  },
  {
    prefix: '未能从全局设置 ',
    key: 'chat.message.errorModelConfigNotFound',
    extract: (body) => ({ keys: body.slice('未能从全局设置 '.length).split(' 中找到')[0] }),
  },
  {
    prefix: 'Agent 绑定的模型 ',
    key: 'chat.message.errorAgentModelNotFound',
    extract: (body) => ({ modelId: body.slice('Agent 绑定的模型 '.length).split(' 不存在')[0] }),
  },
];

function parseErrorContent(content: string): ErrorContent | null {
  try {
    return JSON.parse(content) as ErrorContent;
  } catch {
    return null;
  }
}

function parseErrorMessage(content: string): string {
  const parsed = parseErrorContent(content);
  const message = parsed?.message || content;
  if (!message) return message;
  if (message === '生成被用户取消。' || message === '生成被用户取消') {
    return t('chat.message.errorCancelled');
  }
  const UNHANDLED_PREFIX = '发生未处理的异常: ';
  if (message.startsWith(UNHANDLED_PREFIX)) {
    return t('chat.message.errorUnhandled', {
      detail: message.slice(UNHANDLED_PREFIX.length),
    });
  }
  const typeMatch = message.match(ERROR_TYPE_PREFIX);
  const body = typeMatch ? message.slice(typeMatch[0].length) : message;
  const exactKey = ERROR_EXACT_MAP[body];
  if (exactKey) return t(exactKey);
  for (const rule of ERROR_PREFIX_MATCHES) {
    if (body.startsWith(rule.prefix)) {
      const params = rule.extract ? rule.extract(body) : undefined;
      return t(rule.key, params);
    }
  }
  return message;
}

function parseErrorStackTrace(content: string): string {
  const parsed = parseErrorContent(content);
  return parsed?.stack_trace || '';
}

function toggleErrorDetail(errorId: string) {
  expandedErrorId.value = expandedErrorId.value === errorId ? null : errorId;
}

function handleRetry() {
  interactionStore.retryFailedGeneration(props.message.id);
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

/* ========== 错误区域 ========== */
.error-section {
  border-top: 1px solid var(--el-color-error-light-5);
  padding-top: 12px;
}

/* ========== 交错模式 - 折叠面板样式 ========== */
.interleaved-reasoning-section {
  position: relative;
}

.reasoning-collapsible {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background-color: #fafafa;
}

.reasoning-collapse-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.15s;
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.reasoning-collapse-header:hover {
  background-color: #f0f0f0;
}

.reasoning-collapse-header .collapse-arrow {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.reasoning-collapse-header .collapse-status-icon {
  font-size: 14px;
  flex-shrink: 0;
  color: var(--el-text-color-secondary);
}

.reasoning-collapse-header .collapse-title {
  font-weight: 600;
  flex: 1;
}

.reasoning-collapse-body {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 12px 16px;
  border-left: 3px solid var(--el-border-color);
  background-color: #f5f5f5;
  margin: 0 8px 8px 8px;
  border-radius: 0 6px 6px 0;
}

.reasoning-collapsible.is-collapsed .reasoning-collapse-body {
  display: none;
}

.interleaved-reasoning-section :deep(.message-content) {
  color: var(--el-text-color-primary) !important;
}

.interleaved-reasoning-section :deep(.content-block strong),
.interleaved-reasoning-section :deep(.content-block b) {
  color: var(--el-text-color-primary) !important;
}

.interleaved-normal-section {
  /* 继承主体的白色背景即可 */
}

.interleaved-normal-section :deep(.message-content) {
  color: var(--el-text-color-primary);
}

/* ========== Zip History 覆盖指示器（section 级别） ========== */
.zip-coverage-indicator {
  display: flex;
  justify-content: flex-start;
  padding-left: 4px;
  margin-top: -12px;
}

.zip-coverage-arrow {
  color: var(--el-color-success-light-3);
  cursor: help;
  transition: color 0.2s, transform 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.zip-coverage-arrow:hover {
  color: var(--el-color-success);
  transform: translateY(-1px);
}

.error-block {
  padding: 10px 14px;
  background-color: var(--el-color-error-light-9);
  border: 1px solid var(--el-color-error-light-5);
  border-radius: 8px;
}

.error-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.error-header .el-icon {
  color: var(--el-color-error);
  font-size: 16px;
}

.error-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-error);
}

.error-message {
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.5;
  word-break: break-word;
}

.error-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.error-actions .detail-icon {
  margin-right: 2px;
}

.error-detail {
  margin-top: 8px;
  padding: 8px 10px;
  background-color: var(--el-fill-color-darker);
  border-radius: 6px;
  max-height: 300px;
  overflow-y: auto;
}

.error-detail pre {
  font-size: 12px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  line-height: 1.5;
}
</style>
