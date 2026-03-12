<!-- frontend/mambo/src/components/chat/ChatToolbar.vue -->
<template>
  <div class="chat-toolbar">
    <div class="toolbar-left">
      <div class="model-display">
        <el-icon><Cpu /></el-icon>
        <span>{{ t('chat.toolbar.currentModel') }}: <strong>{{ displayModelName }}</strong></span>
      </div>
      <div class="zip-history-list-trigger" v-if="zipHistoryItems.length > 0">
        <el-popover
          placement="top"
          :width="240"
          trigger="click"
          popper-class="zip-history-popover"
        >
          <template #reference>
            <el-button size="small" text bg class="zip-trigger-btn">
              <el-icon><Tickets /></el-icon>
            </el-button>
          </template>

          <div class="zip-list-container">
            <div class="zip-list-header">{{ t('chat.toolbar.zipHistoryList') }}</div>
            <el-scrollbar max-height="300px">
              <div
                v-for="item in zipHistoryItems"
                :key="item.messageId"
                class="zip-list-item"
                @click="$emit('jumpToMessage', item.messageId)"
              >
                <div class="zip-item-info">
                  <span class="zip-item-title">{{ t('chat.toolbar.messageIndex', { index: item.index }) }}</span>
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
      </div>
      <div class="token-counter" v-if="estimatedTokens > 0">
        <span>{{ t('chat.toolbar.estimatedTokens') }}: <strong>{{ estimatedTokens }}</strong></span>
        <el-tooltip
          :content="t('chat.toolbar.tokenTooltip')"
          placement="top"
          effect="dark"
        >
          <el-icon class="token-tooltip-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
    </div>

    <div class="actions">
      <!-- MCP 工具选择器 -->
      <el-popover
        placement="top"
        :width="260"
        trigger="click"
      >
        <template #reference>
          <el-button
            :icon="Suitcase"
            circle
            :title="t('chat.toolbar.availableTools')"
          />
        </template>
        <div class="mcp-tool-list">
          <div class="mcp-header">{{ t('chat.toolbar.availableTools') }}</div>
          <div v-if="activeUserMcpServices.length === 0" class="mcp-empty">
            {{ t('chat.toolbar.noTools') }}
          </div>
          <div v-else class="mcp-items">
            <div
              v-for="tool in activeUserMcpServices"
              :key="tool.id"
              class="mcp-item"
            >
              <div class="mcp-item-left">
                <el-checkbox
                  :model-value="isMcpToolEnabled(tool.id)"
                  @change="$emit('toggleMcpTool', tool.id)"
                >
                  <span :title="tool.description || tool.name">{{ tool.name }}</span>
                </el-checkbox>
              </div>

              <div class="mcp-item-right">
                <div
                  class="mcp-status-dot"
                  :class="getMcpStatusClass(tool.last_status)"
                  :title="getMcpStatusTitle(tool.last_status)"
                ></div>
                <el-button
                  link
                  size="small"
                  :icon="Refresh"
                  class="mcp-test-btn"
                  :loading="testingMcpIds.has(tool.id)"
                  @click.stop="handleTestMcpTool(tool.id)"
                  :title="t('chat.toolbar.testConnection')"
                />
              </div>
            </div>
          </div>
        </div>
      </el-popover>

      <el-button
        :icon="Search"
        :type="isWebSearchEnabled ? 'primary' : ''"
        circle
        :title="t('chat.toolbar.webSearch')"
        @click="$emit('toggleWebSearch')"
      />
      <el-button
        :icon="Upload"
        circle
        :title="t('common.action.upload')"
        @click="$emit('triggerFileUpload')"
      />
      <el-button
        :icon="Collection"
        circle
        :title="t('chat.settings.selectFromResource')"
        @click="$emit('openResourceSelector')"
      />
      <el-button
        :icon="Files"
        circle
        :title="t('chat.toolbar.chatPartition')"
        @click="$emit('toggleMultiPartMode')"
      />
      <el-button
        :icon="Setting"
        circle
        :title="t('chat.toolbar.chatSettings')"
        @click="$emit('openSettings')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue';
import { storeToRefs } from 'pinia';
import { useI18n } from 'vue-i18n';
import { useProviderStore } from '@/stores/providerStore';
import { useMcpStore } from '@/stores/mcpStore';
import type { Chat, Message, McpHealthStatus } from '@/api/types';
import type { PropType } from 'vue';
import { ElMessage } from 'element-plus';
import {
  Cpu, Setting, Files, Tickets, Upload, Collection,
  QuestionFilled, Search, Suitcase, Refresh
} from '@element-plus/icons-vue';

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
});

defineEmits([
  'openSettings',
  'toggleMultiPartMode',
  'triggerFileUpload',
  'openResourceSelector',
  'jumpToMessage',
  'toggleWebSearch',
  'toggleMcpTool'
]);

const { t } = useI18n();
const providerStore = useProviderStore();
const mcpStore = useMcpStore();

const { activeUserMcpServices } = storeToRefs(mcpStore);

// 本地状态：正在测试连接的 MCP ID 集合
const testingMcpIds = reactive(new Set<string>());

const displayModelName = computed(() => {
  if (!props.currentChat?.aiModelId) {
    return t('common.status.unspecified');
  }
  const model = providerStore.allModels.find(m => m.id === props.currentChat.aiModelId);
  return model ? model.name : t('common.status.unknownModel');
});

/**
 * 检查当前会话是否已启用系统联网搜索工具。
 * 目标 ID: system-ddgs-search
 */
const isWebSearchEnabled = computed((): boolean => {
  const mcpIds = props.currentChat?.enabled_mcp_ids;
  if (!mcpIds) return false;
  return mcpIds.includes('system-ddgs-search');
});

/**
 * 检查指定 MCP 工具是否在当前会话中启用。
 */
const isMcpToolEnabled = (mcpId: string): boolean => {
  const mcpIds = props.currentChat?.enabled_mcp_ids;
  if (!mcpIds) return false;
  return mcpIds.includes(mcpId);
};

/**
 * 提取包含 ZipHistory 子消息的消息，用于渲染工具栏中的历史摘要列表。
 */
const zipHistoryItems = computed(() => {
  const items: Array<{ messageId: string; index: number; isEnabled: boolean }> = [];

  props.messages.forEach((msg, index) => {
    const zipSub = msg.sub_messages.find(sm => sm.type === 'ZipHistory');
    if (zipSub) {
      items.push({
        messageId: msg.id,
        index: index + 1,
        isEnabled: zipSub.config.zip_enable === true,
      });
    }
  });

  return items;
});

/**
 * 处理 MCP 工具连接测试
 */
const handleTestMcpTool = async (mcpId: string) => {
  if (testingMcpIds.has(mcpId)) return;

  testingMcpIds.add(mcpId);
  try {
    await mcpStore.testConnection(mcpId);
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : t('common.status.connectionFailed');
    ElMessage.error(detail);
  } finally {
    testingMcpIds.delete(mcpId);
  }
};

const getMcpStatusClass = (status: McpHealthStatus) => {
  switch (status) {
    case 'healthy': return 'status-healthy';
    case 'unhealthy': return 'status-unhealthy';
    default: return 'status-unknown';
  }
};

const getMcpStatusTitle = (status: McpHealthStatus) => {
  switch (status) {
    case 'healthy': return t('chat.toolbar.mcpStatus.healthy');
    case 'unhealthy': return t('chat.toolbar.mcpStatus.unhealthy');
    default: return t('chat.toolbar.mcpStatus.unknown');
  }
};
</script>

<style scoped>
.chat-toolbar {
  flex-shrink: 0;
  padding: 8px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--color-border);
  background-color: var(--color-background-soft);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-display,
.token-counter,
.zip-history-list-trigger {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.model-display .el-icon,
.token-counter .el-icon {
  margin-right: 8px;
}

.model-display strong,
.token-counter strong {
  color: var(--el-text-color-primary);
  font-weight: 600;
  margin-left: 4px;
}

.token-tooltip-icon {
  margin-left: 6px;
  cursor: help;
  color: var(--el-text-color-placeholder);
}

.zip-trigger-btn {
  padding: 5px 10px;
  height: 28px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.zip-trigger-btn .el-icon {
  margin-right: 0;
}

.actions {
  display: flex;
  gap: 8px;
}

/* Popover Styles */
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

.zip-list-item:hover {
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

/* MCP Tool List Styles */
.mcp-tool-list {
  display: flex;
  flex-direction: column;
}

.mcp-header {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 8px;
}

.mcp-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  text-align: center;
  padding: 8px 0;
}

.mcp-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.mcp-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
}

.mcp-item-left {
  flex: 1;
  min-width: 0;
  margin-right: 8px;
}

.mcp-item-left .el-checkbox {
  width: 100%;
  margin-right: 0;
  height: auto;
}

.mcp-item-left :deep(.el-checkbox__label) {
  width: 100%;
  padding-left: 8px;
}

.mcp-item-left .el-checkbox__label span {
  display: block;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}

.mcp-item-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.mcp-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-healthy {
  background-color: var(--el-color-success);
  box-shadow: 0 0 3px var(--el-color-success-light-5);
}

.status-unhealthy {
  background-color: var(--el-color-danger);
  box-shadow: 0 0 3px var(--el-color-danger-light-5);
}

.status-unknown {
  background-color: var(--el-color-info-light-3);
  border: 1px solid var(--el-color-info-light-5);
}

.mcp-test-btn {
  padding: 4px;
  height: 24px;
  width: 24px;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.mcp-test-btn:hover {
  color: var(--el-color-primary);
  background-color: var(--el-fill-color-light);
}
</style>
