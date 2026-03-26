<!-- frontend/mambo/src/components/chat/message/MessageActions.vue -->
<template>
  <div
    class="message-actions"
    :class="{ 'is-visible': showActions && !isGenerating, 'is-user': isUser }"
  >
    <div v-if="hasSiblings" class="branch-switcher" :class="{ 'is-user': isUser }">
      <el-button
        link
        :disabled="!canGoPrev"
        @click="handlePrev"
        class="switcher-btn"
      >
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <span class="branch-text">{{ currentIndex }} / {{ totalSiblings }}</span>
      <el-button
        link
        :disabled="!canGoNext"
        @click="handleNext"
        class="switcher-btn"
      >
        <el-icon><ArrowRight /></el-icon>
      </el-button>
    </div>

    <el-tooltip :content="$t('chat.message.regenerate')" placement="top" :show-after="500">
      <el-button
        :icon="isUser ? RefreshLeft : Refresh"
        circle
        size="small"
        @click="$emit('regenerate')"
      />
    </el-tooltip>

    <el-tooltip
      v-if="isSingleSubMessage"
      :content="isSingleViewCollapsed ? $t('chat.message.expand') : $t('chat.message.collapse')"
      placement="top"
      :show-after="500"
    >
      <el-button
        :icon="isSingleViewCollapsed ? ArrowDownBold : ArrowUpBold"
        circle
        size="small"
        @click="$emit('toggle-collapse')"
      />
    </el-tooltip>

    <el-tooltip
      v-if="isSingleSubMessage"
      :content="$t('common.action.edit')"
      placement="top"
      :show-after="500"
    >
      <el-button
        :icon="Edit"
        circle
        size="small"
        @click="$emit('edit-request', firstSubMessage, { content: firstSubMessage?.content || '' })"
      />
    </el-tooltip>

    <el-tooltip
      :content="isSingleSubMessage ? $t('common.action.copy') : $t('chat.message.copyAll')"
      placement="top"
      :show-after="500"
    >
      <el-button :icon="CopyDocument" circle size="small" @click="$emit('copy-all')" />
    </el-tooltip>

    <el-tooltip
      :content="$t('chat.message.duplicateUpToHere')"
      placement="top"
      :show-after="500"
    >
      <el-button :icon="DocumentCopy" circle size="small" @click="$emit('duplicate-upto')" />
    </el-tooltip>

    <el-tooltip
      v-if="!isUser"
      :content="$t('chat.message.compressHistory')"
      placement="top"
      :show-after="500"
    >
      <el-button :icon="Clock" circle size="small" @click="$emit('compress-history')" />
    </el-tooltip>

    <el-tooltip
      v-if="!isUser"
      :content="$t('chat.message.viewLogs')"
      placement="top"
      :show-after="500"
    >
      <el-button :icon="Document" circle size="small" @click="$emit('view-logs')" />
    </el-tooltip>

    <el-tooltip :content="$t('common.action.delete')" placement="top" :show-after="500">
      <el-button :icon="Delete" circle size="small" type="danger" plain @click="$emit('delete')" />
    </el-tooltip>

    <UsageInfo
      v-if="usageSubMessage"
      :usage-sub-message="usageSubMessage"
      class="usage-info-component"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Message, SubMessage } from '@/api/types'
import UsageInfo from '../UsageInfo.vue'
import {
  Refresh, RefreshLeft, Delete, Edit, CopyDocument, DocumentCopy,
  ArrowUpBold, ArrowDownBold, Clock, Document, ArrowLeft, ArrowRight
} from '@element-plus/icons-vue'

interface EditPayload {
  content: string
  range?: { start: number; end: number }
  language?: string
  markup?: string
}

const props = defineProps<{
  message: Message
  showActions: boolean
  isGenerating: boolean
  isUser: boolean
  isSingleSubMessage: boolean
  isSingleViewCollapsed: boolean
  firstSubMessage?: SubMessage
  usageSubMessage?: SubMessage
}>()

const emit = defineEmits<{
  (e: 'regenerate'): void
  (e: 'toggle-collapse'): void
  (e: 'edit-request', subMessage: SubMessage | undefined, payload: EditPayload): void
  (e: 'copy-all'): void
  (e: 'duplicate-upto'): void
  (e: 'compress-history'): void
  (e: 'view-logs'): void
  (e: 'delete'): void
  (e: 'switch-branch', messageId: string): void
}>()

const hasSiblings = computed(() => props.message.sibling_ids && props.message.sibling_ids.length > 1)
const currentIndex = computed(() => props.message.sibling_index + 1)
const totalSiblings = computed(() => props.message.sibling_ids ? props.message.sibling_ids.length : 0)
const canGoPrev = computed(() => props.message.sibling_index > 0 && !props.isGenerating)
const canGoNext = computed(() => props.message.sibling_ids && props.message.sibling_index < props.message.sibling_ids.length - 1 && !props.isGenerating)

function handlePrev() {
  if (canGoPrev.value && props.message.sibling_ids) {
    emit('switch-branch', props.message.sibling_ids[props.message.sibling_index - 1])
  }
}

function handleNext() {
  if (canGoNext.value && props.message.sibling_ids) {
    emit('switch-branch', props.message.sibling_ids[props.message.sibling_index + 1])
  }
}
</script>

<style scoped>
.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  opacity: 0;
  visibility: hidden;
  min-height: 24px;
  transition: opacity 0.2s, visibility 0.2s;
  align-items: center;
}
.message-actions.is-visible {
  opacity: 1;
  visibility: visible;
}
.message-actions.is-user {
  justify-content: flex-end;
}
.usage-info-component {
  margin-left: 8px;
}

.branch-switcher {
  display: flex;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  order: -1;
  margin-right: 8px;
  background-color: var(--color-background-soft);
  border-radius: 4px;
  padding: 2px;
}
.branch-switcher.is-user {
  order: 99;
  margin-right: 0;
  margin-left: 8px;
}
.branch-text {
  margin: 0 6px;
  user-select: none;
  font-variant-numeric: tabular-nums;
}
.switcher-btn {
  padding: 2px 4px;
  height: auto;
}
</style>
