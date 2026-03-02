<!-- frontend/mambo/src/mobile/components/chat/MessageItem.vue -->
<template>
  <div :id="id" class="mobile-message-item" :class="roleClass">
    <!-- 头像 -->
    <div class="message-avatar">
      <el-avatar :size="32" :src="avatarUrl || ''">
        <el-icon v-if="message.role === 'user'"><User /></el-icon>
        <el-icon v-else><Cpu /></el-icon>
      </el-avatar>
    </div>

    <!-- 消息体 -->
    <!-- 点击切换菜单 -->
    <div class="message-body" @click="toggleActions">
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
        </template>
      </div>

      <!-- Zip History Bookmark and Card -->
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

      <!-- 建议区域 (独立于操作菜单，始终占据空间但可换行) -->
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

      <!-- 浮动操作菜单 (绝对定位，不占空间) -->
      <transition name="fade-slide">
        <div v-if="showActions && message.status !== 'generating'" class="floating-actions" :class="{'is-user-side': message.role === 'user'}" @click.stop>
          <el-icon class="action-btn" @click="handleEditFirst" v-if="normalSubMessages.length > 0"><Edit /></el-icon>
          <el-icon class="action-btn" @click="handleCopyAll"><CopyDocument /></el-icon>
          <el-icon class="action-btn" @click="handleRegenerate"><RefreshRight /></el-icon>
          <el-icon v-if="message.role === 'assistant'" class="action-btn" @click="handleCompressHistory"><Clock /></el-icon>
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
  </div>

  <!-- 编辑弹窗 -->
  <MobileMessageEditDialog
    v-model:visible="editDialogVisible"
    :initial-content="originalEditingContent"
    :is-user-message="message.role === 'user'"
    @save="handleSaveEdit"
    @save-and-resend="handleSaveAndResend"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { Message, SubMessage, SubMessageCreate, MessageStatus } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User, Cpu, Document, MoreFilled, CopyDocument, RefreshRight, Delete, Edit, Clock, Loading, CircleCheck,
} from '@element-plus/icons-vue'
import SubMessageItem from './SubMessageItem.vue'
import ZipHistoryCard from './ZipHistoryCard.vue'
import MobileMessageEditDialog from '@/mobile/components/chat/dialogs/MobileMessageEditDialog.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { type ParsedBlock } from '@/utils/markdownParser'

const props = defineProps<{
  id?: string
  message: Message
  isLastMessage: boolean
}>()

const emit = defineEmits<{
  (e: 'suggestion-click', text: string): void
}>()

const { t } = useI18n()
const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const settingsStore = useSettingsStore()
const { globalSettings } = storeToRefs(settingsStore)
const { messageRecencyRanks } = storeToRefs(sessionStore)

// --- Interaction State ---
const showActions = ref(false)

const toggleActions = () => {
  if (props.message.status !== 'generating') {
    showActions.value = !showActions.value
  }
}

/**
 * 计算当前消息的新旧程度排名。
 * 0: 正在生成。
 * 1: 最新的一条已完成消息。
 * N: 第N条已完成消息。
 */
const currentMessageRank = computed(() => {
  return messageRecencyRanks.value.get(props.message.id) ?? 999
})

/**
 * 判断子消息是否处于“虚状态”（不参与上下文）。
 */
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
  return props.message.role === 'user'
    ? globalSettings.value.user_avatar_url
    : globalSettings.value.ai_avatar_url
})

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

function handleEditFirst() {
  if (normalSubMessages.value.length > 0) {
    handleEditRequest(normalSubMessages.value[0], { content: normalSubMessages.value[0].content })
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

async function handleCopyAll() {
  const text = normalSubMessages.value.map((sm) => sm.content).join('\n---\n')
  try {
    await copyToClipboard(text)
    ElMessage.success(t('chat.message.codeCopied'))
  } catch {}
}

function handleRegenerate() {
  interactionStore.regenerateFrom(props.message.id)
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
}
</script>

<style scoped>
.mobile-message-item {
  display: flex;
  gap: 8px;
  margin-bottom: 24px; /* 保留底部间距，给浮动菜单留出空间 */
  width: 100%;
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
  cursor: pointer; /* 暗示可点击 */
  position: relative; /* 关键：为绝对定位的菜单提供参考点 */
}

.minimized-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

/* 虚状态样式 - 最小化模式 */
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

/* Suggestion Area - 独立区域，允许换行 */
.suggestion-area {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.suggestion-item {
  margin: 0; /* 重置 margin */
}

/* Floating Actions - 核心修改 */
.floating-actions {
  position: absolute;
  bottom: -30px; /* 向下偏移，进入 margin-bottom 的空间 */
  right: 0;
  z-index: 10;

  display: flex;
  align-items: center;
  gap: 12px;

  background-color: var(--color-background);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  padding: 4px 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 用户消息的菜单靠左对齐 */
.floating-actions.is-user-side {
  right: auto;
  left: 0;
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

/* 过渡动画 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px); /* 从上方滑入 */
}

/* User Message Specifics */
.mobile-message-item.is-user {
  flex-direction: row-reverse;
}

.text-danger {
  color: var(--el-color-danger);
}
</style>
