<!-- frontend/mambo/src/components/chat/ChatToolbar.vue -->
<template>
  <div class="chat-toolbar">
    <div class="toolbar-left">
      <div class="model-display">
        <el-icon><Cpu /></el-icon>
        <span>当前模型: <strong>{{ displayModelName }}</strong></span>
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
            <div class="zip-list-header">历史摘要列表</div>
            <el-scrollbar max-height="300px">
              <div
                v-for="item in zipHistoryItems"
                :key="item.messageId"
                class="zip-list-item"
                @click="$emit('jumpToMessage', item.messageId)"
              >
                <div class="zip-item-info">
                  <span class="zip-item-title">第 {{ item.index }} 条消息</span>
                  <el-tag
                    size="small"
                    :type="item.isEnabled ? 'success' : 'info'"
                    effect="plain"
                    class="zip-item-tag"
                  >
                    {{ item.isEnabled ? '已启用' : '未启用' }}
                  </el-tag>
                </div>
              </div>
            </el-scrollbar>
          </div>
        </el-popover>
      </div>
      <div class="token-counter" v-if="estimatedTokens > 0">
        <span>预估 Tokens: <strong>{{ estimatedTokens }}</strong></span>
        <el-tooltip
          content="仅供参考,实际消耗以usage或服务商账单为准"
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
        placement="bottom-end"
        :width="220"
        trigger="click"
      >
        <template #reference>
          <el-button
            :icon="Suitcase"
            circle
            title="MCP 工具"
          />
        </template>
        <div class="mcp-tool-list">
          <div class="mcp-header">可用工具</div>
          <div v-if="activeUserMcpServices.length === 0" class="mcp-empty">
            暂无可用工具
          </div>
          <div v-else class="mcp-items">
            <div
              v-for="tool in activeUserMcpServices"
              :key="tool.id"
              class="mcp-item"
            >
              <el-checkbox
                :model-value="isMcpToolEnabled(tool.id)"
                @change="$emit('toggleMcpTool', tool.id)"
              >
                <span :title="tool.description || tool.name">{{ tool.name }}</span>
              </el-checkbox>
            </div>
          </div>
        </div>
      </el-popover>

      <el-button
        :icon="Search"
        :type="isWebSearchEnabled ? 'primary' : ''"
        circle
        title="联网搜索"
        @click="$emit('toggleWebSearch')"
      />
      <el-button
        :icon="Upload"
        circle
        title="上传文件"
        @click="$emit('triggerFileUpload')"
      />
      <el-button
        :icon="Collection"
        circle
        title="从资源库选择"
        @click="$emit('openResourceSelector')"
      />
      <el-button
        :icon="Files"
        circle
        title="聊天分区"
        @click="$emit('toggleMultiPartMode')"
      />
      <el-button
        :icon="Setting"
        circle
        title="会话设置"
        @click="$emit('openSettings')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useProviderStore } from '@/stores/providerStore';
import { useMcpStore } from '@/stores/mcpStore';
import type { Chat, Message } from '@/api/types';
import type { PropType } from 'vue';
import {
  Cpu, Setting, Files, Tickets, Upload, Collection,
  QuestionFilled, Search, Suitcase
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

const providerStore = useProviderStore();
const mcpStore = useMcpStore();

const { activeUserMcpServices } = storeToRefs(mcpStore);

const displayModelName = computed(() => {
  if (!props.currentChat?.aiModelId) {
    return '未指定';
  }
  const model = providerStore.allModels.find(m => m.id === props.currentChat.aiModelId);
  return model ? model.name : '未知模型';
});

/**
 * 检查当前会话是否已启用系统联网搜索工具。
 * 目标 ID: system-ddgs-search
 */
const isWebSearchEnabled = computed((): boolean => {
  const mcpIds = props.currentChat?.modelParameters?.enabled_mcp_ids;
  return Array.isArray(mcpIds) && mcpIds.includes('system-ddgs-search');
});

/**
 * 检查指定 MCP 工具是否在当前会话中启用。
 */
const isMcpToolEnabled = (mcpId: string): boolean => {
  const mcpIds = props.currentChat?.modelParameters?.enabled_mcp_ids;
  return Array.isArray(mcpIds) && mcpIds.includes(mcpId);
};

/**
 * Computed property to extract messages containing ZipHistory sub-messages.
 * Used to render the history summary list in the toolbar.
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
}

.mcp-item .el-checkbox {
  width: 100%;
  margin-right: 0;
}

.mcp-item .el-checkbox__label span {
  display: inline-block;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
</style>
