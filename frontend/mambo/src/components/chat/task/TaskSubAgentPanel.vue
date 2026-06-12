<!-- frontend/mambo/src/components/chat/task/TaskSubAgentPanel.vue -->
<template>
  <div class="subagent-panel">
    <!-- 思考区域 (Reasoning) -->
    <div class="bubble-section reasoning-section" v-if="reasoningSection && !isReasoningMinimized">
      <div class="section-title" @click="isReasoningMinimized = true">
        {{ t('chat.message.reasoning') }}
      </div>
      <div class="section-content">
        <BubbleSectionGroup
          v-for="group in reasoningSection.groups"
          :key="group.id"
          :group="group"
          :parent-message="virtualMessage"
          :is-generating="false"
          :is-inactive="false"
          :show-edit="false"
          :external-collapsed="isSubMsgCollapsed(group.textSubMessage?.id)"
          @copy="handleCopy"
          @toggle-collapse="handleToggleCollapse"
          @open-tool-dialog="handleToolClick"
        />
      </div>
    </div>
    <div v-else-if="reasoningSection" class="reasoning-minimized-block" @click="isReasoningMinimized = false">
      {{ t('chat.message.reasoningCollapsed') }}
    </div>

    <!-- 正文区域 (Normal) -->
    <div class="bubble-section normal-section" v-if="normalSection">
      <div class="section-content">
        <BubbleSectionGroup
          v-for="group in normalSection.groups"
          :key="group.id"
          :group="group"
          :parent-message="virtualMessage"
          :is-generating="false"
          :is-inactive="false"
          :show-edit="false"
          :external-collapsed="isSubMsgCollapsed(group.textSubMessage?.id)"
          @copy="handleCopy"
          @toggle-collapse="handleToggleCollapse"
          @open-tool-dialog="handleToolClick"
        />
      </div>
    </div>

    <div v-if="!reasoningSection && !normalSection" class="empty-state">
      {{ t('chat.subagent.noSteps') }}
    </div>

    <McpToolDialog
      v-model:visible="toolDialogVisible"
      :parent-message-id="null"
      :parent-message="toolDialogParentMsg"
      :initial-sub-message-id="toolDialogInitialId"
      mode="single"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import type { Message, MessageRole, MessageStatus, SubMessage, SubMessageType, TaskSubStepContent } from '@/api/types';
import { useAssistantTimeline } from '@/composables/useAssistantTimeline';
import { copyToClipboard } from '@/utils/clipboard';
import BubbleSectionGroupComponent from '../message/BubbleSectionGroup.vue';
import McpToolDialog from '../dialogs/McpToolDialog.vue';

const BubbleSectionGroup = BubbleSectionGroupComponent;
const { t } = useI18n();

const props = defineProps<{
  steps: SubMessage[];
}>();

/** 本地折叠状态：子代理追踪面板内子消息的折叠与展开 */
const collapsedSubMsgIds = ref<Set<string>>(new Set());

function isSubMsgCollapsed(id: string | undefined): boolean | undefined {
  if (!id) return undefined;
  // 返回 undefined 会让 BubbleSectionGroup 走默认 store 逻辑，
  // 但这里我们总是需要外部控制折叠状态
  return collapsedSubMsgIds.value.has(id);
}

function handleToggleCollapse(subMsgId: string) {
  const next = new Set(collapsedSubMsgIds.value);
  if (next.has(subMsgId)) {
    next.delete(subMsgId);
  } else {
    next.add(subMsgId);
  }
  collapsedSubMsgIds.value = next;
}

async function handleCopy(subMessage: SubMessage) {
  try {
    await copyToClipboard(subMessage.content);
    ElMessage.success(t('common.msg.copySuccess'));
  } catch {
    ElMessage.error(t('common.msg.copyFailed'));
  }
}

/** 将 TaskSubStep 数组转换为虚拟 Message，子消息使用 Reasoning/Normal/McpTool 类型 */
const virtualMessage = computed<Message>(() => {
  const subMessages: SubMessage[] = [];

  for (let i = 0; i < props.steps.length; i++) {
    const sm = props.steps[i];
    let stepData: TaskSubStepContent;
    try {
      stepData = JSON.parse(sm.content) as TaskSubStepContent;
    } catch {
      continue;
    }

    switch (stepData.display_type) {
      case 'reasoning':
        subMessages.push({
          ...sm,
          type: 'Reasoning' as SubMessageType,
          content: stepData.content,
          config: { is_collapsed: false, is_minimal: true },
        } as SubMessage);
        break;

      case 'text':
        subMessages.push({
          ...sm,
          type: 'Normal' as SubMessageType,
          content: stepData.content,
          config: { is_collapsed: false },
        } as SubMessage);
        break;

      case 'tool_call': {
        // 查找后续 matching tool_result 合并
        let resultText: string | null = null;
        for (let j = i + 1; j < props.steps.length; j++) {
          try {
            const next = JSON.parse(props.steps[j].content) as TaskSubStepContent;
            if (next.display_type === 'tool_result' && next.tool_name === stepData.tool_name) {
              resultText = next.content;
              break;
            }
          } catch { /* skip */ }
        }
        const toolCallId = `${stepData.tool_call_id}_s_${stepData.step_order}`;
        subMessages.push({
          ...sm,
          type: 'McpTool' as SubMessageType,
          content: JSON.stringify({
            tool_call_id: toolCallId,
            name: stepData.tool_name || '',
            arguments: typeof stepData.tool_args === 'string'
              ? stepData.tool_args
              : JSON.stringify(stepData.tool_args || {}),
            result: resultText,
            is_error: false,
          }),
          config: { is_collapsed: false },
        } as SubMessage);
        break;
      }

      // tool_result: skip（已合并到上方 tool_call）
    }
  }

  return {
    id: props.steps[0]?.id || '',
    createdAt: props.steps[0]?.createdAt || new Date().toISOString(),
    role: 'assistant' as MessageRole,
    chatId: '',
    sortOrder: 0,
    sub_messages: subMessages,
    status: 'completed' as MessageStatus,
    parentId: null,
    lastActiveAt: props.steps[0]?.createdAt || new Date().toISOString(),
    sibling_ids: [],
    sibling_index: 0,
  };
});

const messageRef = computed(() => virtualMessage.value);
const { reasoningSection, normalSection } = useAssistantTimeline(messageRef);
const isReasoningMinimized = ref(true);

// ── 子代理工具调用弹窗 ──
const toolDialogVisible = ref(false);
const toolDialogParentMsg = ref<Message | null>(null);
const toolDialogInitialId = ref('');

function handleToolClick(subMessageId: string) {
  toolDialogParentMsg.value = virtualMessage.value;
  toolDialogInitialId.value = subMessageId;
  toolDialogVisible.value = true;
}
</script>

<style scoped>
.subagent-panel {
  padding: 4px 0;
}

/* 思考区域 */
.reasoning-section {
  position: relative;
  margin-bottom: 16px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  font-weight: bold;
  margin-bottom: 8px;
  cursor: pointer;
  user-select: none;
}
.section-title:hover {
  color: var(--el-text-color-primary);
}

/* 推理最小化态 */
.reasoning-minimized-block {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  margin-bottom: 16px;
  background-color: #fafafa;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  font-size: 13px;
  color: var(--el-text-color-primary);
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.reasoning-minimized-block:hover {
  background-color: #f5f5f5;
  border-color: var(--el-border-color);
}

/* 推理区文字深色 */
.reasoning-section :deep(.message-content) {
  color: var(--el-text-color-primary) !important;
}

/* 正文区域 */
.normal-section {
  /* 继承白色背景 */
}

.empty-state {
  text-align: center;
  color: var(--el-text-color-placeholder);
  padding: 24px;
  font-size: 14px;
}
</style>
