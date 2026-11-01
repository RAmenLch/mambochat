<!-- frontend/mambo/src/mobile/components/chat/ChatToolbar.vue -->
<template>
  <div class="mobile-toolbar">
    <div class="toolbar-left">
      <div class="model-chip" @click="$emit('openSettings')">
        <el-icon :size="14"><User v-if="isAgentMode" /><Cpu v-else /></el-icon>
        <span class="model-name">{{ displayModelName }}</span>
      </div>

      <span v-if="estimatedTokens > 0" class="token-badge">
        <el-icon :size="12"><Coin /></el-icon>
        <span>{{ estimatedTokens }}</span>
      </span>

      <button v-if="usageStats" class="tool-chip usage-chip" @click="showUsageSheet = true">
        <el-icon :size="12"><Histogram /></el-icon>
        <span>{{ formatTokens(usageStats.active_path_main_agent.total_tokens) }}</span>
      </button>

      <button
        v-if="zipHistoryItems.length > 0"
        class="tool-chip zip-chip"
        @click="showZipPopover = !showZipPopover"
      >
        <el-icon :size="14"><Tickets /></el-icon>
        <span>{{ zipHistoryItems.length }}</span>
      </button>
    </div>

    <div class="toolbar-right">
      <button
        class="tool-btn web-search-btn"
        :class="{ active: !!webSearchMode && webSearchMode !== 'disable', direct: webSearchMode === 'direct_read', search: webSearchMode === 'search_and_read' }"
        @click="$emit('toggleWebSearch')"
      >
        <el-icon :size="18"><Search /></el-icon>
      </button>
      <button class="tool-btn" @click="$emit('openResourceSelector')">
        <el-icon :size="18"><Collection /></el-icon>
      </button>
      <button class="tool-btn" @click="showMorePopover = !showMorePopover">
        <el-icon :size="18"><MoreFilled /></el-icon>
      </button>
    </div>

    <!-- More Popover: MCP tools + Settings -->
    <Teleport to="body">
      <Transition name="sheet">
        <div v-if="showMorePopover" class="popover-overlay" @click="showMorePopover = false">
          <div class="popover-sheet" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-title">更多操作</div>
            <div class="sheet-items">
              <button class="sheet-item" @click="showMcpList = true; showMorePopover = false">
                <el-icon :size="20"><Suitcase /></el-icon>
                <span>MCP 工具</span>
              </button>
              <button
                v-if="showVersionHistory"
                class="sheet-item"
                @click="showMorePopover = false; $emit('openVersionHistory')"
              >
                <el-icon :size="20"><Timer /></el-icon>
                <span>{{ t('chat.toolbar.versionHistory') }}</span>
              </button>
              <button class="sheet-item" @click="handleExport('json')">
                <el-icon :size="20"><Document /></el-icon>
                <span>{{ t('chat.header.exportJson') }}</span>
              </button>
              <button class="sheet-item" @click="handleExport('markdown')">
                <el-icon :size="20"><Document /></el-icon>
                <span>{{ t('chat.header.exportMd') }}</span>
              </button>
              <button class="sheet-item" @click="handleExport('html')">
                <el-icon :size="20"><Document /></el-icon>
                <span>{{ t('chat.header.exportHtml') }}</span>
              </button>
              <button class="sheet-item" @click="triggerImport">
                <el-icon :size="20"><Upload /></el-icon>
                <span>{{ t('chat.header.importJson') }}</span>
              </button>
              <input
                ref="importInputRef"
                type="file"
                accept=".json,application/json"
                style="display: none"
                @change="handleImportFile"
              />
            </div>
            <button class="sheet-cancel" @click="showMorePopover = false">{{ t('common.action.cancel') }}</button>
          </div>
        </div>
      </Transition>

      <!-- MCP List -->
      <Transition name="sheet">
        <div v-if="showMcpList" class="popover-overlay" @click="showMcpList = false">
          <div class="popover-sheet" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-title">可用 MCP 工具</div>
            <div class="sheet-items">
              <div v-if="activeUserMcpServices.length === 0" class="sheet-empty">
                暂无可用工具
              </div>
              <label
                v-for="tool in activeUserMcpServices"
                :key="tool.id"
                class="sheet-item checkbox-item"
              >
                <input
                  type="checkbox"
                  :checked="isMcpToolEnabled(tool.id)"
                  @change="$emit('toggleMcpTool', tool.id)"
                />
                <span>{{ tool.name }}</span>
              </label>
            </div>
            <button class="sheet-cancel" @click="showMcpList = false">{{ t('common.action.cancel') }}</button>
          </div>
        </div>
      </Transition>

      <!-- Zip History List -->
      <Transition name="sheet">
        <div v-if="showZipPopover" class="popover-overlay" @click="showZipPopover = false">
          <div class="popover-sheet" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-title">历史压缩记录</div>
            <div class="sheet-items">
              <button
                v-for="item in zipHistoryItems"
                :key="item.messageId"
                class="sheet-item"
                @click="handleJumpToMessage(item.messageId); showZipPopover = false"
              >
                <span>第 {{ item.index }} 条消息</span>
                <span class="zip-status-dot" :class="{ enabled: item.isEnabled }"></span>
              </button>
            </div>
            <button class="sheet-cancel" @click="showZipPopover = false">{{ t('common.action.cancel') }}</button>
          </div>
        </div>
      </Transition>

      <!-- 会话用量统计 -->
      <Transition name="sheet">
        <div v-if="showUsageSheet" class="popover-overlay" @click="showUsageSheet = false">
          <div class="popover-sheet" @click.stop>
            <div class="sheet-handle"></div>
            <div class="sheet-title">{{ t('chat.toolbar.usageConversation') }}</div>
            <div class="usage-sheet-body">
              <div v-for="section in usageSections" :key="section.key" class="usage-section">
                <div class="usage-section-title">{{ section.title }}</div>
                <div class="usage-row">
                  <span class="usage-label">{{ t('chat.toolbar.usageTotal') }}</span>
                  <span class="usage-value">{{ formatTokens(section.data.total_tokens) }}</span>
                </div>
                <div class="usage-row">
                  <span class="usage-label">{{ t('chat.toolbar.usageInput') }}</span>
                  <span class="usage-value">{{ formatTokens(section.data.prompt_tokens) }}</span>
                </div>
                <div class="usage-row">
                  <span class="usage-label">{{ t('chat.toolbar.usageOutput') }}</span>
                  <span class="usage-value">{{ formatTokens(section.data.completion_tokens) }}</span>
                </div>
                <div class="usage-row">
                  <span class="usage-label">{{ t('chat.toolbar.usageCacheHit') }}</span>
                  <span class="usage-value">
                    {{ formatTokens(section.data.cache_hit_tokens) }}
                    <span v-if="cacheHitRate(section.data)" class="usage-rate">{{ cacheHitRate(section.data) }}</span>
                  </span>
                </div>
              </div>
            </div>
            <button class="sheet-cancel" @click="showUsageSheet = false">{{ t('common.action.close') }}</button>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useProviderStore } from '@/stores/providerStore'
import { useMcpStore } from '@/stores/mcpStore'
import { useAgentStore } from '@/stores/agentStore'
import type { Chat, ChatUsageStats, Message } from '@/api/types'
import type { PropType } from 'vue'
import { getChatUsage, importChat } from '@/api/chatService'
import { exportChat, type ChatExportFormat } from '@/utils/chatExport'
import {
  Cpu, Collection, Coin, Suitcase, Tickets, MoreFilled, User, Search,
  Histogram, Document, Upload, Timer,
} from '@element-plus/icons-vue'

const props = defineProps({
  currentChat: {
    type: Object as PropType<Chat>,
    required: true,
  },
  messages: {
    type: Array as PropType<Message[]>,
    default: () => [],
  },
  estimatedTokens: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits([
  'openSettings',
  'openResourceSelector',
  'toggleMcpTool',
  'jumpToMessage',
  'toggleWebSearch',
  'openVersionHistory',
  'imported',
])

const { t } = useI18n()
const providerStore = useProviderStore()
const mcpStore = useMcpStore()
const agentStore = useAgentStore()
const { activeUserMcpServices } = storeToRefs(mcpStore)

const showMorePopover = ref(false)
const showMcpList = ref(false)
const showZipPopover = ref(false)

const displayModelName = computed(() => {
  if (props.currentChat?.chatMode === 'agent') {
    if (props.currentChat.agentId) {
      const agent = agentStore.allAgents.find(a => a.id === props.currentChat!.agentId)
      if (agent) return agent.name
    }
    return t('common.status.unspecified')
  }
  if (!props.currentChat?.aiModelId) return t('common.status.unspecified')
  const model = providerStore.allModels.find((m) => m.id === props.currentChat.aiModelId)
  return model ? model.name : t('common.status.unknownModel')
})

const isAgentMode = computed(() => props.currentChat?.chatMode === 'agent')

const webSearchMode = computed((): 'direct_read' | 'search_and_read' | 'disable' | null => {
  return props.currentChat?.web_search_mode ?? null
})

const isMcpToolEnabled = (mcpId: string): boolean => {
  return props.currentChat?.enabled_mcp_ids?.includes(mcpId) ?? false
}

const zipHistoryItems = computed(() => {
  return props.messages.reduce<Array<{ messageId: string; index: number; isEnabled: boolean }>>((items, msg, index) => {
    const zipSub = msg.sub_messages.find((sm) => sm.type === 'ZipHistory')
    if (zipSub) {
      items.push({
        messageId: msg.id,
        index: index + 1,
        isEnabled: zipSub.config.zip_enable === true,
      })
    }
    return items
  }, [])
})

function handleJumpToMessage(messageId: string) {
  emit('jumpToMessage', messageId)
}

// --- 会话累计用量（B8） ---
const usageStats = ref<ChatUsageStats | null>(null)
const showUsageSheet = ref(false)

const fetchUsage = async () => {
  const chatId = props.currentChat?.id
  if (!chatId) return
  try {
    usageStats.value = await getChatUsage(chatId)
  } catch {
    // 用量统计失败不阻塞工具栏
  }
}

watch(
  () => props.currentChat?.id,
  () => {
    usageStats.value = null
    fetchUsage()
  },
  { immediate: true },
)

/** 消息中出现新的 Usage 子消息时刷新统计 */
const usageSubMessageCount = computed(() => {
  let count = 0
  for (const msg of props.messages || []) {
    for (const sm of msg.sub_messages || []) {
      if (sm.type === 'Usage') count += 1
    }
  }
  return count
})

watch(usageSubMessageCount, (val, old) => {
  if (val !== old) fetchUsage()
})

function formatTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k'
  return String(n)
}

/** 缓存命中率 = 缓存命中量 / 输入量 */
function cacheHitRate(agg: ChatUsageStats['conversation']): string | null {
  if (agg.prompt_tokens <= 0) return null
  return ((agg.cache_hit_tokens / agg.prompt_tokens) * 100).toFixed(1) + '%'
}

const usageSections = computed(() => {
  if (!usageStats.value) return []
  return [
    { key: 'active', title: t('chat.toolbar.usageActivePath'), data: usageStats.value.active_path_main_agent },
    { key: 'conversation', title: t('chat.toolbar.usageConversation'), data: usageStats.value.conversation },
  ]
})

// --- 版本历史入口（B4） ---
/** 仅在 Agent 模式下且 Agent 启用了版本控制时显示 */
const showVersionHistory = computed(() => {
  const chat = props.currentChat
  if (chat?.chatMode !== 'agent' || !chat.agentId) return false
  const agent = agentStore.allAgents.find(a => a.id === chat.agentId) ||
    agentStore.agentList.find(a => a.id === chat.agentId)
  if (!agent) return false
  const params = (agent as any).agentParameters
  return params?.version_control?.enabled === true
})

// --- 导出 / 导入（B5） ---
const isExporting = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)

async function handleExport(format: ChatExportFormat) {
  if (isExporting.value) return
  isExporting.value = true
  try {
    await exportChat(props.currentChat, props.messages || [], format)
    showMorePopover.value = false
  } catch (error) {
    console.error('Export failed:', error)
    ElMessage.error(t('chat.header.exportFailed'))
  } finally {
    isExporting.value = false
  }
}

function triggerImport() {
  showMorePopover.value = false
  importInputRef.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  try {
    const report = await importChat(file)
    ElMessage.success(t('chat.header.importSuccess', { name: report.name }))
    emit('imported', report.chat_id)
  } catch (error) {
    console.error('Chat import failed:', error)
    ElMessage.error(t('common.error.operationFailed'))
  }
}
</script>

<style scoped>
.mobile-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  gap: 8px;
  min-height: 36px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  flex: 1;
  min-width: 0;
}

.model-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  font-size: 12px;
  color: var(--el-text-color-regular);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px;
  transition: background-color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.model-chip:active {
  background: var(--el-fill-color);
}

.model-name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.token-badge {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

.tool-chip {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 4px 8px;
  border-radius: 10px;
  border: none;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
  font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}

.toolbar-right {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.tool-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
  -webkit-tap-highlight-color: transparent;
}

.tool-btn:active {
  background: var(--el-fill-color-light);
  color: var(--el-color-primary);
}

.web-search-btn.active {
  color: var(--el-color-primary);
}

.web-search-btn.direct {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.web-search-btn.search {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}

/* 会话用量统计 */
.usage-chip {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.usage-sheet-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 2px 8px;
}

.usage-section {
  background: var(--el-fill-color-light);
  border-radius: 10px;
  padding: 10px 12px;
}

.usage-section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  margin-bottom: 6px;
}

.usage-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 2px 0;
}

.usage-label {
  color: var(--el-text-color-secondary);
}

.usage-value {
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}

.usage-rate {
  color: var(--el-text-color-secondary);
  font-size: 11px;
  margin-left: 4px;
}

/* Popover Sheet (reusable) */
.popover-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.popover-sheet {
  width: 100%;
  max-width: 500px;
  background: var(--color-background);
  border-radius: 16px 16px 0 0;
  padding: 8px 16px;
  padding-bottom: max(16px, env(safe-area-inset-bottom));
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--el-border-color);
  border-radius: 2px;
  margin: 8px auto 12px;
}

.sheet-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  padding: 0 4px;
}

.sheet-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 50vh;
  overflow-y: auto;
}

.sheet-item {
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
  text-align: left;
  -webkit-tap-highlight-color: transparent;
}

.sheet-item:active {
  background: var(--el-fill-color-light);
}

.sheet-item.checkbox-item {
  cursor: pointer;
}

.sheet-item.checkbox-item input[type="checkbox"] {
  width: 20px;
  height: 20px;
  accent-color: var(--el-color-primary);
  flex-shrink: 0;
}

.sheet-empty {
  padding: 20px;
  text-align: center;
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.zip-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-text-color-placeholder);
  margin-left: auto;
}

.zip-status-dot.enabled {
  background: var(--el-color-success);
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

/* Transitions */
.sheet-enter-active {
  transition: all 0.25s ease-out;
}
.sheet-leave-active {
  transition: all 0.2s ease-in;
}
.sheet-enter-from .popover-sheet,
.sheet-leave-to .popover-sheet {
  transform: translateY(100%);
}
.sheet-enter-from {
  opacity: 0;
}
.sheet-leave-to {
  opacity: 0;
}
</style>
