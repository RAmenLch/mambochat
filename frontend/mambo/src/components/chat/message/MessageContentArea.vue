<template>
  <div
    class="sub-messages-container"
    :class="{
      'is-single': useSinglePartitionView,
      'is-single-collapsed': useSinglePartitionView && isSingleViewCollapsed,
      'is-user': isUser
    }"
  >
    <!-- Initial Loading Placeholder -->
    <div
      v-if="isGenerating && normalSubMessages.length === 0"
      class="initial-loading-placeholder"
    >
      <div class="typing-indicator"><span></span><span></span><span></span></div>
    </div>

    <template v-for="(group, groupIndex) in groupedSubMessages" :key="groupIndex">
      <!-- File Group -->
      <div v-if="group.type === 'file'" class="file-group-container">
        <SubMessageItem
          v-for="(subMessage, index) in group.sub_messages"
          :key="subMessage.id"
          :id="`sub-msg-${subMessage.id}`"
          :sub-message="subMessage"
          :parent-message="message"
          :index="index + 1"
          :is-minimize-disabled="isLastVisibleSubMessage"
          :is-inactive="isSubMessageInactive(subMessage)"
          @edit="(payload) => $emit('edit', subMessage, payload)"
          @edit-file="(file) => $emit('edit-file', file)"
          @copy="$emit('copy', subMessage)"
        />
      </div>
      <!-- Normal SubMessage -->
      <SubMessageItem
        v-else
        :key="group.sub_messages[0].id"
        :id="`sub-msg-${group.sub_messages[0].id}`"
        :sub-message="group.sub_messages[0]"
        :parent-message="message"
        :show-header="!useSinglePartitionView"
        :index="group.sub_messages[0].sortOrder + 1"
        :is-minimize-disabled="isLastVisibleSubMessage"
        :is-inactive="isSubMessageInactive(group.sub_messages[0])"
        @edit="(payload) => $emit('edit', group.sub_messages[0], payload)"
        @copy="$emit('copy', group.sub_messages[0])"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Message, SubMessage, FileResponse } from '@/api/types'
import SubMessageItem from '../SubMessageItem.vue'

interface SubMessageGroup {
  type: 'file' | 'normal'
  sub_messages: SubMessage[]
}

const props = defineProps<{
  message: Message
  normalSubMessages: SubMessage[]
  isSingleViewCollapsed: boolean
  currentMessageRank: number
  isGenerating: boolean
  isUser: boolean
}>()

const emit = defineEmits<{
  (e: 'edit', subMessage: SubMessage, payload: any): void
  (e: 'edit-file', file: FileResponse): void
  (e: 'copy', subMessage: SubMessage): void
}>()

function isSubMessageInactive(subMessage: SubMessage): boolean {
  if (props.isGenerating) return false
  const cpl = subMessage.config?.context_participation_length
  if (cpl === undefined || cpl === null) return false
  if (cpl === 0) return true
  if (cpl > 0) return props.currentMessageRank > cpl
  return false
}

const isLastVisibleSubMessage = computed(() => props.normalSubMessages.length === 1)
const firstSubMessage = computed(() => props.normalSubMessages[0])

const useSinglePartitionView = computed(() => {
  return props.normalSubMessages.length === 1 && firstSubMessage.value?.type === 'Normal'
})

const groupedSubMessages = computed((): SubMessageGroup[] => {
  if (!props.normalSubMessages || props.normalSubMessages.length === 0) return []

  const result: SubMessageGroup[] = []
  let lastGroup: SubMessageGroup | null = null

  for (const subMessage of props.normalSubMessages) {
    if (subMessage.type === 'File') {
      if (lastGroup && lastGroup.type === 'file') {
        lastGroup.sub_messages.push(subMessage)
      } else {
        const newGroup: SubMessageGroup = { type: 'file', sub_messages: [subMessage] }
        result.push(newGroup)
        lastGroup = newGroup
      }
    } else {
      const newGroup: SubMessageGroup = { type: 'normal', sub_messages: [subMessage] }
      result.push(newGroup)
      lastGroup = newGroup
    }
  }
  return result
})
</script>

<style scoped>
.sub-messages-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  position: relative;
  transition: max-height 0.25s ease-out;
  overflow: hidden;
}

.file-group-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.sub-messages-container.is-single {
  gap: 0;
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
  min-height: 40px;
}
.sub-messages-container.is-user.is-single {
  background-color: var(--el-color-primary-light-9);
}
.sub-messages-container.is-user {
  align-items: flex-end;
}
.sub-messages-container.is-user .file-group-container {
  justify-content: flex-end;
}

.sub-messages-container.is-single :deep(.sub-message-item) {
  border: none;
  background-color: transparent;
  overflow: visible;
}
.sub-messages-container.is-single :deep(.message-content) {
  padding: 0;
  max-height: none;
}
.sub-messages-container.is-single :deep(.message-content)::after {
  display: none;
}

.sub-messages-container.is-single-collapsed {
  max-height: 5em;
}
.sub-messages-container.is-single-collapsed::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  background: linear-gradient(to bottom, transparent, var(--color-background-soft));
  pointer-events: none;
}
.sub-messages-container.is-user.is-single-collapsed::after {
  background: linear-gradient(to bottom, transparent, var(--el-color-primary-light-9));
}

.initial-loading-placeholder {
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 10px 15px;
  border-radius: 8px;
  background-color: var(--color-background-soft);
}

.typing-indicator {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  height: 24px;
}
.typing-indicator span {
  height: 8px;
  width: 8px;
  border-radius: 50%;
  background-color: #909399;
  margin: 0 3px;
  animation: bounce 1.4s infinite ease-in-out both;
}
.typing-indicator span:nth-of-type(1) {
  animation-delay: -0.32s;
}
.typing-indicator span:nth-of-type(2) {
  animation-delay: -0.16s;
}
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}
</style>
