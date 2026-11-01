<!-- frontend/mambo/src/mobile/components/chat/message/MobileAssistantBubble.vue -->
<template>
  <div class="mobile-assistant-bubble">

    <!-- Spark 视图折叠提示：移动端无桌面悬浮头，需常驻展开入口 -->
    <div v-if="hasSparkMode" class="spark-toggle-bar" @click.stop="toggleSpark">
      <el-icon>
        <FullScreen v-if="isSparkCollapsed" />
        <Minus v-else />
      </el-icon>
      <span>{{ isSparkCollapsed ? $t('chat.message.expandSpark') : $t('chat.message.collapseSpark') }}</span>
    </div>

    <!-- ========== 堆叠模式 ========== -->
    <template v-if="messageDisplayMode === 'stacked'">
      <!-- 顶部区域：头像 + 思考 -->
      <div class="bubble-header" v-if="reasoningSection || $slots.avatar">
        <!-- 头像插槽 -->
        <div class="bubble-avatar">
          <slot name="avatar"></slot>
        </div>

        <!-- 思考区域 -->
        <div class="bubble-reasoning" v-if="reasoningSection">
          <!-- 最小化态 -->
          <div v-if="isReasoningMinimized" class="reasoning-minimized-block" @click.stop="toggleReasoningMinimize">
            <el-icon>
              <Loading v-if="isGenerating && !hasPendingReviews" class="is-loading" />
              <Warning v-else-if="hasPendingReviews" class="text-warning" />
              <Check v-else />
            </el-icon>
            <span>{{ $t('chat.message.reasoningCollapsed') }}</span>
          </div>

          <!-- 展开态 -->
          <div v-else class="reasoning-expanded">
            <div class="section-title" @click.stop="toggleReasoningMinimize">
              <span>{{ $t('chat.message.reasoning') }}</span>
              <el-icon><ArrowUp /></el-icon>
            </div>
            <div class="section-content">
              <MobileBubbleSectionGroup
                v-for="group in reasoningSection.groups"
                :key="group.id"
                :group="group"
                :parent-message="message"
                :is-generating="isGenerating"
                :is-inactive="isInactive(group)"
                is-reasoning
                @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
                @edit-file="(file) => $emit('edit-file', file)"
                @copy="(subMsg) => $emit('copy', subMsg)"
                @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
                @toggle-actions="(id) => $emit('toggle-actions', id)"
              >
                <!-- 透传操作菜单插槽 -->
                <template #actions>
                  <slot name="actions" :sub-message-id="group.textSubMessage?.id || group.id"></slot>
                </template>
              </MobileBubbleSectionGroup>
            </div>
          </div>
        </div>
      </div>

      <!-- 正文区域：全宽 -->
      <div class="bubble-section normal-section" v-if="normalSection || isGenerating">
        <div class="section-content">
          <MobileBubbleSectionGroup
            v-if="normalSection"
            v-for="group in normalSection.groups"
            :key="group.id"
            :group="group"
            :parent-message="message"
            :is-generating="isGenerating"
            :is-inactive="isInactive(group)"
            @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
            @edit-file="(file) => $emit('edit-file', file)"
            @copy="(subMsg) => $emit('copy', subMsg)"
            @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
            @toggle-actions="(id) => $emit('toggle-actions', id)"
          >
            <!-- 透传操作菜单插槽 -->
            <template #actions>
              <slot name="actions" :sub-message-id="group.textSubMessage?.id || group.id"></slot>
            </template>
          </MobileBubbleSectionGroup>

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
          'mobile-interleaved-section',
          section.type === 'reasoning' ? 'mobile-reasoning-section' : 'mobile-normal-section'
        ]"
      >
        <!-- Reasoning Section (折叠面板) -->
        <template v-if="section.type === 'reasoning'">
          <div class="mobile-reasoning-collapsible" :class="{ 'is-collapsed': isSectionMinimized(section) }">
            <div class="reasoning-collapse-header" @click.stop="toggleSectionMinimize(index)">
              <el-icon class="collapse-arrow">
                <ArrowRight v-if="isSectionMinimized(section)" />
                <ArrowDown v-else />
              </el-icon>
              <span class="collapse-title">{{ $t('chat.message.reasoning') }}</span>
              <el-icon v-if="isGenerating && !hasPendingReviews" class="collapse-status-icon is-loading">
                <Loading />
              </el-icon>
              <el-icon v-else-if="hasPendingReviews" class="collapse-status-icon text-warning">
                <Warning />
              </el-icon>
            </div>
            <div class="reasoning-collapse-body" v-show="!isSectionMinimized(section)">
              <div class="section-content">
                <MobileBubbleSectionGroup
                  v-for="group in section.groups"
                  :key="group.id"
                  :group="group"
                  :parent-message="message"
                  :is-generating="isGenerating"
                  :is-inactive="isInactive(group)"
                  is-reasoning
                  @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
                  @edit-file="(file) => $emit('edit-file', file)"
                  @copy="(subMsg) => $emit('copy', subMsg)"
                  @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
                  @toggle-actions="(id) => $emit('toggle-actions', id)"
                >
                  <template #actions>
                    <slot name="actions" :sub-message-id="group.textSubMessage?.id || group.id"></slot>
                  </template>
                </MobileBubbleSectionGroup>
              </div>
            </div>
          </div>
        </template>

        <!-- Normal Section -->
        <template v-else>
          <div class="section-content">
            <MobileBubbleSectionGroup
              v-for="group in section.groups"
              :key="group.id"
              :group="group"
              :parent-message="message"
              :is-generating="isGenerating"
              :is-inactive="isInactive(group)"
              @edit="(subMsg, payload) => $emit('edit', subMsg, payload)"
              @edit-file="(file) => $emit('edit-file', file)"
              @copy="(subMsg) => $emit('copy', subMsg)"
              @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
              @toggle-actions="(id) => $emit('toggle-actions', id)"
            >
              <template #actions>
                <slot name="actions" :sub-message-id="group.textSubMessage?.id || group.id"></slot>
              </template>
            </MobileBubbleSectionGroup>
          </div>
        </template>
      </div>

      <!-- 交错模式下的空态打字指示器 -->
      <div v-if="isGenerating && interleavedSections.length === 0" class="typing-indicator">
        <span></span><span></span><span></span>
      </div>
    </template>

    <!-- 生图区域：同一次生成的多图编为一组，重跑的多次生成用左右箭头切换 -->
    <MobileImageRunGallery
      v-for="slot in imageSlots"
      :key="slot.slotId"
      :slot="slot"
      :parent-message="message"
      @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
      @edit-file="(file) => $emit('edit-file', file)"
    />

    <!-- 错误区域 (Error)：后端生成的错误子消息，不进时间线，单独呈现原因/堆栈/重试 -->
    <div class="error-section" v-if="errorSubMessages.length > 0 && !isGenerating">
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
            v-if="parseErrorStackTrace(errorSub.content)"
            link
            size="small"
            @click.stop="toggleErrorDetail(errorSub.id)"
          >
            <el-icon class="detail-icon"><View /></el-icon>
            {{ expandedErrorId === errorSub.id ? $t('chat.message.hideStack') : $t('chat.message.showStack') }}
          </el-button>
          <el-button
            link
            size="small"
            type="primary"
            :disabled="!canRetry"
            @click.stop="handleRetry"
          >
            <el-icon><RefreshRight /></el-icon>
            {{ $t('chat.message.retryFromError') }}
          </el-button>
        </div>
        <pre v-if="expandedErrorId === errorSub.id && parseErrorStackTrace(errorSub.content)" class="error-detail">{{ parseErrorStackTrace(errorSub.content) }}</pre>
      </div>
    </div>

    <!-- 尾部工具汇总面板（config.is_tail_tool，不参与正文/时间线；默认折叠） -->
    <TailToolPanel
      v-if="tailToolSubMessages.length > 0"
      :sub-messages="tailToolSubMessages"
      :parent-message="message"
      @open-tool-dialog="(toolId) => $emit('open-tool-dialog', toolId)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { Message, SubMessage, FileResponse } from '@/api/types'
import { useAssistantTimeline, type BubbleSectionGroup } from '@/composables/useAssistantTimeline'
import { useImageRuns } from '@/composables/useImageRuns'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { usePendingFileStore } from '@/stores/pendingFileStore'
import { parseErrorMessage, parseErrorStackTrace } from '@/utils/errorMessage'
import MobileBubbleSectionGroup from './MobileBubbleSectionGroup.vue'
import MobileImageRunGallery from './MobileImageRunGallery.vue'
import TailToolPanel from '@/components/chat/message/TailToolPanel.vue'
import { Loading, Warning, Check, ArrowUp, ArrowRight, ArrowDown, FullScreen, Minus, View, RefreshRight } from '@element-plus/icons-vue'

const props = defineProps<{
  message: Message
  isGenerating: boolean
  currentMessageRank: number
}>()

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void
  (e: 'copy', subMessage: SubMessage): void
  (e: 'open-tool-dialog', subMessageId: string): void
  (e: 'toggle-actions', subMessageId: string): void
  (e: 'edit-file', file: FileResponse): void
}>()

const { t } = useI18n()
const interactionStore = useChatInteractionStore()
const settingsStore = useSettingsStore()
const { globalSettings } = storeToRefs(settingsStore)

const messageRef = computed(() => props.message)
const messageDisplayMode = computed(() => globalSettings.value.message_display_mode ?? 'interleaved')

// 生图「按次编组」：已归入图片区域的 File 子消息不再由正文分组渲染
const { imageSlots, galleryFileIds } = useImageRuns(messageRef)
const timelineMessageRef = computed<Message>(() => {
  if (galleryFileIds.value.size === 0) return props.message
  return {
    ...props.message,
    sub_messages: props.message.sub_messages.filter(sm => !galleryFileIds.value.has(sm.id)),
  }
})

// 归入图片区域的待生成文件不会渲染正文卡片，SSE 订阅需在此代为注册
const pendingFileStore = usePendingFileStore()
const galleryPendingIds = computed(() =>
  imageSlots.value
    .flatMap(slot => slot.runs.flatMap(run => run.pendingFiles))
    .filter(sm => sm.status === 'waiting')
    .map(sm => sm.id),
)

watch(
  galleryPendingIds,
  (ids, oldIds) => {
    for (const id of ids) {
      if (!oldIds?.includes(id)) {
        pendingFileStore.register(id, { onReady() {}, onTimeout() {} })
      }
    }
    for (const id of oldIds ?? []) {
      if (!ids.includes(id)) pendingFileStore.unregister(id)
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  for (const id of galleryPendingIds.value) pendingFileStore.unregister(id)
})

const {
  reasoningSection,
  normalSection,
  interleavedSections,
  isSectionMinimized,
  isReasoningMinimized,
  hasPendingReviews,
  errorSubMessages,
  hasSparkMode,
  isSparkCollapsed,
  toggleSpark,
  tailToolSubMessages
} = useAssistantTimeline(timelineMessageRef, messageDisplayMode)

function toggleReasoningMinimize() {
  const newState = !isReasoningMinimized.value
  interactionStore.batchUpdateSubMessagesMinimalState(props.message.id, newState)
}

/**
 * 交错模式：切换单个 Reasoning section 的最小化状态
 * 将 section 内所有 Reasoning 子消息统一切换
 */
function toggleSectionMinimize(sectionIndex: number) {
  const section = interleavedSections.value[sectionIndex]
  if (!section || section.type !== 'reasoning') return
  const newState = !isSectionMinimized(section)
  for (const group of section.groups) {
    if (group.textSubMessage && group.textSubMessage.type === 'Reasoning') {
      interactionStore.updateSingleSubMessageMinimalState(props.message.id, group.textSubMessage.id, newState)
    }
  }
}

function isInactive(group: BubbleSectionGroup): boolean {
  if (props.isGenerating) return false
  const cpl = group.textSubMessage?.config?.context_participation_length
  if (cpl === undefined || cpl === null) return false
  if (cpl === 0) return true
  if (cpl > 0) return props.currentMessageRank > cpl
  return false
}

// --- Error Section Logic ---
const expandedErrorId = ref<string | null>(null)

const canRetry = computed(() => props.message.status === 'failed' && !props.isGenerating)

function toggleErrorDetail(errorId: string) {
  expandedErrorId.value = expandedErrorId.value === errorId ? null : errorId
}

function handleRetry() {
  if (!canRetry.value) return
  interactionStore.retryFailedGeneration(props.message.id)
}
</script>

<style scoped>
.mobile-assistant-bubble {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

/* ========== Spark 折叠提示条 ========== */
.spark-toggle-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  align-self: flex-start;
  padding: 6px 10px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-color-primary);
  user-select: none;
}

/* ========== 错误区域 ========== */
.error-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-block {
  padding: 10px 12px;
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
  font-size: 15px;
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
  margin: 8px 0 0;
  padding: 8px 10px;
  background-color: var(--el-fill-color-darker);
  border-radius: 6px;
  max-height: 220px;
  overflow-y: auto;
  font-size: 11px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

.bubble-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
}

.bubble-avatar {
  flex-shrink: 0;
  display: flex;
  padding-top: 2px;
}

.bubble-reasoning {
  flex: 1;
  min-width: 0;
}

.reasoning-section {
  position: relative;
}

.reasoning-minimized-block {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  user-select: none;
}

.reasoning-minimized-block .is-loading {
  animation: rotating 2s linear infinite;
}

.text-warning {
  color: var(--el-color-warning);
}

.reasoning-expanded {
  padding: 8px 12px;
  border-left: 3px solid var(--el-border-color-light);
  background-color: var(--color-background-soft);
  border-radius: 0 8px 8px 0;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: bold;
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
}

.normal-section {
  background-color: transparent;
}

.typing-indicator {
  display: flex;
  align-items: center;
  height: 24px;
  padding: 4px 0;
}

.typing-indicator span {
  height: 6px;
  width: 6px;
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

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ========== 交错模式 - 折叠面板样式 ========== */
.mobile-interleaved-section {
  width: 100%;
}

.mobile-reasoning-section {
  position: relative;
}

.mobile-reasoning-collapsible {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
  background-color: var(--color-background-soft);
}

.mobile-reasoning-collapsible .reasoning-collapse-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.mobile-reasoning-collapsible .reasoning-collapse-header .collapse-arrow {
  font-size: 11px;
  flex-shrink: 0;
}

.mobile-reasoning-collapsible .reasoning-collapse-header .collapse-status-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.mobile-reasoning-collapsible .reasoning-collapse-header .collapse-title {
  font-weight: 600;
  flex: 1;
}

.mobile-reasoning-collapsible .reasoning-collapse-header .collapse-status-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.mobile-reasoning-collapsible .reasoning-collapse-body {
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 8px 12px;
  border-left: 3px solid var(--el-border-color-light);
  background-color: var(--color-background-soft);
  margin: 0 6px 6px 6px;
  border-radius: 0 6px 6px 0;
}

.mobile-reasoning-collapsible.is-collapsed .reasoning-collapse-body {
  display: none;
}

.mobile-normal-section {
  background-color: transparent;
}

.mobile-normal-section .section-content {
  /* 无额外样式，保持简洁 */;
}
</style>
