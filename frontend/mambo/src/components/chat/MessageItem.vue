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
      <!-- Minimized SubMessages Area -->
      <div v-if="minimizedSubMessages.length > 0" class="minimized-sub-messages-container">
        <el-tooltip
          v-for="subMessage in minimizedSubMessages"
          :key="subMessage.id"
          placement="top"
          :show-after="300"
        >
          <template #content>
            <div style="max-width: 300px; white-space: pre-wrap">
              {{ getMinimizedTooltipContent(subMessage) }}
            </div>
          </template>
          <div
            class="minimized-item"
            :class="{
              'is-inactive': isSubMessageInactive(subMessage),
              'has-review': hasReview(subMessage)
            }"
            @click="restoreSubMessage(subMessage.id)"
          >
            <!-- MCP Tool / Review Tool Specific Minimized View -->
            <template v-if="subMessage.type === 'McpTool' || subMessage.type === 'ReviewTool'">
              <el-icon>
                <Warning v-if="subMessage.type === 'ReviewTool'" style="color: var(--el-color-warning)" />
                <Loading
                  v-else-if="getMinimizedMcpInfo(subMessage).status === 'generating'"
                  class="is-loading"
                />
                <CircleCheck
                  v-else-if="getMinimizedMcpInfo(subMessage).status === 'success'"
                  style="color: var(--el-color-success)"
                />
                <CircleClose v-else style="color: var(--el-color-error)" />
              </el-icon>
              <span class="minimized-item-title">
                {{ subMessage.type === 'ReviewTool' ? $t('chat.message.pendingReview', '待审核') : $t('chat.message.toolCall') }}
              </span>
            </template>
            <!-- Generic Minimized View -->
            <template v-else>
              <el-icon><Document /></el-icon>
              <span class="minimized-item-title">{{
                getPartitionTitleForMinimized(subMessage)
              }}</span>
            </template>
          </div>
        </el-tooltip>
      </div>

      <div
        class="sub-messages-container"
        :class="{
          'is-single': useSinglePartitionView,
          'is-single-collapsed': useSinglePartitionView && isSingleViewCollapsed,
        }"
      >
        <!-- Display a loading indicator when the message is generating but has no sub-messages yet -->
        <div
          v-if="message.status === 'generating' && normalSubMessages.length === 0"
          class="initial-loading-placeholder"
        >
          <div class="typing-indicator"><span></span><span></span><span></span></div>
        </div>

        <template v-for="(group, groupIndex) in groupedSubMessages" :key="groupIndex">
          <!-- Render a group of files with a flex layout -->
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
              @edit="(payload) => handleEditRequest(subMessage, payload)"
              @edit-file="handleFileEdit"
              @copy="handleCopySingle(subMessage)"
            />
          </div>
          <!-- Render a single non-file sub-message -->
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
            @edit="(payload) => handleEditRequest(group.sub_messages[0], payload)"
            @copy="handleCopySingle(group.sub_messages[0])"
          />
        </template>
      </div>

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

      <div
        class="message-actions"
        :class="{ 'is-visible': showActions && message.status !== 'generating' }"
      >
        <el-tooltip :content="$t('chat.message.regenerate')" placement="top" :show-after="500">
          <el-button
            :icon="message.role === 'user' ? RefreshLeft : Refresh"
            circle
            size="small"
            @click="handleRegenerate"
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
            @click="toggleSingleViewCollapse"
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
            @click="handleEditRequest(firstSubMessage, { content: firstSubMessage.content })"
          />
        </el-tooltip>

        <el-tooltip
          :content="isSingleSubMessage ? $t('common.action.copy') : $t('chat.message.copyAll')"
          placement="top"
          :show-after="500"
        >
          <el-button :icon="CopyDocument" circle size="small" @click="handleCopy" />
        </el-tooltip>

        <el-tooltip
          v-if="message.role === 'assistant'"
          :content="$t('chat.message.compressHistory')"
          placement="top"
          :show-after="500"
        >
          <el-button :icon="Clock" circle size="small" @click="handleCompressHistory" />
        </el-tooltip>

        <el-tooltip :content="$t('common.action.delete')" placement="top" :show-after="500">
          <el-button :icon="Delete" circle size="small" type="danger" plain @click="handleDelete" />
        </el-tooltip>

        <UsageInfo
          v-if="usageSubMessage"
          :usage-sub-message="usageSubMessage"
          class="usage-info-component"
        />
      </div>
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
import type {
  Message,
  SubMessage,
  SubMessageCreate,
  MessageStatus,
  McpToolContent,
  FileResponse,
  ReviewToolContent
} from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User,
  Cpu,
  Refresh,
  RefreshLeft,
  Delete,
  Edit,
  CopyDocument,
  ArrowUpBold,
  ArrowDownBold,
  Clock,
  Document,
  Loading,
  CircleCheck,
  CircleClose,
  Warning
} from '@element-plus/icons-vue'
import SubMessageItem from './SubMessageItem.vue'
import MessageEditDialog from './dialogs/MessageEditDialog.vue'
import UsageInfo from './UsageInfo.vue'
import ZipHistoryCard from './ZipHistoryCard.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { getFileContent, updateFileContent } from '@/api/fileService'

interface SubMessageGroup {
  type: 'file' | 'normal'
  sub_messages: SubMessage[]
}

interface MinimizedMcpInfo {
  status: 'generating' | 'success' | 'error'
}

interface EditPayload {
  content: string
  range?: {
    start: number
    end: number
  }
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
  (e: 'open-tool-dialog', message: Message, subMessageId: string): void
}>()

const { t } = useI18n()
const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const settingsStore = useSettingsStore()
const { globalSettings } = storeToRefs(settingsStore)
const { messageRecencyRanks } = storeToRefs(sessionStore)

const showActions = ref(false)
const isZipCardVisible = ref(false)

const currentMessageRank = computed(() => {
  return messageRecencyRanks.value.get(props.message.id) ?? 999
})

function isSubMessageInactive(subMessage: SubMessage): boolean {
  if (props.message.status === 'generating') return false

  const cpl = subMessage.config?.context_participation_length
  if (cpl === undefined || cpl === null) return false
  if (cpl === 0) return true
  if (cpl > 0) {
    return currentMessageRank.value > cpl
  }
  return false
}

const displayableSubMessages = computed(() =>
  props.message.sub_messages.filter(
    (sm) => sm.type !== 'Usage' && sm.type !== 'ZipHistory' && sm.type !== 'Suggest',
  ),
)

const reviewedToolCallIds = computed(() => {
  const ids = new Set<string>();
  displayableSubMessages.value.forEach(sm => {
    if (sm.type === 'ReviewTool') {
      try {
        const content = JSON.parse(sm.content) as ReviewToolContent;
        ids.add(content.tool_call_id);
      } catch {}
    }
  });
  return ids;
});

function hasReview(subMessage: SubMessage): boolean {
  if (subMessage.type !== 'McpTool') return false;
  try {
    const content = JSON.parse(subMessage.content) as McpToolContent;
    return reviewedToolCallIds.value.has(content.tool_call_id);
  } catch { return false; }
}

const minimizedSubMessages = computed(() => {
  const allSubMessages = displayableSubMessages.value;

  const tools = allSubMessages.filter(sm => sm.type === 'McpTool' || sm.type === 'ReviewTool');

  const mcpToolCallIds = new Set(
    tools.filter(sm => sm.type === 'McpTool')
         .map(sm => {
           try {
             const content = JSON.parse(sm.content) as McpToolContent;
             return content.tool_call_id;
           } catch { return null; }
         })
         .filter(Boolean)
  );

  const deduplicatedTools = tools.filter(sm => {
    if (sm.type === 'ReviewTool') {
      try {
        const content = JSON.parse(sm.content) as ReviewToolContent;
        if (content.decision) {
          return false;
        }
        return !mcpToolCallIds.has(content.tool_call_id);
      } catch { return true; }
    }
    return true;
  });

  const normalMinimized = allSubMessages.filter(sm =>
    sm.config?.is_minimal === true && sm.type !== 'McpTool' && sm.type !== 'ReviewTool'
  );

  return [...normalMinimized, ...deduplicatedTools].sort((a, b) => a.sortOrder - b.sortOrder);
});

const normalSubMessages = computed(() =>
  displayableSubMessages.value.filter((sm) =>
    !sm.config?.is_minimal && sm.type !== 'McpTool' && sm.type !== 'ReviewTool'
  ),
)

const isLastVisibleSubMessage = computed(() => normalSubMessages.value.length === 1)

const usageSubMessage = computed(() => props.message.sub_messages.find((sm) => sm.type === 'Usage'))

const zipHistorySubMessage = computed(() =>
  props.message.sub_messages.find((sm) => sm.type === 'ZipHistory'),
)

const suggestSubMessage = computed(() =>
  props.message.sub_messages.find((sm) => sm.type === 'Suggest'),
)

const suggestionList = computed((): string[] => {
  if (!suggestSubMessage.value || !suggestSubMessage.value.content) return []
  try {
    const list = JSON.parse(suggestSubMessage.value.content)
    return Array.isArray(list) ? list : []
  } catch (e) {
    return []
  }
})

const zipStatus = computed(() => {
  if (!zipHistorySubMessage.value) return null
  if (zipHistorySubMessage.value.status === 'generating') return 'generating'
  if (zipHistorySubMessage.value.config.zip_enable) return 'enabled'
  return 'disabled'
})

const zipBookmarkIcon = computed(() => {
  switch (zipStatus.value) {
    case 'generating':
      return Loading
    case 'enabled':
      return CircleCheck
    case 'disabled':
      return Clock
    default:
      return Clock
  }
})

const zipBookmarkText = computed(() => {
  switch (zipStatus.value) {
    case 'generating':
      return t('chat.message.zipGenerating')
    case 'enabled':
      return t('chat.message.zipHistory')
    case 'disabled':
      return t('chat.message.zipHistory')
    default:
      return t('chat.message.zipHistory')
  }
})

const zipBookmarkClass = computed(() => ({
  'is-generating': zipStatus.value === 'generating',
  'is-enabled': zipStatus.value === 'enabled',
  'is-disabled': zipStatus.value === 'disabled',
}))

const isSingleSubMessage = computed(() => normalSubMessages.value.length === 1)
const firstSubMessage = computed(() => normalSubMessages.value[0])

const groupedSubMessages = computed((): SubMessageGroup[] => {
  if (!normalSubMessages.value || normalSubMessages.value.length === 0) {
    return []
  }

  const result: SubMessageGroup[] = []
  let lastGroup: SubMessageGroup | null = null

  for (const subMessage of normalSubMessages.value) {
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

const useSinglePartitionView = computed(() => {
  return normalSubMessages.value.length === 1 && firstSubMessage.value?.type === 'Normal'
})

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}))

const avatarUrl = computed(() => {
  if (props.message.role === 'user') {
    return globalSettings.value.user_avatar_url
  }
  if (props.message.role === 'assistant') {
    return globalSettings.value.ai_avatar_url
  }
  return null
})

const isSingleViewCollapsed = ref(firstSubMessage.value?.config?.is_collapsed || false)
watch(
  () => firstSubMessage.value?.config?.is_collapsed,
  (newValue) => {
    isSingleViewCollapsed.value = newValue || false
  },
)

function toggleSingleViewCollapse() {
  if (!firstSubMessage.value) return
  const newCollapsedState = !isSingleViewCollapsed.value
  isSingleViewCollapsed.value = newCollapsedState
  interactionStore.updateSubMessage({
    subMessageId: firstSubMessage.value.id,
    data: { config: { ...firstSubMessage.value.config, is_collapsed: newCollapsedState } },
  })
}

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

function handleEditRequest(subMessage: SubMessage, payload: EditPayload) {
  if (!subMessage || !payload) {
    return
  }

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

  if (!editingRange.value) {
    return newPartialContent
  }

  const { start, end } = editingRange.value
  const fence = editingMarkup.value
  const lang = editingLanguage.value
  const newBlockString = `${fence}${lang}\n${newPartialContent}\n${fence}`

  return (
    fullOriginalContent.substring(0, start) + newBlockString + fullOriginalContent.substring(end)
  )
}

async function handleSaveEdit(newContent: string) {
  const currentEditingFile = editingFileInfo.value;

  if (currentEditingFile) {
    try {
      const updatedFile = await updateFileContent(currentEditingFile.id, newContent)

      const msg = sessionStore.currentChatMessages.find(m => m.id === props.message.id)
      if (msg) {
        const subMsg = msg.sub_messages.find(sm => sm.file_info?.id === currentEditingFile.id)
        if (subMsg) {
          subMsg.file_info = updatedFile
        }
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

  const newSubMessages: SubMessageCreate[] = props.message.sub_messages.map((sm) => {
    return {
      content: sm.id === editingSubMessage.value!.id ? updatedContent : sm.content,
      sortOrder: sm.sortOrder,
      type: sm.type,
      config: sm.config,
      status: 'completed' as MessageStatus,
    }
  })

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
  } catch {
    /* User canceled */
  }
}

async function handleCopySingle(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

async function handleCopy() {
  const contentToCopy = normalSubMessages.value
    .map((sm) => {
      return sm.content
    })
    .join('\n--------------------------\n')

  try {
    await copyToClipboard(contentToCopy)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

function handleCompressHistory() {
  interactionStore.initiateHistoryCompression(props.message.id)
  ElMessage.info('已开始在后台压缩历史对话，您可以继续聊天。')
}

function handleZipBookmarkClick() {
  if (zipStatus.value === 'generating') return
  isZipCardVisible.value = !isZipCardVisible.value
}

function restoreSubMessage(subMessageId: string) {
  const subMessage = props.message.sub_messages.find((sm) => sm.id === subMessageId)
  if (!subMessage) return

  if (subMessage.type === 'McpTool' || subMessage.type === 'ReviewTool') {
    emit('open-tool-dialog', props.message, subMessageId);
    return;
  }

  interactionStore.updateSubMessage({
    subMessageId: subMessageId,
    data: { config: { ...subMessage.config, is_minimal: false } },
  })
}

function getPartitionTitleForMinimized(subMessage: SubMessage): string {
  if (subMessage.type === 'Reasoning') return t('chat.message.reasoning')
  if (subMessage.type === 'File') return '文件'
  if (subMessage.type === 'Normal') {
    const normalSubMessages = displayableSubMessages.value.filter((sm) => sm.type === 'Normal')
    if (normalSubMessages.length <= 1) return t('chat.message.content')
    const normalIndex = normalSubMessages.findIndex((sm) => sm.id === subMessage.id)
    if (normalIndex !== -1) {
      return `${t('chat.message.content')}(${normalIndex + 1})`
    }
  }
  return '分区'
}

function getMinimizedMcpInfo(subMessage: SubMessage): MinimizedMcpInfo {
  if (subMessage.status === 'generating') {
    return { status: 'generating' }
  }
  try {
    const content = JSON.parse(subMessage.content)
    return {
      status: content.is_error ? 'error' : 'success',
    }
  } catch (e) {
    return { status: 'error' }
  }
}

function getMinimizedTooltipContent(subMessage: SubMessage): string {
  if (subMessage.type === 'McpTool' || subMessage.type === 'ReviewTool') {
    try {
      const content = JSON.parse(subMessage.content)
      let argsStr = ''
      if (typeof content.arguments === 'string') {
        argsStr = content.arguments
      } else if (typeof content.arguments === 'object') {
        argsStr = JSON.stringify(content.arguments)
      }
      const args = argsStr ? `Args: ${argsStr}` : ''
      return `${t('chat.message.toolCall')}: ${content.name || 'Unknown'}\n${args}`.trim()
    } catch {
      return t('chat.message.toolCall')
    }
  }
  return subMessage.content.substring(0, 100) + (subMessage.content.length > 100 ? '...' : '')
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
}
.minimized-sub-messages-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}
.minimized-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 6px;
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-light);
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.minimized-item .el-icon.is-loading {
  animation: rotating 2s linear infinite;
}
.minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.minimized-item.is-inactive {
  opacity: 1;
  border-style: dashed;
  background-color: var(--el-fill-color-lighter);
  color: var(--el-text-color-regular);
}
.minimized-item.is-inactive:hover {
  border-color: var(--el-text-color-placeholder);
  color: var(--el-text-color-regular);
}

.is-user .minimized-item {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-8);
}
.is-user .minimized-item:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.is-user .minimized-item.is-inactive {
  opacity: 1;
  border-style: dashed;
  border-color: var(--el-color-primary-light-5);
  background-color: var(--el-color-primary-light-9);
}
.is-user .minimized-item.is-inactive:hover {
  border-color: var(--el-color-primary-light-3);
  color: var(--el-color-primary-dark-2);
}

.minimized-item.has-review {
  border-color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}
.minimized-item.has-review:hover {
  border-color: var(--el-color-warning-dark-2);
  color: var(--el-color-warning-dark-2);
}
.is-user .minimized-item.has-review {
  border-color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-8);
}

.minimized-item-title {
  white-space: nowrap;
}

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
.is-user .sub-messages-container.is-single {
  background-color: var(--el-color-primary-light-9);
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
.is-user .sub-messages-container.is-single-collapsed::after {
  background: linear-gradient(to bottom, transparent, var(--el-color-primary-light-9));
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

.message-actions {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  opacity: 0;
  visibility: hidden;
  min-height: 24px;
  transition:
    opacity 0.2s,
    visibility 0.2s;
  align-items: center;
}
.message-actions.is-visible {
  opacity: 1;
  visibility: visible;
}
.message-item-container.is-user {
  flex-direction: row-reverse;
  margin-left: auto;
}
.is-user .message-avatar {
  margin-right: 0;
  margin-left: 12px;
}
.is-user .sub-messages-container {
  align-items: flex-end;
}
.is-user .minimized-sub-messages-container {
  justify-content: flex-end;
}
.is-user .file-group-container {
  justify-content: flex-end;
}
.is-user .message-actions {
  justify-content: flex-end;
}

.usage-info-component {
  margin-left: 8px;
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
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}
</style>
