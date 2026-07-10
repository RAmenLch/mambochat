<!-- frontend/mambo/src/mobile/components/chat/ChatWindow.vue -->
<template>
  <div class="mobile-chat-window">
    <ChatHeader
      :current-chat="currentChat"
      @toggle-drawer="$emit('toggle-drawer')"
      @open-settings="handleOpenSettings"
    />

    <div class="mobile-messages" v-if="currentChat">
      <el-scrollbar ref="scrollbarRef" class="message-scrollbar" @scroll="handleScroll">
        <div class="message-wrapper">
          <MessageItem
            v-for="(message, index) in currentChatMessages"
            :key="message.id"
            :id="'msg-' + message.id"
            :message="message"
            :is-last-message="index === currentChatMessages.length - 1"
            @suggestion-click="handleSuggestionClick"
            @switch-branch="handleSwitchBranch"
            @open-tool-dialog="handleOpenToolDialog"
          />
        </div>
      </el-scrollbar>
    </div>

    <div class="mobile-empty" v-else>
      <div class="welcome-brand">
        <img src="/logo.svg" alt="Mambo" class="welcome-logo" />
        <h2 class="welcome-title">Mambo Chat</h2>
        <p class="welcome-desc">{{ $t('chat.window.welcome') }}</p>
      </div>
    </div>

    <div class="mobile-input-area" v-if="currentChat">
      <div v-if="isPendingReview" class="pending-review-bar" @click="handleOpenReviewFromInput">
        <el-icon :size="18"><Warning /></el-icon>
        <span>有 {{ pendingReviewSubMessages.length }} 项待审核，点击处理</span>
        <el-icon :size="14"><ArrowRight /></el-icon>
      </div>

      <input
        type="file"
        ref="fileInputRef"
        @change="onFileSelected"
        multiple
        style="display: none"
      />

      <AttachmentPreview
        v-if="hasAttachments"
        :uploaded-files="uploadedFiles"
        :attached-resources="attachedSubmessageResources"
        :attached-knowledge-bases="attachedKnowledgeBases"
        @remove-file="removeUploadedFile"
        @remove-resource="removeAttachedResource"
        @remove-knowledge-base="handleRemoveKnowledgeBase"
      />

      <ChatToolbar
        :current-chat="currentChat"
        :messages="currentChatMessages"
        :estimated-tokens="estimatedTokens"
        @trigger-file-upload="handleTriggerFileUpload"
        @open-resource-selector="resourceSelectorVisible = true"
        @toggle-mcp-tool="handleToggleMcpTool"
        @toggle-web-search="handleToggleWebSearch"
        @jump-to-message="handleJumpToMessage"
      />

      <ChatInputBox
        ref="chatInputBoxRef"
        :is-generating="isGenerating"
        :is-send-button-disabled="isSendButtonDisabled"
        v-model="singlePartDraft"
        @send="handleSendMessage"
        @stop-generation="handleStopGeneration"
        @files-pasted="handleFileUploads"
        @trigger-file-upload="handleTriggerFileUpload"
        @open-resource-selector="resourceSelectorVisible = true"
      />
    </div>

    <ChatSettingsDrawer
      v-model:visible="settingsDrawerVisible"
      :chat-data="currentChat"
      :grouped-models="groupedModels"
      @save="handleSaveSettings"
    />

    <MobileChatAgentSettingsDrawer
      v-model:visible="agentSettingsDrawerVisible"
      :chat-data="currentChat"
      @save="handleSaveAgentSettings"
    />

    <MobileToolDialog
      v-model:visible="toolDialogVisible"
      :parent-message-id="toolDialogMessageId"
      :initial-sub-message-id="toolDialogInitialId"
      :mode="toolDialogMode"
    />

    <MobileAskUserDialog
      v-model:visible="askUserDialogVisible"
      :parent-message-id="askUserDialogMessageId"
      :initial-sub-message-id="askUserDialogInitialSubMessageId"
    />

    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      :context="currentChat?.chatMode === 'agent' ? 'agent-toolbar' : 'chat-toolbar'"
      @mount-resources="handleMountResources"
      @append-resources="handleAppendResources"
      @mount-knowledge-base="handleMountKnowledgeBase"
    />
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  watch,
  nextTick,
  computed,
  onMounted,
  onUnmounted,
} from 'vue'
import { storeToRefs } from 'pinia'
import { ElScrollbar, ElMessage } from 'element-plus'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ChatHeader from './ChatHeader.vue'
import MessageItem from '@/mobile/components/chat/MessageItem.vue'
import ChatToolbar from '@/mobile/components/chat/ChatToolbar.vue'
import AttachmentPreview from '@/mobile/components/chat/AttachmentPreview.vue'
import ChatInputBox from '@/mobile/components/chat/ChatInputBox.vue'
import ChatSettingsDrawer from './ChatSettingsDrawer.vue'
import MobileChatAgentSettingsDrawer from './MobileChatAgentSettingsDrawer.vue'
import MobileToolDialog from './dialogs/MobileToolDialog.vue'
import MobileAskUserDialog from './dialogs/MobileAskUserDialog.vue'
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue'

import { useChatListStore } from '@/stores/chatListStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useProviderStore } from '@/stores/providerStore'
import { useAgentStore } from '@/stores/agentStore'
import { useChatInput } from '@/composables/useChatInput'
import { useTokenEstimator } from '@/composables/useTokenEstimator'
import { uploadFile } from '@/api/fileService'
import type { AIModel, ChatUpdate, Resource, SubMessageCreate, Message, SubMessage } from '@/api/types'

interface GroupedModels {
  label: string
  options: AIModel[]
}

const emit = defineEmits<{
  (e: 'toggle-drawer'): void
}>()

const { t } = useI18n()
const chatListStore = useChatListStore()
const chatSessionStore = useChatSessionStore()
const chatInteractionStore = useChatInteractionStore()
const providerStore = useProviderStore()
const agentStore = useAgentStore()

const { currentChat, currentChatMessages, isGenerating, currentChatId, contextForTokenEstimation, systemPromptResources } =
  storeToRefs(chatSessionStore)
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]> }

const {
  singlePartDraft,
  uploadedFiles,
  attachedSubmessageResources,
  isReadyToSend,
  addUploadedFile,
  removeUploadedFile,
  addAttachedResource,
  removeAttachedResource,
  resetDraft,
  appendContentToDraft,
} = useChatInput(currentChatId)

const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()
const chatInputBoxRef = ref()
const fileInputRef = ref<HTMLInputElement | null>(null)
const settingsDrawerVisible = ref(false)
const agentSettingsDrawerVisible = ref(false)
const resourceSelectorVisible = ref(false)
const userHasScrolledUp = ref(false)

const toolDialogVisible = ref(false)
const toolDialogMessageId = ref<string | null>(null)
const toolDialogInitialId = ref<string | undefined>(undefined)
const toolDialogMode = ref<'review_all' | 'single'>('single')

const askUserDialogVisible = ref(false)
const askUserDialogMessageId = ref<string | null>(null)
const askUserDialogInitialSubMessageId = ref<string | null>(null)

let vvResizeHandler: (() => void) | null = null
let vvScrollHandler: (() => void) | null = null
let winResizeHandler: (() => void) | null = null

const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value)

const attachedKnowledgeBases = computed(() => {
  return systemPromptResources.value.filter(r => r.resourceType === 'knowledge_base')
})

const hasAttachments = computed(
  () =>
    uploadedFiles.value.length > 0 ||
    attachedSubmessageResources.value.length > 0 ||
    attachedKnowledgeBases.value.length > 0,
)

const pendingMessageTextForTokenEstimation = computed(() => {
  const parts: string[] = []
  if (singlePartDraft.value) {
    parts.push(singlePartDraft.value)
  }
  attachedSubmessageResources.value.forEach((resource) => {
    if (resource.resourceType === 'submessage_template' && resource.latest_version?.content) {
      parts.push(resource.latest_version.content)
    }
  })
  return parts.join('\n')
})

const { estimatedTokens } = useTokenEstimator(
  contextForTokenEstimation,
  pendingMessageTextForTokenEstimation,
)

onMounted(() => {
  if (agentStore.allAgents.length === 0) {
    agentStore.fetchAllAgents()
  }

  const setVH = () => {
    const vh = window.visualViewport ? window.visualViewport.height : window.innerHeight
    document.documentElement.style.setProperty('--vv-height', `${vh}px`)
  }
  setVH()

  vvResizeHandler = setVH
  vvScrollHandler = setVH
  winResizeHandler = setVH

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', vvResizeHandler)
    window.visualViewport.addEventListener('scroll', vvScrollHandler)
  }
  window.addEventListener('resize', winResizeHandler)
})

onUnmounted(() => {
  if (window.visualViewport) {
    if (vvResizeHandler) window.visualViewport.removeEventListener('resize', vvResizeHandler)
    if (vvScrollHandler) window.visualViewport.removeEventListener('scroll', vvScrollHandler)
  }
  if (winResizeHandler) window.removeEventListener('resize', winResizeHandler)
})

const handleSendMessage = async () => {
  if (isSendButtonDisabled.value) return

  const content = singlePartDraft.value.trim()
  const textSubMessages: SubMessageCreate[] = content
    ? [
        {
          content,
          sortOrder: 0,
          type: 'Normal',
        },
      ]
    : []

  const fileSubMessages: SubMessageCreate[] = uploadedFiles.value.map((file) => ({
    content: file.id,
    type: 'File',
    sortOrder: textSubMessages.length,
  }))

  const finalSubMessages = [...textSubMessages, ...fileSubMessages].map((sm, idx) => ({
    ...sm,
    sortOrder: idx,
  }))

  if (finalSubMessages.length > 0) {
    const attachedResourceIds = attachedSubmessageResources.value.map((r) => r.id)
    await chatInteractionStore.sendMessage(finalSubMessages, attachedResourceIds)
    resetDraft()
  }
}

const handleStopGeneration = () => {
  const genMsg = currentChatMessages.value.find((m) => m.status === 'generating')
  if (genMsg) chatInteractionStore.cancelGeneration(genMsg.id)
}

const handleSuggestionClick = (text: string) => {
  singlePartDraft.value = text
  nextTick(() => {
    chatInputBoxRef.value?.focus()
  })
}

const handleSwitchBranch = async (targetId: string) => {
  if (typeof chatInteractionStore.activateBranch === 'function') {
    await chatInteractionStore.activateBranch(targetId)
  }
}

const handleOpenToolDialog = (message: Message, subMessageId: string, mode: 'review_all' | 'single') => {
  const sub = message.sub_messages.find(sm => sm.id === subMessageId)
  if (sub && sub.type === 'AskUser') {
    askUserDialogMessageId.value = message.id
    askUserDialogInitialSubMessageId.value = subMessageId
    askUserDialogVisible.value = true
    return
  }
  toolDialogMessageId.value = message.id
  toolDialogInitialId.value = subMessageId
  toolDialogMode.value = mode
  toolDialogVisible.value = true
}

const pendingReviewSubMessages = computed(() => {
  const pendingMsg = currentChatMessages.value.find(msg => msg.status === 'pending_review')
  if (!pendingMsg) return [] as SubMessage[]
  return pendingMsg.sub_messages.filter(
    sm => (sm.type === 'ReviewTool' || sm.type === 'AskUser') && sm.status === 'pending_review'
  )
})

const isPendingReview = computed(() => pendingReviewSubMessages.value.length > 0)

function handleOpenReviewFromInput() {
  if (pendingReviewSubMessages.value.length > 0) {
    const first = pendingReviewSubMessages.value[0]
    const parentMsg = currentChatMessages.value.find(m => m.id === first.messageId)
    if (parentMsg) {
      if (first.type === 'AskUser') {
        askUserDialogMessageId.value = parentMsg.id
        askUserDialogInitialSubMessageId.value = null
        askUserDialogVisible.value = true
      } else {
        handleOpenToolDialog(parentMsg, first.id, 'review_all')
      }
    }
  }
}

function handleTriggerFileUpload() {
  fileInputRef.value?.click()
}

async function onFileSelected(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files) return
  await handleFileUploads(target.files)
  target.value = ''
}

async function handleFileUploads(files: FileList) {
  if (!files || files.length === 0) return
  for (const file of Array.from(files)) {
    try {
      const fileInfo = await uploadFile(file)
      addUploadedFile(fileInfo)
    } catch (error) {
      console.error(`Failed to upload file ${file.name}:`, error)
      ElMessage.error(`文件 ${file.name} 上传失败`)
    }
  }
}

async function handleMountResources(resources: Resource[]) {
  for (const resource of resources) {
    if (resource.resourceType === 'submessage_template') {
      addAttachedResource(resource)
    } else if (resource.resourceType === 'file') {
      const fileInfo = resource.latest_version?.file_info
      if (fileInfo) addUploadedFile(fileInfo)
    }
  }
}

async function handleAppendResources(resources: Resource[]) {
  const contents = resources.map((res) => res.latest_version?.content).filter(Boolean)
  if (contents.length > 0) {
    appendContentToDraft(contents.join('\n'))
    nextTick(() => chatInputBoxRef.value?.focus())
  }
}

async function handleMountKnowledgeBase(resources: Resource[]) {
  if (!currentChat.value) return
  const currentList = currentChat.value.resource_prompt_list || []
  const newIds = resources.map(r => r.id).filter(id => !currentList.includes(id))

  if (newIds.length > 0) {
    const updatedList = [...currentList, ...newIds]
    await chatListStore.updateChatSettings(currentChat.value.id, {
      resource_prompt_list: updatedList
    })
    ElMessage.success(`已启用知识库: ${resources.map(r => r.name).join(', ')}`)
  }
}

async function handleRemoveKnowledgeBase(resourceId: string) {
  if (!currentChat.value) return
  const currentList = currentChat.value.resource_prompt_list || []
  const updatedList = currentList.filter(id => id !== resourceId)

  await chatListStore.updateChatSettings(currentChat.value.id, {
    resource_prompt_list: updatedList.length > 0 ? updatedList : null
  })
  ElMessage.success('已停用知识库')
}

async function handleToggleMcpTool(mcpId: string) {
  if (!currentChat.value) return
  const currentIds = currentChat.value.enabled_mcp_ids || []
  const newIds = currentIds.includes(mcpId)
    ? currentIds.filter(id => id !== mcpId)
    : [...currentIds, mcpId]

  await chatListStore.updateChatSettings(currentChat.value.id, { enabled_mcp_ids: newIds })
}

async function handleToggleWebSearch() {
  if (!currentChat.value) return
  const currentMode = currentChat.value.web_search_mode
  let nextMode: 'direct_read' | 'search_and_read' | null
  if (!currentMode) {
    nextMode = 'direct_read'
  } else if (currentMode === 'direct_read') {
    nextMode = 'search_and_read'
  } else {
    nextMode = null
  }
  await chatListStore.updateChatSettings(currentChat.value.id, { web_search_mode: nextMode })
  if (nextMode === 'direct_read') {
    ElMessage.success('联网搜索：直接读取')
  } else if (nextMode === 'search_and_read') {
    ElMessage.success('联网搜索：搜索并读取')
  } else {
    ElMessage.info('联网搜索已关闭')
  }
}

function handleOpenSettings() {
  if (currentChat.value?.chatMode === 'agent') {
    agentSettingsDrawerVisible.value = true
  } else {
    settingsDrawerVisible.value = true
  }
}

async function handleSaveSettings(settings: ChatUpdate) {
  if (!currentChat.value) return
  await chatListStore.updateChatSettings(currentChat.value.id, settings)
  settingsDrawerVisible.value = false
  ElMessage.success(t('chat.settings.saveSuccess'))
}

async function handleSaveAgentSettings(settings: ChatUpdate) {
  if (!currentChat.value) return
  await chatListStore.updateChatSettings(currentChat.value.id, settings)
  agentSettingsDrawerVisible.value = false
  ElMessage.success(t('chat.settings.saveSuccess'))
}

const handleScroll = ({ scrollTop }: { scrollTop: number }) => {
  const el = scrollbarRef.value?.wrapRef
  if (!el) return
  userHasScrolledUp.value = el.scrollHeight - el.clientHeight - scrollTop > 20
}

function handleJumpToMessage(messageId: string) {
  const elementId = `msg-${messageId}`
  const element = document.getElementById(elementId)

  if (element && scrollbarRef.value) {
    const offset = element.offsetTop - 10
    scrollbarRef.value.setScrollTop(offset)

    element.classList.add('jump-highlight')
    setTimeout(() => {
      element.classList.remove('jump-highlight')
    }, 2000)
  }
}

watch(
  () => currentChatMessages.value,
  () => {
    if (!userHasScrolledUp.value || !isGenerating.value) {
      nextTick(() => {
        const wrap = scrollbarRef.value?.wrapRef
        if (wrap) wrap.scrollTop = wrap.scrollHeight
      })
    }
  },
  { deep: true },
)
</script>

<style scoped>
.mobile-chat-window {
  display: flex;
  flex-direction: column;
  height: var(--vv-height, 100dvh);
  height: var(--vv-height, 100vh);
  background-color: var(--color-background);
  overflow: hidden;
}

.mobile-messages {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.message-scrollbar {
  height: 100%;
}

.message-wrapper {
  padding: 12px 10px 24px;
}

.mobile-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

.welcome-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  opacity: 0.7;
}

.welcome-logo {
  width: 64px;
  height: 64px;
  border-radius: 16px;
}

.welcome-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-heading);
  letter-spacing: -0.3px;
}

.welcome-desc {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  max-width: 240px;
  line-height: 1.5;
}

.mobile-input-area {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-background);
  border-top: 0.5px solid var(--el-border-color-lighter);
  padding-bottom: env(safe-area-inset-bottom);
}

.pending-review-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin: 0 0 0 0;
  background: var(--el-color-warning-light-9);
  border-bottom: 1px solid var(--el-color-warning-light-5);
  font-size: 14px;
  color: var(--el-color-warning-dark-2);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}

.pending-review-bar span {
  flex: 1;
}

.pending-review-bar:active {
  background: var(--el-color-warning-light-7);
}

.mobile-input-area > * {
  padding-left: 10px;
  padding-right: 10px;
}

:deep(.jump-highlight) {
  animation: jump-pulse 0.5s ease-in-out 3;
  background-color: var(--el-color-primary-light-9);
  border-radius: 8px;
}

@keyframes jump-pulse {
  0%,
  100% {
    background-color: var(--el-color-primary-light-9);
    box-shadow: 0 0 8px var(--el-color-primary-light-5);
  }
  50% {
    background-color: var(--el-color-primary-light-7);
    box-shadow: 0 0 16px var(--el-color-primary-light-3);
  }
}
</style>
