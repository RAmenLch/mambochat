<!-- frontend/mambo/src/components/chat/MessageItem.vue -->
<template>
  <div
    :id="id"
    class="message-item-container"
    :class="roleClass"
    @mouseenter="showActions = true"
    @mouseleave="showActions = false"
  >
    <div class="message-avatar">
      <el-avatar :src="avatarUrl || ''">
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <div class="message-body">
      <!-- User Message Area -->
      <template v-if="message.role === 'user'">
        <!-- Minimized SubMessages Area -->
        <MessageMinimizedArea
          :displayable-sub-messages="displayableSubMessages"
          :current-message-rank="currentMessageRank"
          :is-generating="message.status === 'generating'"
          :is-user="true"
          @restore="restoreSubMessage"
        />

        <!-- Main Content Area -->
        <MessageContentArea
          :message="message"
          :normal-sub-messages="normalSubMessages"
          :is-single-view-collapsed="isSingleViewCollapsed"
          :current-message-rank="currentMessageRank"
          :is-generating="message.status === 'generating'"
          :is-user="true"
          @edit="handleEditRequest"
          @edit-file="handleFileEdit"
          @copy="handleCopySingle"
        />
      </template>

      <!-- Assistant Message Area (Big Bubble) -->
      <template v-else-if="message.role === 'assistant'">
        <AssistantBubble
          :message="message"
          :is-generating="message.status === 'generating'"
          :current-message-rank="currentMessageRank"
          @edit="handleEditRequest"
          @copy="handleCopySingle"
          @open-tool-dialog="(toolId) => $emit('open-tool-dialog', message, toolId, 'single')"
        />
      </template>

      <!-- Zip History Bookmark and Card -->
      <div v-if="zipHistorySubMessage" class="zip-history-section">
        <div class="zip-history-bookmark" :class="zipBookmarkClass" @click="handleZipBookmarkClick">
          <el-icon :class="{ 'is-loading': zipStatus === 'generating' }">
            <component :is="zipBookmarkIcon" />
          </el-icon>
          <span>{{ zipBookmarkText }}</span>
        </div>
        <ZipHistoryCard
          v-if="isZipCardVisible && zipStatus !== 'generating'"
          :sub-message="zipHistorySubMessage"
          class="zip-history-card"
        />
      </div>

      <!-- Suggestion Chips -->
      <div v-if="isLastMessage && suggestionList.length > 0" class="suggestion-chips">
        <el-tag
          v-for="(suggestion, idx) in suggestionList"
          :key="idx"
          class="suggestion-item"
          type="info"
          effect="plain"
          round
          @click="$emit('suggestion-click', suggestion)"
        >
          {{ suggestion }}
        </el-tag>
      </div>

      <!-- Actions -->
      <MessageActions
        :message="message"
        :show-actions="showActions"
        :is-generating="message.status === 'generating'"
        :is-user="message.role === 'user'"
        :is-single-sub-message="isSingleSubMessage"
        :is-single-view-collapsed="isSingleViewCollapsed"
        :first-sub-message="firstSubMessage"
        :usage-sub-message="usageSubMessage"
        @regenerate="handleRegenerate"
        @toggle-collapse="toggleSingleViewCollapse"
        @edit-request="handleEditRequest"
        @copy-all="handleCopy"
        @duplicate-upto="$emit('duplicate-upto', message.id)"
        @compress-history="handleCompressHistory"
        @delete="handleDelete"
        @view-logs="$emit('view-logs', message.id)"
        @switch-branch="(targetId) => $emit('switch-branch', targetId)"
      />
    </div>
  </div>

  <MessageEditDialog
    v-model:visible="editDialogVisible"
    :initial-content="originalEditingContent"
    :can-regenerate="!editingFileInfo && message.role === 'user'"
    @save="handleSaveEdit"
    @save-and-resend="handleSaveAndResend"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { Message, SubMessage, SubMessageCreate, MessageStatus, FileResponse } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Cpu, Loading, CircleCheck, Clock } from '@element-plus/icons-vue'
import { copyToClipboard } from '@/utils/clipboard'
import { getFileContent, updateFileContent } from '@/api/fileService'

import MessageEditDialog from './dialogs/MessageEditDialog.vue'
import ZipHistoryCard from './ZipHistoryCard.vue'
import MessageMinimizedArea from './message/MessageMinimizedArea.vue'
import MessageContentArea from './message/MessageContentArea.vue'
import MessageActions from './message/MessageActions.vue'
import AssistantBubble from './message/AssistantBubble.vue'

interface EditPayload {
  content: string
  range?: { start: number; end: number }
  language?: string
  markup?: string
}

const props = defineProps<{
  id: string
  message: Message
  isLastMessage: boolean
}>()

const emit = defineEmits<{
  (e: 'suggestion-click', text: string): void
  (e: 'open-tool-dialog', message: Message, subMessageId: string, mode: 'review_all' | 'single'): void
  (e: 'view-logs', messageId: string): void
  (e: 'duplicate-upto', messageId: string): void
  (e: 'switch-branch', targetId: string): void
}>()

const { t } = useI18n()
const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const settingsStore = useSettingsStore()
const { globalSettings } = storeToRefs(settingsStore)
const { messageRecencyRanks } = storeToRefs(sessionStore)

const showActions = ref(false)
const isZipCardVisible = ref(false)

const currentMessageRank = computed(() => messageRecencyRanks.value.get(props.message.id) ?? 999)

const displayableSubMessages = computed(() =>
  props.message.sub_messages.filter(
    (sm) => sm.type !== 'Usage' && sm.type !== 'ZipHistory' && sm.type !== 'Suggest',
  ),
)

const normalSubMessages = computed(() =>
  displayableSubMessages.value.filter((sm) =>
    !sm.config?.is_minimal && sm.type !== 'McpTool' && sm.type !== 'ReviewTool'
  ),
)

const usageSubMessage = computed(() => {
  const usageMessages = props.message.sub_messages.filter((sm) => sm.type === 'Usage');
  if (usageMessages.length === 0) return undefined;
  return usageMessages.sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
});
const zipHistorySubMessage = computed(() => props.message.sub_messages.find((sm) => sm.type === 'ZipHistory'))
const suggestSubMessage = computed(() => props.message.sub_messages.find((sm) => sm.type === 'Suggest'))

const suggestionList = computed((): string[] => {
  if (!suggestSubMessage.value || !suggestSubMessage.value.content) return []
  try {
    const list = JSON.parse(suggestSubMessage.value.content)
    return Array.isArray(list) ? list : []
  } catch (e) { return [] }
})

const zipStatus = computed(() => {
  if (!zipHistorySubMessage.value) return null
  if (zipHistorySubMessage.value.status === 'generating') return 'generating'
  if (zipHistorySubMessage.value.config.zip_enable) return 'enabled'
  return 'disabled'
})

const zipBookmarkIcon = computed(() => {
  switch (zipStatus.value) {
    case 'generating': return Loading
    case 'enabled': return CircleCheck
    case 'disabled': return Clock
    default: return Clock
  }
})

const zipBookmarkText = computed(() => {
  switch (zipStatus.value) {
    case 'generating': return t('chat.message.zipGenerating')
    default: return t('chat.message.zipHistory')
  }
})

const zipBookmarkClass = computed(() => ({
  'is-generating': zipStatus.value === 'generating',
  'is-enabled': zipStatus.value === 'enabled',
  'is-disabled': zipStatus.value === 'disabled',
}))

const isSingleSubMessage = computed(() => props.message.role === 'user' && normalSubMessages.value.length === 1)
const firstSubMessage = computed(() => normalSubMessages.value[0])

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}))

const avatarUrl = computed(() => {
  if (props.message.role === 'user') return globalSettings.value.user_avatar_url
  if (props.message.role === 'assistant') return globalSettings.value.ai_avatar_url
  return null
})

const isSingleViewCollapsed = ref(firstSubMessage.value?.config?.is_collapsed || false)
watch(() => firstSubMessage.value?.config?.is_collapsed, (newValue) => {
  isSingleViewCollapsed.value = newValue || false
})

function toggleSingleViewCollapse() {
  if (!firstSubMessage.value) return
  const newCollapsedState = !isSingleViewCollapsed.value
  isSingleViewCollapsed.value = newCollapsedState
  interactionStore.updateSubMessage({
    subMessageId: firstSubMessage.value.id,
    data: { config: { ...firstSubMessage.value.config, is_collapsed: newCollapsedState } },
  })
}

// --- Edit Dialog Logic ---
const editDialogVisible = ref(false)
const editingSubMessage = ref<SubMessage | null>(null)
const originalEditingContent = ref('')
const editingFileInfo = ref<FileResponse | null>(null)
const editingRange = ref<{ start: number; end: number } | null>(null)
const editingMarkup = ref('```')
const editingLanguage = ref('')

watch(editDialogVisible, (newValue) => {
  if (!newValue) {
    editingSubMessage.value = null
    originalEditingContent.value = ''
    editingRange.value = null
    editingMarkup.value = '```'
    editingLanguage.value = ''
    editingFileInfo.value = null
  }
})

function handleEditRequest(subMessage: SubMessage | undefined, payload: EditPayload) {
  if (!subMessage || !payload) return
  editingSubMessage.value = subMessage
  originalEditingContent.value = payload.content
  editingFileInfo.value = null

  if (payload.range) {
    editingRange.value = payload.range
    editingMarkup.value = payload.markup || '```'
    editingLanguage.value = payload.language || ''
  } else {
    editingRange.value = null
    editingMarkup.value = '```'
    editingLanguage.value = ''
  }
  editDialogVisible.value = true
}

async function handleFileEdit(file: FileResponse) {
  try {
    const response = await getFileContent(file.id)
    editingFileInfo.value = file
    editingSubMessage.value = null
    editingRange.value = null
    originalEditingContent.value = response.content
    editDialogVisible.value = true
  } catch (error) {
    ElMessage.error(t('chat.message.fileLoadFailed'))
  }
}

function getUpdatedFullContent(newPartialContent: string): string {
  if (!editingSubMessage.value) return ''
  const fullOriginalContent = editingSubMessage.value.content
  if (!editingRange.value) return newPartialContent

  const { start, end } = editingRange.value
  const fence = editingMarkup.value
  const lang = editingLanguage.value
  const newBlockString = `${fence}${lang}\n${newPartialContent}\n${fence}`
  return fullOriginalContent.substring(0, start) + newBlockString + fullOriginalContent.substring(end)
}

async function handleSaveEdit(newContent: string) {
  const currentEditingFile = editingFileInfo.value
  if (currentEditingFile) {
    try {
      const updatedFile = await updateFileContent(currentEditingFile.id, newContent)
      const msg = sessionStore.currentChatMessages.find(m => m.id === props.message.id)
      if (msg) {
        const subMsg = msg.sub_messages.find(sm => sm.file_info?.id === currentEditingFile.id)
        if (subMsg) subMsg.file_info = updatedFile
      }
    } catch (error) {
      console.error('Failed to save file content:', error)
    }
    return
  }

  if (!editingSubMessage.value) return
  const updatedContent = getUpdatedFullContent(newContent)
  interactionStore.updateSubMessage({
    subMessageId: editingSubMessage.value.id,
    data: { content: updatedContent },
  })
}

function handleSaveAndResend(newContent: string) {
  if (!editingSubMessage.value) return
  const updatedContent = getUpdatedFullContent(newContent)
  const newSubMessages: SubMessageCreate[] = props.message.sub_messages.map((sm) => ({
    content: sm.id === editingSubMessage.value!.id ? updatedContent : sm.content,
    sortOrder: sm.sortOrder,
    type: sm.type,
    config: sm.config,
    status: 'completed' as MessageStatus,
  }))

  interactionStore.editMessageAndRegenerate({
    messageId: props.message.id,
    sub_messages: newSubMessages,
    resend: true,
  })
}

function handleRegenerate() {
  interactionStore.regenerateFrom(props.message.id)
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(t('chat.message.deleteConfirm'), t('common.action.delete'), {
      confirmButtonText: t('common.action.delete'),
      cancelButtonText: t('common.action.cancel'),
      type: 'warning',
    })
    await interactionStore.deleteMessage(props.message.id)
  } catch { /* User canceled */ }
}

async function handleCopySingle(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content)
    ElMessage.success(t('common.msg.copySuccess'))
  } catch { ElMessage.error(t('common.msg.copyFailed')) }
}

async function handleCopy() {
  const contentToCopy = normalSubMessages.value.map((sm) => sm.content).join('\n--------------------------\n')
  try {
    await copyToClipboard(contentToCopy)
    ElMessage.success(t('common.msg.copySuccess'))
  } catch { ElMessage.error(t('common.msg.copyFailed')) }
}

function handleCompressHistory() {
  interactionStore.initiateHistoryCompression(props.message.id)
  ElMessage.info(t('chat.message.compressHistoryStart'))
}

function handleZipBookmarkClick() {
  if (zipStatus.value === 'generating') return
  isZipCardVisible.value = !isZipCardVisible.value
}

function restoreSubMessage(subMessageId: string) {
  const subMessage = props.message.sub_messages.find((sm) => sm.id === subMessageId)
  if (!subMessage) return

  if (subMessage.type === 'McpTool' || subMessage.type === 'ReviewTool') {
    emit('open-tool-dialog', props.message, subMessageId, 'single')
    return
  }

  interactionStore.updateSubMessage({
    subMessageId: subMessageId,
    data: { config: { ...subMessage.config, is_minimal: false } },
  })
}
</script>

<style scoped>
.message-item-container {
  display: flex;
  align-items: flex-start;
  margin-bottom: 20px;
  max-width: 90%;
}
.message-avatar {
  flex-shrink: 0;
  margin-right: 12px;
  margin-top: 2px;
}
.message-body {
  display: flex;
  flex-direction: column;
  min-width: 80px;
  width: 100%;
}

.zip-history-section {
  margin-top: 8px;
}

.zip-history-bookmark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}

.zip-history-bookmark.is-enabled {
  background-color: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
  color: var(--el-color-success);
}
.zip-history-bookmark.is-enabled:hover {
  background-color: var(--el-color-success-light-8);
}

.zip-history-bookmark.is-disabled {
  background-color: var(--el-color-info-light-9);
  border-color: var(--el-color-info-light-7);
  color: var(--el-color-info);
}
.zip-history-bookmark.is-disabled:hover {
  background-color: var(--el-color-info-light-8);
}

.zip-history-bookmark.is-generating {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
  cursor: default;
}

.zip-history-bookmark .el-icon.is-loading {
  animation: rotating 2s linear infinite;
}

.zip-history-card {
  margin-top: 8px;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.suggestion-item {
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  border-color: var(--el-border-color);
  background-color: var(--color-background);
}
.suggestion-item:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}

.message-item-container.is-user {
  flex-direction: row-reverse;
  margin-left: auto;
}
.is-user .message-avatar {
  margin-right: 0;
  margin-left: 12px;
}
</style>
