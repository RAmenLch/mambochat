<!-- frontend/mambo/src/mobile/components/chat/MessageItem.vue -->
<template>
  <!-- 点击空白区域关闭菜单 -->
  <div :id="id" class="mobile-message-item" :class="roleClass" @click="clearActions">

    <!-- 用户消息 -->
    <template v-if="message.role === 'user'">
      <!-- 头像 -->
      <div class="message-avatar">
        <el-avatar :size="32" :src="avatarUrl || ''">
          <el-icon><User /></el-icon>
        </el-avatar>
      </div>

      <!-- 消息体 -->
      <div class="message-body">
        <!-- 最小化子消息区域 -->
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

        <!-- 子消息列表 -->
        <div class="sub-messages-container">
          <div
            v-if="message.status === 'generating' && normalSubMessages.length === 0"
            class="initial-loading"
          >
            <div class="typing-indicator"><span></span><span></span><span></span></div>
          </div>

          <template v-for="(subMessage, index) in normalSubMessages" :key="subMessage.id">
            <!-- 针对单个用户子消息的包裹层，绑定点击事件 -->
            <div class="user-sub-message-wrapper" @click.stop="toggleActions(subMessage.id)">
              <SubMessageItem
                :id="`sub-msg-${subMessage.id}`"
                :sub-message="subMessage"
                :parent-message="message"
                :index="index + 1"
                :show-header="normalSubMessages.length > 1 || subMessage.type !== 'Normal'"
                :is-inactive="isSubMessageInactive(subMessage)"
                @edit="(payload) => handleEditRequest(subMessage, payload)"
                @copy="handleCopySingle(subMessage)"
              />

              <!-- 用户消息的内联浮动菜单 -->
              <transition name="fade-slide">
                <div v-if="activeSubMessageId === subMessage.id && message.status !== 'generating'" class="floating-actions inline-actions is-user-side" @click.stop>
                  <el-icon class="action-btn" @click="handleEditSpecific(subMessage.id)"><Edit /></el-icon>
                  <el-icon class="action-btn" @click="handleCopySpecific(subMessage.id)"><CopyDocument /></el-icon>
                  <el-icon class="action-btn" @click="handleRegenerate"><RefreshRight /></el-icon>
                  <el-dropdown trigger="click" @command="handleCommand">
                    <el-icon class="action-btn"><MoreFilled /></el-icon>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="delete" class="text-danger">
                          <el-icon><Delete /></el-icon>{{ $t('common.action.delete') }}
                        </el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </transition>
            </div>
          </template>
        </div>
      </div>
    </template>

    <!-- AI 消息 -->
    <template v-else-if="message.role === 'assistant'">
      <div class="assistant-message-container">
        <MobileAssistantBubble
          :message="message"
          :is-generating="message.status === 'generating'"
          :current-message-rank="currentMessageRank"
          @edit="handleEditRequest"
          @copy="handleCopySingle"
          @open-tool-dialog="(toolId) => $emit('open-tool-dialog', message, toolId, 'single')"
          @toggle-actions="toggleActions"
        >
          <template #avatar>
            <div class="message-avatar">
              <el-avatar :size="32" :src="avatarUrl || ''">
                <el-icon><Cpu /></el-icon>
              </el-avatar>
            </div>
          </template>

          <!-- 接收 AI 子消息的插槽，渲染对应的内联菜单 -->
          <template #actions="{ subMessageId }">
            <transition name="fade-slide">
              <div v-if="activeSubMessageId === subMessageId && message.status !== 'generating'" class="floating-actions inline-actions" @click.stop>
                <!-- 分支切换 -->
                <div v-if="hasSiblings" class="branch-switcher">
                  <el-icon class="action-btn" :class="{'is-disabled': !canGoPrev}" @click="handlePrev"><ArrowLeft /></el-icon>
                  <span class="branch-text">{{ currentIndex }} / {{ totalSiblings }}</span>
                  <el-icon class="action-btn" :class="{'is-disabled': !canGoNext}" @click="handleNext"><ArrowRight /></el-icon>
                  <el-divider direction="vertical" />
                </div>

                <!-- Token 消耗 -->
                <el-icon v-if="usageSubMessage" class="action-btn" @click="handleShowUsage"><Coin /></el-icon>

                <el-icon class="action-btn" @click="handleEditSpecific(subMessageId)"><Edit /></el-icon>
                <el-icon class="action-btn" @click="handleCopySpecific(subMessageId)"><CopyDocument /></el-icon>
                <el-icon class="action-btn" @click="handleRegenerate"><RefreshRight /></el-icon>
                <el-icon class="action-btn" @click="handleCompressHistory"><Clock /></el-icon>

                <el-dropdown trigger="click" @command="handleCommand">
                  <el-icon class="action-btn"><MoreFilled /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="delete" class="text-danger">
                        <el-icon><Delete /></el-icon>{{ $t('common.action.delete') }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </transition>
          </template>
        </MobileAssistantBubble>

        <!-- Zip History -->
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

        <!-- 建议区域 -->
        <div class="suggestion-area" v-if="message.status !== 'generating' && isLastMessage && suggestionList.length > 0">
          <el-tag
            v-for="(suggestion, idx) in suggestionList"
            :key="idx"
            class="suggestion-item"
            type="info"
            effect="plain"
            round
            size="small"
            @click.stop="$emit('suggestion-click', suggestion)"
          >
            {{ suggestion }}
          </el-tag>
        </div>
      </div>
    </template>

    <!-- 编辑弹窗 -->
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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { Message, SubMessage, SubMessageCreate, MessageStatus } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { useAgentStore } from '@/stores/agentStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User, Cpu, Document, MoreFilled, CopyDocument, RefreshRight, Delete, Edit, Clock, Loading, CircleCheck, ArrowLeft, ArrowRight, Coin
} from '@element-plus/icons-vue'
import SubMessageItem from './SubMessageItem.vue'
import ZipHistoryCard from './ZipHistoryCard.vue'
import MobileAssistantBubble from './message/MobileAssistantBubble.vue'
import MobileMessageEditDialog from '@/mobile/components/chat/dialogs/MobileMessageEditDialog.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { type ParsedBlock } from '@/utils/markdownParser'
import { resolveFileUrl } from '@/services/electronUrl'

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

const { globalSettings } = storeToRefs(settingsStore)
const { messageRecencyRanks } = storeToRefs(sessionStore)

// --- Interaction State ---
const activeSubMessageId = ref<string | null>(null)

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

// --- Multi-Branch Logic ---
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

// --- Data Logic ---
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

// --- Usage Info Logic ---
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

// --- Edit Logic ---
const editDialogVisible = ref(false)
const editingSubMessage = ref<SubMessage | null>(null)
const originalEditingContent = ref('')
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

// 精准编辑特定的 SubMessage
function handleEditSpecific(id: string) {
  const targetSub = props.message.sub_messages.find((sm) => sm.id === id)
  if (targetSub) {
    handleEditRequest(targetSub, { content: targetSub.content })
  } else if (normalSubMessages.value.length > 0) {
    // Fallback: 如果点的是纯工具组，降级编辑第一个普通消息
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

function handleSaveEdit(newContent: string) {
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

// --- Zip History Actions ---
function handleZipBookmarkClick() {
  if (zipStatus.value === 'generating') return
  isZipCardVisible.value = !isZipCardVisible.value
}

function handleCompressHistory() {
  interactionStore.initiateHistoryCompression(props.message.id)
  ElMessage.info(t('chat.message.compressStarted'))
}

// --- Actions ---
async function handleCopySingle(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content)
    ElMessage.success(t('chat.message.codeCopied'))
  } catch {}
}

// 精准复制特定的 SubMessage
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

async function handleCommand(command: string) {
  if (command === 'delete') {
    try {
      await ElMessageBox.confirm(t('chat.message.deleteConfirm'), t('common.action.delete'), {
        type: 'warning',
      })
      await interactionStore.deleteMessage(props.message.id)
    } catch {}
  }
  activeSubMessageId.value = null
}
</script>

<style scoped>
.mobile-message-item {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
  width: 100%;
}

.mobile-message-item.is-user {
  flex-direction: row-reverse;
}

.message-avatar {
  flex-shrink: 0;
  margin-top: 2px;
}

.message-body {
  flex-grow: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.user-sub-message-wrapper {
  display: flex;
  flex-direction: column;
  cursor: pointer;
}

.assistant-message-container {
  width: 100%;
  display: flex;
  flex-direction: column;
}

.minimized-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.minimized-bar .el-tag.is-inactive {
  opacity: 1;
  border-style: dashed;
  background-color: var(--el-fill-color-lighter);
  color: var(--el-text-color-regular);
}

.sub-messages-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.initial-loading {
  padding: 10px;
  background: var(--color-background-soft);
  border-radius: 8px;
  display: inline-flex;
}

.typing-indicator {
  display: flex;
  gap: 4px;
}
.typing-indicator span {
  width: 6px;
  height: 6px;
  background: #999;
  border-radius: 50%;
  animation: bounce 1.4s infinite;
}
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* Zip History Styles */
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

.zip-history-bookmark.is-generating {
  background-color: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
  cursor: default;
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

/* Suggestion Area */
.suggestion-area {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.suggestion-item {
  margin: 0;
}

/* Floating Actions - Inline Mode */
.floating-actions.inline-actions {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  background-color: var(--color-background);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 4px 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  z-index: 10;
  margin-top: 4px;
}

/* AI 消息的操作菜单靠右对齐 (由于放在 group-actions-container 已经靠右，这里保持默认) */

/* 用户消息的操作菜单靠左对齐 */
.floating-actions.inline-actions.is-user-side {
  align-self: flex-end; /* 因为 user 消息整体是 row-reverse，这里用 flex-end 靠左 */
}

.branch-switcher {
  display: flex;
  align-items: center;
  gap: 4px;
}

.branch-text {
  font-size: 12px;
  color: var(--el-text-color-regular);
  user-select: none;
  font-variant-numeric: tabular-nums;
  margin: 0 2px;
}

.action-btn {
  font-size: 16px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: color 0.2s;
}

.action-btn:hover {
  color: var(--el-color-primary);
}

.action-btn.is-disabled {
  color: var(--el-text-color-disabled);
  cursor: not-allowed;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-5px); /* 改为稍微向下偏移滑入，更符合内联展开的视觉 */
}

.text-danger {
  color: var(--el-color-danger);
}
</style>
