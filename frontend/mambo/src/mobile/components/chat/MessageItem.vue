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
    <div class="message-body">
      <!-- 最小化子消息区域 (简单展示图标) -->
      <div v-if="minimizedSubMessages.length > 0" class="minimized-bar">
        <el-tag
          v-for="sub in minimizedSubMessages"
          :key="sub.id"
          size="small"
          type="info"
          @click="restoreSubMessage(sub.id)"
        >
          <el-icon><Document /></el-icon>
        </el-tag>
      </div>

      <!-- 子消息列表 -->
      <div class="sub-messages-container">
        <!-- Loading 占位 -->
        <div
          v-if="message.status === 'generating' && normalSubMessages.length === 0"
          class="initial-loading"
        >
          <div class="typing-indicator"><span></span><span></span><span></span></div>
        </div>

        <!-- 渲染子消息 -->
        <template v-for="(subMessage, index) in normalSubMessages" :key="subMessage.id">
          <SubMessageItem
            :id="`sub-msg-${subMessage.id}`"
            :sub-message="subMessage"
            :parent-message="message"
            :index="index + 1"
            :show-header="normalSubMessages.length > 1 || subMessage.type !== 'Normal'"
            @edit="(payload) => handleEditRequest(subMessage, payload)"
            @copy="handleCopySingle(subMessage)"
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

      <!-- 底部操作栏 -->
      <div class="message-footer" v-if="message.status !== 'generating'">
        <!-- 左侧：建议 Chips -->
        <div class="footer-left">
          <div v-if="isLastMessage && suggestionList.length > 0" class="suggestion-scroll">
            <el-tag
              v-for="(suggestion, idx) in suggestionList"
              :key="idx"
              class="suggestion-item"
              type="info"
              effect="plain"
              round
              size="small"
              @click="$emit('suggestion-click', suggestion)"
            >
              {{ suggestion }}
            </el-tag>
          </div>
        </div>

        <!-- 右侧：操作按钮组 -->
        <div class="footer-right actions-group">
          <!-- 编辑 -->
          <el-icon class="action-btn" @click="handleEditFirst" v-if="normalSubMessages.length > 0"
            ><Edit
          /></el-icon>

          <!-- 复制全部 -->
          <el-icon class="action-btn" @click="handleCopyAll"><CopyDocument /></el-icon>

          <!-- 重新生成 -->
          <el-icon class="action-btn" @click="handleRegenerate"><RefreshRight /></el-icon>

          <!-- 压缩历史 (仅 Assistant 消息显示) -->
          <el-icon
            v-if="message.role === 'assistant'"
            class="action-btn"
            @click="handleCompressHistory"
          >
            <Clock />
          </el-icon>

          <!-- 更多/删除 -->
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
      </div>
    </div>
  </div>

  <!-- 编辑弹窗 -->
  <MessageEditDialog
    v-model:visible="editDialogVisible"
    :initial-content="originalEditingContent"
    :is-user-message="message.role === 'user'"
    @save="handleSaveEdit"
    @save-and-resend="handleSaveAndResend"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { storeToRefs } from 'pinia'
import type { Message, SubMessage, SubMessageCreate, MessageStatus } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useSettingsStore } from '@/stores/settingsStore'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  User,
  Cpu,
  Document,
  MoreFilled,
  CopyDocument,
  RefreshRight,
  Delete,
  Edit,
  Clock,
  Loading,
  CircleCheck,
} from '@element-plus/icons-vue'
import SubMessageItem from './SubMessageItem.vue'
import ZipHistoryCard from './ZipHistoryCard.vue'
import MessageEditDialog from '@/components/chat/dialogs/MessageEditDialog.vue'
import { copyToClipboard } from '@/utils/clipboard'
import { parseMarkdown } from '@/utils/markdownParser'

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
const settingsStore = useSettingsStore()
const { globalSettings } = storeToRefs(settingsStore)

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

/**
 * 提取出 'ZipHistory' 类型的子消息，用于显示历史摘要卡片。
 */
const zipHistorySubMessage = computed(() =>
  props.message.sub_messages.find((sm) => sm.type === 'ZipHistory'),
)

/**
 * 计算历史摘要的当前状态
 */
const zipStatus = computed(() => {
  if (!zipHistorySubMessage.value) return null
  if (zipHistorySubMessage.value.status === 'generating') return 'generating'
  if (zipHistorySubMessage.value.config.zip_enable) return 'enabled'
  return 'disabled'
})

/**
 * 根据状态返回对应的图标组件
 */
const zipBookmarkIcon = computed(() => {
  switch (zipStatus.value) {
    case 'generating':
      return Loading
    case 'enabled':
      return CircleCheck
    default:
      return Clock
  }
})

/**
 * 根据状态返回显示的文本
 */
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

/**
 * 根据状态返回 CSS 类名
 */
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
const editingBlockIndex = ref<number | null>(null)

function handleEditRequest(
  subMessage: SubMessage,
  payload: { content: string; blockIndex?: number },
) {
  editingSubMessage.value = subMessage
  originalEditingContent.value = payload.content
  editingBlockIndex.value = payload.blockIndex ?? null
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
  const blockIndex = editingBlockIndex.value

  if (blockIndex === null || blockIndex === undefined) {
    return newPartialContent
  }

  const originalBlocks = parseMarkdown(fullOriginalContent)

  if (blockIndex >= originalBlocks.length) {
    console.warn('Block index out of bounds, falling back to full replacement')
    return fullOriginalContent
  }

  const targetBlock = originalBlocks[blockIndex]

  if (targetBlock && targetBlock.type === 'code') {
    let targetCodeIdx = 0
    for (let i = 0; i < blockIndex; i++) {
      if (originalBlocks[i].type === 'code') targetCodeIdx++
    }

    const fenceRegex = /(^|\n)(`{3,}|~{3,})([^\n]*)(\n)([\s\S]*?)(\n?)(\2)(?=\n|$)/g

    let matchCount = 0
    return fullOriginalContent.replace(fenceRegex, (match, p1, p2, p3, p4, p5, p6, p7) => {
      if (matchCount === targetCodeIdx) {
        matchCount++
        return `${p1}${p2}${p3}${p4}${newPartialContent}\n${p7}`
      }
      matchCount++
      return match
    })
  }

  return newPartialContent
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
  margin-bottom: 24px;
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
}

.minimized-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
  flex-wrap: wrap;
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
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
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

.zip-history-bookmark.is-disabled {
  background-color: var(--el-color-info-light-9);
  border-color: var(--el-color-info-light-7);
  color: var(--el-color-info);
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
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.zip-history-card {
  margin-top: 8px;
}

/* Footer & Actions */
.message-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
  min-height: 24px;
}

.footer-left {
  flex-grow: 1;
  overflow: hidden;
}

.footer-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: 8px;
  opacity: 0.6;
}

.action-btn {
  font-size: 16px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
}

/* Suggestion Chips Scroll */
.suggestion-scroll {
  display: flex;
  overflow-x: auto;
  gap: 6px;
  padding-bottom: 2px;
  scrollbar-width: none;
}
.suggestion-scroll::-webkit-scrollbar {
  display: none;
}

.suggestion-item {
  flex-shrink: 0;
}

/* User Message Specifics */
.mobile-message-item.is-user {
  flex-direction: row-reverse;
}
.is-user .message-footer {
  flex-direction: row-reverse;
}
.is-user .footer-right {
  margin-left: 0;
  margin-right: 8px;
}

.text-danger {
  color: var(--el-color-danger);
}
</style>
