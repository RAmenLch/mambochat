<!-- frontend/mambo/src/mobile/components/chat/message/MobileAssistantBubble.vue -->
<template>
  <div class="mobile-assistant-bubble">
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Message, SubMessage } from '@/api/types'
import { useAssistantTimeline, type BubbleSectionGroup } from '@/composables/useAssistantTimeline'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import MobileBubbleSectionGroup from './MobileBubbleSectionGroup.vue'
import { Loading, Warning, Check, ArrowUp } from '@element-plus/icons-vue'

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
}>()

const { t } = useI18n()
const interactionStore = useChatInteractionStore()

const messageRef = computed(() => props.message)

const {
  reasoningSection,
  normalSection,
  isReasoningMinimized,
  hasPendingReviews
} = useAssistantTimeline(messageRef)

function toggleReasoningMinimize() {
  const newState = !isReasoningMinimized.value
  interactionStore.batchUpdateSubMessagesMinimalState(props.message.id, newState)
}

function isInactive(group: BubbleSectionGroup): boolean {
  if (props.isGenerating) return false
  const cpl = group.textSubMessage?.config?.context_participation_length
  if (cpl === undefined || cpl === null) return false
  if (cpl === 0) return true
  if (cpl > 0) return props.currentMessageRank > cpl
  return false
}
</script>

<style scoped>
.mobile-assistant-bubble {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
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
</style>
