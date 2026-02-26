<!-- frontend/mambo/src/mobile/components/chat/ChatWindow.vue -->
<template>
  <!-- 修改点：动态绑定 style，使用 fixed 定位强制适应可视区域 -->
  <div class="mobile-chat-window" :style="containerStyle">
    <!-- Header -->
    <ChatHeader
      :current-chat="currentChat"
      @toggle-drawer="$emit('toggle-drawer')"
      @open-settings="settingsDrawerVisible = true"
    />

    <!-- Messages Area -->
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
          />
        </div>
      </el-scrollbar>
    </div>

    <!-- Empty State -->
    <div class="mobile-empty" v-else>
      <el-empty :description="$t('chat.window.welcome')" />
    </div>

    <!-- Input Area -->
    <div class="mobile-input-area" v-if="currentChat">
      <input
        type="file"
        ref="fileInputRef"
        @change="onFileSelected"
        multiple
        style="display: none"
      />

      <!-- Attachment Preview -->
      <AttachmentPreview
        v-if="hasAttachments"
        :uploaded-files="uploadedFiles"
        :attached-resources="attachedSubmessageResources"
        :attached-knowledge-bases="attachedKnowledgeBases"
        @remove-file="removeUploadedFile"
        @remove-resource="removeAttachedResource"
        @remove-knowledge-base="handleRemoveKnowledgeBase"
      />

      <!-- Toolbar -->
      <ChatToolbar
        :current-chat="currentChat"
        :messages="currentChatMessages"
        :estimated-tokens="estimatedTokens"
        @trigger-file-upload="handleTriggerFileUpload"
        @open-resource-selector="resourceSelectorVisible = true"
        @toggle-mcp-tool="handleToggleMcpTool"
        @jump-to-message="handleJumpToMessage"
        @open-settings="settingsDrawerVisible = true"
      />

      <!-- Input Box -->
      <ChatInputBox
        ref="chatInputBoxRef"
        :is-generating="isGenerating"
        :is-send-button-disabled="isSendButtonDisabled"
        v-model="singlePartDraft"
        @send="handleSendMessage"
        @stop-generation="handleStopGeneration"
        @files-pasted="handleFileUploads"
      />
    </div>

    <!-- Settings Drawer -->
    <ChatSettingsDrawer
      v-model:visible="settingsDrawerVisible"
      :chat-data="currentChat"
      :grouped-models="groupedModels"
      @save="handleSaveSettings"
    />

    <!-- Resource Selector Dialog -->
    <ResourceSelectorDialog
      v-model:visible="resourceSelectorVisible"
      source="toolbar"
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
  reactive,
  type CSSProperties,
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
import ResourceSelectorDialog from './dialogs/ResourceSelectorDialog.vue'

import { useChatListStore } from '@/stores/chatListStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useProviderStore } from '@/stores/providerStore'
import { useResourceStore } from '@/stores/resourceStore'
import { useChatInput } from '@/composables/useChatInput'
import { useTokenEstimator } from '@/composables/useTokenEstimator'
import { uploadFile } from '@/api/chatService'
import type { AIModel, ChatUpdate, Resource, SubMessageCreate } from '@/api/types'

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
const resourceStore = useResourceStore()

const { currentChat, currentChatMessages, isGenerating, currentChatId, contextForTokenEstimation } =
  storeToRefs(chatSessionStore)
const { groupedModels } = storeToRefs(providerStore) as { groupedModels: Ref<GroupedModels[]> }
const { resources: allResources } = storeToRefs(resourceStore)

// --- State from Composables ---
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

// --- Local State ---
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>()
const chatInputBoxRef = ref()
const fileInputRef = ref<HTMLInputElement | null>(null)
const settingsDrawerVisible = ref(false)
const resourceSelectorVisible = ref(false)
const userHasScrolledUp = ref(false)

// --- 新增：可视区域布局状态 ---
const layoutStyle = reactive({
  top: '0px',
  height: '100%',
  width: '100%',
})

// 计算属性用于模板绑定
const containerStyle = computed<CSSProperties>(() => ({
  position: 'fixed',
  top: layoutStyle.top,
  height: layoutStyle.height,
  width: layoutStyle.width,
}))

// --- 新增：核心布局修复逻辑 ---
const updateLayout = () => {
  // 优先使用 visualViewport
  if (window.visualViewport) {
    const vv = window.visualViewport
    // 计算 top：由于页面可能滚动，我们需要计算可视区域在布局视口中的位置
    // 并将容器固定在当前可视区域的位置
    const top = vv.offsetTop
    const height = vv.height

    layoutStyle.top = `${top}px`
    layoutStyle.height = `${height}px`

    // 键盘弹起引起的视口变化时，确保输入框可见
    // 这里我们利用 nextTick 确保 DOM 更新后滚动
    nextTick(() => {
      const wrap = scrollbarRef.value?.wrapRef
      if (wrap) wrap.scrollTop = wrap.scrollHeight
    })
  } else {
    // 降级处理：如果浏览器不支持 visualViewport (极少见)，回退到 100dvh
    layoutStyle.top = '0px'
    layoutStyle.height = '100dvh'
  }
}

// --- Computed ---
const isSendButtonDisabled = computed(() => isGenerating.value || !isReadyToSend.value)

const hasAttachments = computed(
  () =>
    uploadedFiles.value.length > 0 ||
    attachedSubmessageResources.value.length > 0 ||
    attachedKnowledgeBases.value.length > 0,
)

// --- Token Estimation ---
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

// --- Knowledge Base Logic ---
const activeKnowledgeBaseId = computed(() => {
  const params = currentChat.value?.modelParameters
  if (!params?.enabled_mcp_ids) return null
  if (!Array.isArray(params.enabled_mcp_ids) && typeof params.enabled_mcp_ids === 'object') {
    const kbConfig = params.enabled_mcp_ids['system-knowledge-base']
    return kbConfig?.['MAMBOCHAT_RESOURCE_ID'] || null
  }
  return null
})

const attachedKnowledgeBases = computed(() => {
  const id = activeKnowledgeBaseId.value
  if (!id) return []
  const resource = allResources.value.find((r) => r.id === id)
  if (resource) return [resource]
  return []
})

watch(
  activeKnowledgeBaseId,
  (newId) => {
    if (newId) {
      const exists = allResources.value.some((r) => r.id === newId)
      if (!exists) resourceStore.fetchResourceDetails(newId)
    }
  },
  { immediate: true },
)

// --- Lifecycle Hooks ---
onMounted(() => {
  updateLayout() // 初始化布局
  if (window.visualViewport) {
    // 监听视口变化 (键盘弹起/落下, 滚动等)
    window.visualViewport.addEventListener('resize', updateLayout)
    window.visualViewport.addEventListener('scroll', updateLayout)
  }
  // 备用监听：某些浏览器在全屏切换时可能触发 window resize
  window.addEventListener('resize', updateLayout)
})

onUnmounted(() => {
  if (window.visualViewport) {
    window.visualViewport.removeEventListener('resize', updateLayout)
    window.visualViewport.removeEventListener('scroll', updateLayout)
  }
  window.removeEventListener('resize', updateLayout)
})

// --- Methods ---

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

// --- File Upload ---
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

// --- Resource & KB Mounting ---
function normalizeMcpIds(currentIds: any): Record<string, any> {
  if (!currentIds) return {}
  if (Array.isArray(currentIds)) {
    return currentIds.reduce(
      (acc, id) => {
        acc[id] = {}
        return acc
      },
      {} as Record<string, any>,
    )
  }
  if (typeof currentIds === 'object') return { ...currentIds }
  return {}
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

async function handleMountKnowledgeBase(resource: Resource) {
  if (!currentChat.value) return
  const currentParams = currentChat.value.modelParameters || {}
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids)
  mcpIds['system-knowledge-base'] = { MAMBOCHAT_RESOURCE_ID: resource.id }

  const updatedSettings: ChatUpdate = {
    modelParameters: { ...currentParams, enabled_mcp_ids: mcpIds },
  }
  await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings)
  ElMessage.success(`已启用知识库: ${resource.name}`)
}

async function handleRemoveKnowledgeBase() {
  if (!currentChat.value) return
  const currentParams = currentChat.value.modelParameters || {}
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids)
  if (mcpIds['system-knowledge-base']) {
    delete mcpIds['system-knowledge-base']
    const updatedSettings: ChatUpdate = {
      modelParameters: { ...currentParams, enabled_mcp_ids: mcpIds },
    }
    await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings)
    ElMessage.success('已停用知识库检索')
  }
}

async function handleToggleMcpTool(mcpId: string) {
  if (!currentChat.value) return
  const currentParams = currentChat.value.modelParameters || {}
  const mcpIds = normalizeMcpIds(currentParams.enabled_mcp_ids)
  if (mcpIds[mcpId]) {
    delete mcpIds[mcpId]
  } else {
    mcpIds[mcpId] = {}
  }
  const updatedSettings: ChatUpdate = {
    modelParameters: { ...currentParams, enabled_mcp_ids: mcpIds },
  }
  await chatListStore.updateChatSettings(currentChat.value.id, updatedSettings)
}

// --- Settings ---
async function handleSaveSettings(settings: ChatUpdate) {
  if (!currentChat.value) return
  await chatListStore.updateChatSettings(currentChat.value.id, settings)
  settingsDrawerVisible.value = false
  ElMessage.success(t('chat.settings.saveSuccess'))
}

// --- Scroll & Jump ---
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
/* 移除 height: 100dvh，改为由 JS 动态控制 */
.mobile-chat-window {
  /* position: fixed;  <- 由 JS 动态注入，这里为了性能可以预设，但会被 style 覆盖 */
  left: 0;
  right: 0;
  bottom: 0; /* 兜底 */
  display: flex;
  flex-direction: column;
  background-color: var(--color-background);
  overflow: hidden;
  /* 移除 transition，因为在全屏键盘弹起瞬间，transition 会导致动画不同步，感觉卡顿 */
}

.mobile-messages {
  flex-grow: 1;
  overflow: hidden;
  position: relative;
}

.message-scrollbar {
  height: 100%;
}

.message-wrapper {
  padding: 10px;
  padding-bottom: 20px;
}

.mobile-empty {
  flex-grow: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mobile-input-area {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--color-border);
  background: var(--color-background);
  /* Safe area for iOS */
  padding-bottom: env(safe-area-inset-bottom);
}

/* Padding for content inside input area to avoid overlap with notches */
.mobile-input-area > * {
  padding-left: 10px;
  padding-right: 10px;
}

.mobile-input-area > .mobile-toolbar {
  padding-left: 5px; /* Less padding for toolbar icons */
  padding-right: 5px;
}

/* Jump highlight animation */
:deep(.jump-highlight) {
  animation: jump-pulse 0.5s ease-in-out 3;
  background-color: var(--el-color-primary-light-9);
  border-radius: 6px;
}

@keyframes jump-pulse {
  0%,
  100% {
    background-color: var(--el-color-primary-light-9);
    box-shadow: 0 0 8px var(--el-color-primary-light-5);
  }
  50% {
    background-color: var(--el-color-primary-light-7);
    box-shadow: 0 0 12px var(--el-color-primary-light-3);
  }
}
</style>
