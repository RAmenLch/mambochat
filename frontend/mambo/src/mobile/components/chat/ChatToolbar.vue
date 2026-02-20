<!-- frontend/mambo/src/mobile/components/chat/ChatToolbar.vue -->
<template>
  <div class="mobile-toolbar">
    <div class="toolbar-left">
      <div class="model-display">
        <el-icon><Cpu /></el-icon>
        <span class="model-name">{{ displayModelName }}</span>
      </div>

      <!-- Zip History Jump Button -->
      <el-popover
        v-if="zipHistoryItems.length > 0"
        placement="top"
        :width="220"
        trigger="click"
        popper-class="zip-history-popover"
      >
        <template #reference>
          <el-button size="small" text class="zip-trigger-btn">
            <el-icon><Tickets /></el-icon>
            <span class="zip-count">{{ zipHistoryItems.length }}</span>
          </el-button>
        </template>

        <div class="zip-list-container">
          <div class="zip-list-header">{{ t('chat.toolbar.zipHistoryList') }}</div>
          <el-scrollbar max-height="250px">
            <div
              v-for="item in zipHistoryItems"
              :key="item.messageId"
              class="zip-list-item"
              @click="handleJumpToMessage(item.messageId)"
            >
              <div class="zip-item-info">
                <span class="zip-item-title">{{
                  t('chat.toolbar.messageIndex', { index: item.index })
                }}</span>
                <el-tag
                  size="small"
                  :type="item.isEnabled ? 'success' : 'info'"
                  effect="plain"
                  class="zip-item-tag"
                >
                  {{ item.isEnabled ? t('common.status.enabled') : t('common.status.disabled') }}
                </el-tag>
              </div>
            </div>
          </el-scrollbar>
        </div>
      </el-popover>

      <!-- Token Estimate: Click to Show -->
      <el-popover placement="top" :width="180" trigger="click" v-if="estimatedTokens > 0">
        <template #reference>
          <el-button size="small" text class="token-btn">
            <el-icon><Coin /></el-icon>
            <span>{{ estimatedTokens }}</span>
          </el-button>
        </template>
        <div class="token-detail">
          <span>{{ t('chat.toolbar.estimatedTokens') }} :</span>
          <strong>{{ estimatedTokens }}</strong>
        </div>
      </el-popover>
    </div>

    <div class="toolbar-right">
      <!-- MCP Tools -->
      <el-popover placement="top-start" :width="280" trigger="click">
        <template #reference>
          <el-button :icon="Suitcase" circle size="small" />
        </template>
        <div class="mcp-tool-list">
          <div class="mcp-header">{{ t('chat.toolbar.availableTools') }}</div>
          <div v-if="activeUserMcpServices.length === 0" class="mcp-empty">
            {{ t('chat.toolbar.noTools') }}
          </div>
          <div v-else class="mcp-items">
            <div v-for="tool in activeUserMcpServices" :key="tool.id" class="mcp-item">
              <el-checkbox
                :model-value="isMcpToolEnabled(tool.id)"
                @change="$emit('toggleMcpTool', tool.id)"
              >
                {{ tool.name }}
              </el-checkbox>
            </div>
          </div>
        </div>
      </el-popover>

      <!-- Upload File -->
      <el-button :icon="Upload" circle size="small" @click="$emit('triggerFileUpload')" />

      <!-- Resource Selector -->
      <el-button :icon="Collection" circle size="small" @click="$emit('openResourceSelector')" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { useProviderStore } from '@/stores/providerStore'
import { useMcpStore } from '@/stores/mcpStore'
import type { Chat, Message } from '@/api/types'
import type { PropType } from 'vue'
import { Cpu, Upload, Collection, Coin, Suitcase, Tickets } from '@element-plus/icons-vue'

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
  'triggerFileUpload',
  'openResourceSelector',
  'toggleMcpTool',
  'jumpToMessage',
])

const { t } = useI18n()
const providerStore = useProviderStore()
const mcpStore = useMcpStore()
const { activeUserMcpServices } = storeToRefs(mcpStore)

const displayModelName = computed(() => {
  if (!props.currentChat?.aiModelId) return t('common.status.unspecified')
  const model = providerStore.allModels.find((m) => m.id === props.currentChat.aiModelId)
  return model ? model.name : t('common.status.unknownModel')
})

const isMcpToolEnabled = (mcpId: string): boolean => {
  const mcpIds = props.currentChat?.modelParameters?.enabled_mcp_ids
  if (!mcpIds) return false
  if (Array.isArray(mcpIds)) return mcpIds.includes(mcpId)
  if (typeof mcpIds === 'object') return Object.prototype.hasOwnProperty.call(mcpIds, mcpId)
  return false
}

/**
 * 提取包含 ZipHistory 子消息的消息，用于渲染工具栏中的历史摘要列表。
 */
const zipHistoryItems = computed(() => {
  const items: Array<{ messageId: string; index: number; isEnabled: boolean }> = []

  props.messages.forEach((msg, index) => {
    const zipSub = msg.sub_messages.find((sm) => sm.type === 'ZipHistory')
    if (zipSub) {
      items.push({
        messageId: msg.id,
        index: index + 1,
        isEnabled: zipSub.config.zip_enable === true,
      })
    }
  })

  return items
})

function handleJumpToMessage(messageId: string) {
  emit('jumpToMessage', messageId)
}
</script>

<style scoped>
.mobile-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 8px;
  padding-bottom: 8px;
  min-height: 40px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  overflow: hidden;
  gap: 4px;
}

.model-display {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--el-text-color-regular);
  margin-right: 4px;
}

.model-display .el-icon {
  margin-right: 4px;
  color: var(--el-text-color-secondary);
}

.model-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100px;
}

.zip-trigger-btn {
  padding: 4px 8px;
  font-size: 13px;
  color: var(--el-color-primary);
  display: flex;
  align-items: center;
  gap: 2px;
}

.zip-count {
  font-weight: 600;
}

.token-btn {
  padding: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.token-detail {
  text-align: center;
}

.toolbar-right {
  display: flex;
  gap: 4px;
}

/* MCP Popover Styles */
.mcp-tool-list {
  max-height: 300px;
  overflow-y: auto;
}

.mcp-header {
  font-weight: bold;
  margin-bottom: 8px;
  font-size: 13px;
}

.mcp-item {
  padding: 4px 0;
}

/* Zip History List Styles */
.zip-list-container {
  display: flex;
  flex-direction: column;
}

.zip-list-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  padding: 0 8px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 4px;
}

.zip-list-item {
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.zip-list-item:active {
  background-color: var(--el-fill-color-light);
}

.zip-item-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.zip-item-title {
  font-size: 13px;
  color: var(--el-text-color-regular);
}

.zip-item-tag {
  margin-left: 8px;
}
</style>
