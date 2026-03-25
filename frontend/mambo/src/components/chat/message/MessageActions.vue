<!-- frontend/mambo/src/components/chat/message/MessageActions.vue -->
<template>
  <div
    class="message-actions"
    :class="{ 'is-visible': showActions && !isGenerating, 'is-user': isUser }"
  >
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
import type { SubMessage } from '@/api/types'
import UsageInfo from '../UsageInfo.vue'
import {
  Refresh, RefreshLeft, Delete, Edit, CopyDocument, DocumentCopy,
  ArrowUpBold, ArrowDownBold, Clock, Document
} from '@element-plus/icons-vue'

interface EditPayload {
  content: string
  range?: { start: number; end: number }
  language?: string
  markup?: string
}

defineProps<{
  showActions: boolean
  isGenerating: boolean
  isUser: boolean
  isSingleSubMessage: boolean
  isSingleViewCollapsed: boolean
  firstSubMessage?: SubMessage
  usageSubMessage?: SubMessage
}>()

defineEmits<{
  (e: 'regenerate'): void
  (e: 'toggle-collapse'): void
  (e: 'edit-request', subMessage: SubMessage | undefined, payload: EditPayload): void
  (e: 'copy-all'): void
  (e: 'duplicate-upto'): void
  (e: 'compress-history'): void
  (e: 'view-logs'): void
  (e: 'delete'): void
}>()
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
</style>
