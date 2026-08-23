<!-- frontend/mambo/src/mobile/components/chat/MessageItem.vue -->
<template>
  <div
    :id="id"
    class="mobile-message-item"
    :class="roleClass"
    @click="clearActions"
    @touchstart="handleTouchStart"
    @touchend="handleTouchEnd"
    @touchmove="handleTouchMove"
  >

    <!-- 用户消息：右侧气泡 -->
    <template v-if="message.role === 'user'">
      <div class="message-avatar">
        <el-avatar :size="28" :src="avatarUrl || ''">
          <el-icon :size="16"><User /></el-icon>
        </el-avatar>
      </div>

      <div class="message-body user-body">
        <div v-if="minimizedSubMessages.length > 0" class="minimized-bar">
          <el-tag
            v-for="sub in minimizedSubMessages"
            :key="sub.id"
            size="small"
            type="info"
            :class="{ 'is-inactive': isSubMessageInactive(sub) }"
            @click.stop="restoreSubMessage(sub.id)"
          >
            <el-icon><Document /></el-icon>
          </el-tag>
        </div>

        <div class="sub-messages-container">
          <div
            v-if="message.status === 'generating' && normalSubMessages.length === 0"
            class="bubble user-bubble typing-bubble"
          >
            <div class="typing-indicator"><span></span><span></span><span></span></div>
          </div>

          <template v-for="(subMessage, index) in normalSubMessages" :key="subMessage.id">
            <div
              class="bubble user-bubble"
              :class="{ 'is-first': index === 0, 'is-last': index === normalSubMessages.length - 1 }"
              @click.stop="toggleActions(subMessage.id)"
            >
              <SubMessageItem
                :id="`sub-msg-${subMessage.id}`"
                :sub-message="subMessage"
                :parent-message="message"
                :index="index + 1"
                :show-header="normalSubMessages.length > 1 || subMessage.type !== 'Normal'"
                :is-inactive="isSubMessageInactive(subMessage)"
                @edit="(payload) => handleEditRequest(subMessage, payload)"
                @edit-file="handleFileEdit"
                @copy="handleCopySingle(subMessage)"
              />
            </div>
          </template>
        </div>
      </div>

      <div
        v-if="activeSubMessageId && message.status !== 'generating'"
        class="inline-actions user-inline-actions"
        @click.stop
      >
        <button class="action-btn" @click="handleEditSpecific(activeSubMessageId)">
          <el-icon :size="16"><Edit /></el-icon>
        </button>
        <button class="action-btn" @click="handleCopySpecific(activeSubMessageId)">
          <el-icon :size="16"><CopyDocument /></el-icon>
        </button>
        <button class="action-btn danger" @click="handleDeleteMessage">
          <el-icon :size="16"><Delete /></el-icon>
        </button>
      </div>
    </template>

    <!-- AI 消息：左侧气泡 -->
    <template v-else-if="message.role === 'assistant'">
      <div class="message-avatar">
        <el-avatar :size="28" :src="avatarUrl || ''">
          <el-icon :size="16"><Cpu /></el-icon>
        </el-avatar>
      </div>

      <div class="message-body assistant-body">
        <MobileAssistantBubble
          :message="message"
          :is-generating="message.status === 'generating'"
          :current-message-rank="currentMessageRank"
          @edit="handleEditRequest"
          @edit-file="handleFileEdit"
          @copy="handleCopySingle"
          @open-tool-dialog="(toolId) => $emit('open-tool-dialog', message, toolId, 'single')"
          @toggle-actions="toggleActions"
        >

          <template #actions="{ subMessageId }">
            <div
              v-if="activeSubMessageId === subMessageId && message.status !== 'generating'"
              class="inline-actions"
              @click.stop
            >
              <div v-if="hasSiblings" class="branch-switcher">
                <button class="action-btn" :disabled="!canGoPrev" @click="handlePrev">
                  <el-icon :size="16"><ArrowLeft /></el-icon>
                </button>
                <span class="branch-text">{{ currentIndex }}/{{ totalSiblings }}</span>
                <button class="action-btn" :disabled="!canGoNext" @click="handleNext">
                  <el-icon :size="16"><ArrowRight /></el-icon>
                </button>
              </div>
              <UsageInfo
                v-if="usageSubMessage"
                :usage-sub-message="usageSubMessage"
                :max-context-tokens="maxContextTokens"
                :start-time="message.createdAt"
                :end-time="usageSubMessage.createdAt"
                :is-generating="false"
              />
              <button class="action-btn" @click="handleEditSpecific(subMessageId)">
                <el-icon :size="16"><Edit /></el-icon>
              </button>
              <button class="action-btn" @click="handleCopySpecific(subMessageId)">
                <el-icon :size="16"><CopyDocument /></el-icon>
              </button>
              <button class="action-btn" @click="handleRegenerate">
                <el-icon :size="16"><RefreshRight /></el-icon>
              </button>
              <button class="action-btn danger" @click="handleDeleteMessage">
                <el-icon :size="16"><Delete /></el-icon>
              </button>
            </div>
          </template>
        </MobileAssistantBubble>

        <div v-if="zipHistorySubMessage" class="zip-history-section">
          <div class="zip-history-bookmark" :class="zipBookmarkClass" @click.stop="handleZipBookmarkClick">
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

        <div class="suggestion-area" v-if="message.status !== 'generating' && isLastMessage && suggestionList.length > 0">
          <button
            v-for="(suggestion, idx) in suggestionList"
            :key="idx"
            class="suggestion-chip"
            @click.stop="$emit('suggestion-click', suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>
      </div>
    </template>

    <!-- 长按操作面板 -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="actionSheetVisible" class="action-sheet-overlay" @click="closeActionSheet">
          <div class="action-sheet" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-actions">
              <button
                v-for="action in currentActions"
                :key="action.key"
                class="sheet-action-btn"
                :class="{ danger: action.danger }"
                @click="action.handler()"
              >
                <el-icon :size="20"><component :is="action.icon" /></el-icon>
                <span>{{ action.label }}</span>
              </button>
            </div>
            <button class="sheet-cancel" @click="closeActionSheet">{{ $t('common.action.cancel') }}</button>
          </div>
        </div>
      </Transition>
    </Teleport>

    <MobileMessageEditDialog
      v-model:visible="editDialogVisible"
      :initial-content="originalEditingContent"
      :is-user-message="message.role === 'user'"
      @save="handleSaveEdit"
      @save-and-resend="handleSaveAndResend"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { Message, SubMessage, SubMessageCreate, MessageStatus, FileResponse } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useAgentStore } from '@/stores/agentStore'
import { useProviderStore } from '@/stores/providerStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User, Cpu, Document, CopyDocument, RefreshRight, Delete, Edit, Clock, Loading, CircleCheck, ArrowLeft, ArrowRight
} from '@element-plus/icons-vue'
import SubMessageItem from './SubMessageItem.vue'
import ZipHistoryCard from './ZipHistoryCard.vue'
import MobileAssistantBubble from './message/MobileAssistantBubble.vue'
import MobileMessageEditDialog from '@/mobile/components/chat/dialogs/MobileMessageEditDialog.vue'
import UsageInfo from '@/components/chat/UsageInfo.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { getFileContent, updateFileContent } from '@/api/fileService'
import { type ParsedBlock } from '@/utils/markdownParser'
import { resolveFileUrl } from '@/services/electronUrl'

interface ActionItem {
  key: string
  label: string
  icon: Component
  danger?: boolean
  handler: () => void
}

const props = defineProps<{
  id?: string
  message: Message
  isLastMessage: boolean
}>()

const emit = defineEmits<{
  (e: 'suggestion-click', text: string): void
  (e: 'switch-branch', targetId: string): void
  (e: 'open-tool-dialog', message: Message, subMessageId: string, mode: 'review_all' | 'single'): void
}>()

const { t } = useI18n()
const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const settingsStore = useSettingsStore()
const agentStore = useAgentStore()
const providerStore = useProviderStore()

const { globalSettings } = storeToRefs(settingsStore)
const { messageRecencyRanks } = storeToRefs(sessionStore)

const activeSubMessageId = ref<string | null>(null)
const actionSheetVisible = ref(false)
const currentActions = ref<ActionItem[]>([])

let longPressTimer: ReturnType<typeof setTimeout> | null = null
let touchStartX = 0
let touchStartY = 0
let hasMoved = false

function handleTouchStart(e: TouchEvent) {
  hasMoved = false
  touchStartX = e.touches[0].clientX
  touchStartY = e.touches[0].clientY
  longPressTimer = setTimeout(() => {
    if (!hasMoved) {
      showActionSheet()
    }
  }, 500)
}

function handleTouchMove(e: TouchEvent) {
  const dx = Math.abs(e.touches[0].clientX - touchStartX)
  const dy = Math.abs(e.touches[0].clientY - touchStartY)
  if (dx > 8 || dy > 8) {
    hasMoved = true
    if (longPressTimer) clearTimeout(longPressTimer)
  }
}

function handleTouchEnd() {
  if (longPressTimer) clearTimeout(longPressTimer)
}

function showActionSheet() {
  const actions: ActionItem[] = []

  if (props.message.role === 'user') {
    actions.push({
      key: 'edit',
      label: t('common.action.edit'),
      icon: Edit,
      handler: () => {
        if (normalSubMessages.value.length > 0) {
          const firstNormal = normalSubMessages.value[0]
          handleEditRequest(firstNormal, { content: firstNormal.content })
        }
        closeActionSheet()
      }
    })
  }

  if (props.message.role === 'assistant') {
    if (hasSiblings.value) {
      actions.push({
        key: 'prev-branch',
        label: t('chat.message.prevBranch'),
        icon: ArrowLeft,
        handler: () => { handlePrev(); closeActionSheet() }
      })
      actions.push({
        key: 'next-branch',
        label: t('chat.message.nextBranch'),
        icon: ArrowRight,
        handler: () => { handleNext(); closeActionSheet() }
      })
    }
    actions.push({
      key: 'regenerate',
      label: t('chat.message.regenerate'),
      icon: RefreshRight,
      handler: () => { handleRegenerate(); closeActionSheet() }
    })
  }

  actions.push({
    key: 'copy',
    label: t('common.action.copy'),
    icon: CopyDocument,
    handler: () => {
      const text = normalSubMessages.value.map(sm => sm.content).join('\n')
      copyToClipboard(text).then(() => ElMessage.success(t('chat.message.codeCopied')))
      closeActionSheet()
    }
  })

  if (props.message.role === 'assistant') {
    actions.push({
      key: 'compress',
      label: t('chat.message.compressHistory'),
      icon: Clock,
      handler: () => { handleCompressHistory(); closeActionSheet() }
    })
  }

  actions.push({
    key: 'delete',
    label: t('common.action.delete'),
    icon: Delete,
    danger: true,
    handler: () => { handleDeleteMessage(); closeActionSheet() }
  })

  currentActions.value = actions
  actionSheetVisible.value = true
}

function closeActionSheet() {
  actionSheetVisible.value = false
}

const toggleActions = (id?: string) => {
  if (props.message.status === 'generating') return
  if (!id) return
  if (activeSubMessageId.value === id) {
    activeSubMessageId.value = null
  } else {
    activeSubMessageId.value = id
  }
}

const clearActions = () => {
  activeSubMessageId.value = null
}

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

const hasSiblings = computed(() => props.message.sibling_ids && props.message.sibling_ids.length > 1)
const currentIndex = computed(() => props.message.sibling_index + 1)
const totalSiblings = computed(() => props.message.sibling_ids ? props.message.sibling_ids.length : 0)
const canGoPrev = computed(() => props.message.sibling_index > 0 && props.message.status !== 'generating')
const canGoNext = computed(() => props.message.sibling_ids && props.message.sibling_index < props.message.sibling_ids.length - 1 && props.message.status !== 'generating')

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

const displayableSubMessages = computed(() =>
  props.message.sub_messages.filter(
    (sm) => sm.type !== 'Usage' && sm.type !== 'ZipHistory' && sm.type !== 'Suggest',
  ),
)

const minimizedSubMessages = computed(() =>
  displayableSubMessages.value.filter((sm) => sm.config?.is_minimal === true),
)

const normalSubMessages = computed(() =>
  displayableSubMessages.value.filter((sm) => !sm.config?.is_minimal),
)

const suggestSubMessage = computed(() =>
  props.message.sub_messages.find((sm) => sm.type === 'Suggest'),
)

const suggestionList = computed((): string[] => {
  if (!suggestSubMessage.value?.content) return []
  try {
    return JSON.parse(suggestSubMessage.value.content)
  } catch {
    return []
  }
})

const zipHistorySubMessage = computed(() =>
  props.message.sub_messages.find((sm) => sm.type === 'ZipHistory'),
)

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
    default: return Clock
  }
})

const zipBookmarkText = computed(() => {
  switch (zipStatus.value) {
    case 'generating': return t('chat.message.zipGenerating')
    case 'enabled': return t('chat.message.zipHistory')
    case 'disabled': return t('chat.message.zipHistory')
    default: return t('chat.message.zipHistory')
  }
})

const zipBookmarkClass = computed(() => ({
  'is-generating': zipStatus.value === 'generating',
  'is-enabled': zipStatus.value === 'enabled',
  'is-disabled': zipStatus.value === 'disabled',
}))

const isZipCardVisible = ref(false)

const roleClass = computed(() => ({
  'is-user': props.message.role === 'user',
  'is-assistant': props.message.role === 'assistant',
}))

const avatarUrl = computed(() => {
  if (props.message.role === 'user') {
    return resolveFileUrl(globalSettings.value.user_avatar_url)
  }
  if (props.message.role === 'assistant') {
    // Mini_Avatar 模式：优先使用 show 工具设置的图片作为头像
    const miniAvatarSub = props.message.sub_messages.find(
      sm => sm.type === 'File' &&
        sm.config?.show_tool_mode === 'Mini_Avatar' &&
        sm.file_info?.mime_type?.startsWith('image/')
    )
    if (miniAvatarSub?.file_info?.url) {
      return miniAvatarSub.file_info.url
    }

    const currentChat = sessionStore.currentChat
    if (currentChat?.chatMode === 'agent' && currentChat.agentId) {
      const agent = agentStore.allAgents.find(a => a.id === currentChat.agentId)
      if (agent && agent.agentAvatarUrl) {
        return resolveFileUrl(agent.agentAvatarUrl)
      }
    }
    return resolveFileUrl(globalSettings.value.ai_avatar_url)
  }
  return null
})

const usageSubMessage = computed(() => {
  const usageMessages = props.message.sub_messages.filter((sm) => sm.type === 'Usage')
  if (usageMessages.length === 0) return undefined
  return usageMessages.sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0]
})

function handleShowUsage() {
  if (!usageSubMessage.value) return
  try {
    const usage = JSON.parse(usageSubMessage.value.content)
    const prompt = usage.prompt_tokens ?? 0
    const completion = usage.completion_tokens ?? 0
    const total = usage.total_tokens ?? (prompt + completion)
    ElMessage.info(`Tokens - Prompt: ${prompt}, Completion: ${completion}, Total: ${total}`)
  } catch {
    ElMessage.info(usageSubMessage.value.content)
  }
}

const maxContextTokens = computed(() => {
  const chat = sessionStore.currentChat
  if (!chat?.aiModelId) return undefined
  const model = providerStore.allModels.find(m => m.id === chat.aiModelId)
  return model?.meta_config?.context_length ?? undefined
})

const editDialogVisible = ref(false)
const editingSubMessage = ref<SubMessage | null>(null)
const editingFileInfo = ref<FileResponse | null>(null)
const originalEditingContent = ref('')
const editingRange = ref<{ start: number; end: number } | null>(null)
const editingMarkup = ref('```')
const editingLanguage = ref('')

watch(editDialogVisible, (newValue) => {
  if (!newValue) {
    editingSubMessage.value = null
    editingFileInfo.value = null
    originalEditingContent.value = ''
    editingRange.value = null
    editingMarkup.value = '```'
    editingLanguage.value = ''
  }
})

function handleEditRequest(
  subMessage: SubMessage,
  payload: { content: string; range?: ParsedBlock['range']; language?: string; markup?: string },
) {
  editingSubMessage.value = subMessage
  originalEditingContent.value = payload.content
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

function handleEditSpecific(id: string) {
  const targetSub = props.message.sub_messages.find((sm) => sm.id === id)
  if (targetSub) {
    handleEditRequest(targetSub, { content: targetSub.content })
  } else if (normalSubMessages.value.length > 0) {
    const firstNormal = normalSubMessages.value[0]
    handleEditRequest(firstNormal, { content: firstNormal.content })
  }
  activeSubMessageId.value = null
}

function getUpdatedFullContent(newPartialContent: string): string {
  if (!editingSubMessage.value) return ''
  const fullOriginalContent = editingSubMessage.value.content
  if (!editingRange.value) return newPartialContent
  const { start, end } = editingRange.value
  const fence = editingMarkup.value
  const lang = editingLanguage.value
  const newBlockString = `${fence}${lang}\n${newPartialContent}\n${fence}`
  return (
    fullOriginalContent.substring(0, start) + newBlockString + fullOriginalContent.substring(end)
  )
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

function restoreSubMessage(subMessageId: string) {
  const subMessage = props.message.sub_messages.find((sm) => sm.id === subMessageId)
  if (!subMessage) return
  interactionStore.updateSubMessage({
    subMessageId: subMessageId,
    data: { config: { ...subMessage.config, is_minimal: false } },
  })
}

function handleZipBookmarkClick() {
  if (zipStatus.value === 'generating') return
  isZipCardVisible.value = !isZipCardVisible.value
}

function handleCompressHistory() {
  interactionStore.initiateHistoryCompression(props.message.id)
  ElMessage.info(t('chat.message.compressStarted'))
}

async function handleCopySingle(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content)
    ElMessage.success(t('chat.message.codeCopied'))
  } catch {}
}

async function handleCopySpecific(id: string) {
  const targetSub = props.message.sub_messages.find((sm) => sm.id === id)
  if (targetSub) {
    await handleCopySingle(targetSub)
  }
  activeSubMessageId.value = null
}

function handleRegenerate() {
  interactionStore.regenerateFrom(props.message.id)
  activeSubMessageId.value = null
}

async function handleDeleteMessage() {
  try {
    await ElMessageBox.confirm(t('chat.message.deleteConfirm'), t('common.action.delete'), {
      type: 'warning',
    })
    await interactionStore.deleteMessage(props.message.id)
  } catch {}
  activeSubMessageId.value = null
}
</script>

<style scoped>
.mobile-message-item {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  width: 100%;
  animation: msg-in 0.3s ease-out;
}

@keyframes msg-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.mobile-message-item.is-user {
  flex-direction: row-reverse;
}

.mobile-message-item.is-assistant {
  flex-direction: row;
}

.message-avatar {
  flex-shrink: 0;
  margin-top: 2px;
}

.message-body {
  flex: 1;
  min-width: 0;
  max-width: 82%;
  display: flex;
  flex-direction: column;
}

.user-body {
  align-items: flex-end;
}

.assistant-body {
  align-items: flex-start;
  max-width: 85%;
}

.bubble {
  padding: 10px 14px;
  border-radius: 18px;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  position: relative;
}

.user-bubble {
  background: #409EFF !important;
  background: linear-gradient(135deg, var(--el-color-primary, #409EFF), var(--el-color-primary-light-1, #66b1ff)) !important;
  color: #fff !important;
  border-bottom-right-radius: 4px;
  max-width: 100%;
  overflow: hidden;
}

.user-bubble :deep(.message-content),
.user-bubble :deep(.message-content *) {
  color: rgba(255, 255, 255, 0.95) !important;
}

.user-bubble :deep(.partition-title) {
  color: rgba(255, 255, 255, 0.7) !important;
}

.user-bubble :deep(.action-icon) {
  color: rgba(255, 255, 255, 0.6) !important;
}

.user-bubble :deep(pre),
.user-bubble :deep(code) {
  color: rgba(255, 255, 255, 0.9);
}

.user-bubble :deep(.el-tag) {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.3);
  color: rgba(255, 255, 255, 0.9);
}

.user-bubble.is-first {
  border-top-right-radius: 18px;
}

.user-bubble.is-last {
  border-bottom-right-radius: 4px;
}

.typing-bubble {
  padding: 10px 16px;
}

.assistant-body :deep(.sub-message-item) {
  border: none;
  background: transparent;
  border-radius: 0;
  margin-bottom: 0;
  box-shadow: none;
}

.assistant-body :deep(.sub-message-item .message-content) {
  padding: 0;
}

/* AI message sections are card-style inside the bubble group */
.assistant-body :deep(.mobile-bubble-section-group) {
  border-bottom: none;
  padding: 4px 0;
}

.minimized-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.sub-messages-container {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.typing-indicator {
  display: flex;
  gap: 4px;
}
.typing-indicator span {
  width: 6px;
  height: 6px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

.inline-actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: var(--color-background);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 4px 8px;
  margin-top: 6px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.user-inline-actions {
  align-self: flex-end;
}

.branch-switcher {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-right: 6px;
  margin-right: 4px;
  border-right: 1px solid var(--el-border-color-lighter);
}

.branch-text {
  font-size: 11px;
  color: var(--el-text-color-regular);
  user-select: none;
  font-variant-numeric: tabular-nums;
  min-width: 28px;
  text-align: center;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  background: transparent;
  border-radius: 8px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.action-btn:active {
  background-color: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

.action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.action-btn.danger:active {
  color: var(--el-color-danger);
}

.zip-history-section {
  margin-top: 8px;
}

.zip-history-bookmark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--color-background-soft);
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.zip-history-bookmark.is-enabled {
  background: var(--el-color-success-light-9);
  border-color: var(--el-color-success-light-5);
  color: var(--el-color-success);
}

.zip-history-bookmark.is-generating {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}

.zip-history-bookmark .el-icon.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.zip-history-card {
  margin-top: 8px;
}

.suggestion-area {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.suggestion-chip {
  padding: 6px 14px;
  border-radius: 16px;
  border: 1px solid var(--el-border-color-light);
  background: var(--color-background-soft);
  font-size: 13px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  transition: all 0.15s;
  -webkit-tap-highlight-color: transparent;
  font-family: inherit;
}

.suggestion-chip:active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}

/* Action Sheet */
.action-sheet-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  -webkit-tap-highlight-color: transparent;
}

.action-sheet {
  width: 100%;
  max-width: 500px;
  background: var(--color-background);
  border-radius: 16px 16px 0 0;
  padding: 8px 16px;
  padding-bottom: max(16px, env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--el-border-color);
  border-radius: 2px;
  margin: 8px auto 12px;
}

.sheet-actions {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sheet-action-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 14px 8px;
  border: none;
  border-radius: 10px;
  background: transparent;
  font-size: 16px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition: background-color 0.15s;
  font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}

.sheet-action-btn:active {
  background: var(--el-fill-color-light);
}

.sheet-action-btn.danger {
  color: var(--el-color-danger);
}

.sheet-cancel {
  width: 100%;
  padding: 14px;
  margin-top: 8px;
  border: none;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}

.sheet-cancel:active {
  background: var(--el-fill-color);
}

.sheet-enter-active {
  transition: all 0.25s ease-out;
}
.sheet-leave-active {
  transition: all 0.2s ease-in;
}
.sheet-enter-from .action-sheet,
.sheet-leave-to .action-sheet {
  transform: translateY(100%);
}
.sheet-enter-from {
  opacity: 0;
}
.sheet-leave-to {
  opacity: 0;
}
</style>
