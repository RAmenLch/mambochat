<!-- frontend/mambo/src/components/chat/dialogs/McpToolDialog.vue -->
<template>
  <el-dialog
    v-model="internalVisible"
    :title="mode === 'review_all' ? t('chat.message.mcp.batchReview') : t('chat.message.toolCall')"
    :width="dialogWidth + 'px'"
    top="3vh"
    destroy-on-close
    class="mcp-tool-dialog"
    :style="{ '--dialog-height': dialogHeight > 0 ? dialogHeight + 'px' : 'auto' }"
    @close="handleClose"
  >
    <el-tabs v-if="toolMessages.length > 0" v-model="activeTabId">
      <el-tab-pane
        v-for="msg in toolMessages"
        :key="msg.id"
        :label="getTabLabel(msg)"
        :name="msg.id"
      >
        <div class="tool-detail-container" v-if="getParsedContent(msg)">
          <div class="tool-header">
            <h3>{{ getParsedContent(msg)?.name }}</h3>
            <p v-if="getToolDescription(msg)" class="tool-desc">
              {{ getToolDescription(msg) }}
            </p>
          </div>

          <div class="tool-arguments">
            <h4>{{ t('chat.message.mcp.arguments') }}</h4>

            <!-- Read-only view for completed McpTool -->
            <div v-if="msg.type === 'McpTool'">
              <div v-if="Object.keys(editForms[msg.id] || {}).length > 0" class="readonly-args-box">
                <div v-for="(val, key) in editForms[msg.id]" :key="key" class="arg-row" :class="{ 'is-multiline': isMultilineValue(val) }">
                  <span class="arg-key">{{ key }}</span>
                  <pre class="arg-val" v-if="isMultilineValue(val)">{{ typeof val === 'object' ? JSON.stringify(val, null, 2) : val }}</pre>
                  <span class="arg-val arg-val-inline" v-else>{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
                </div>
              </div>
              <div v-else class="no-args">{{ t('chat.message.mcp.noArguments') }}</div>
            </div>

            <!-- Editable form for ReviewTool -->
            <el-form v-else label-position="top">
              <template v-for="propName in getCombinedArgKeys(msg)" :key="propName">
                <el-form-item :label="String(propName)" :required="isPropRequired(msg, String(propName))">
                  <!-- 添加 as number 断言 -->
                  <el-input-number
                    v-if="getSchemaProperty(msg, String(propName))?.type === 'integer' || getSchemaProperty(msg, String(propName))?.type === 'number'"
                    v-model="(editForms[msg.id][String(propName)] as number)"
                    controls-position="right"
                    style="width: 100%"
                  />
                  <!-- 添加 as boolean 断言 -->
                  <el-switch
                    v-else-if="getSchemaProperty(msg, String(propName))?.type === 'boolean'"
                    v-model="(editForms[msg.id][String(propName)] as boolean)"
                  />
                  <!-- 添加 as string 断言 -->
                  <el-input
                    v-else
                    v-model="(editForms[msg.id][String(propName)] as string)"
                    type="textarea"
                    autosize
                  />
                  <div class="prop-desc" v-if="getSchemaProperty(msg, String(propName))?.description">
                    {{ getSchemaProperty(msg, String(propName))?.description }}
                  </div>
                </el-form-item>
              </template>
              <div v-if="getCombinedArgKeys(msg).length === 0" class="no-args">
                {{ t('chat.message.mcp.noArguments') }}
              </div>
            </el-form>
          </div>

          <div v-if="msg.type === 'McpTool'" class="tool-result">
            <h4>{{ t('chat.message.mcp.result') }}</h4>
            <div class="result-box" :class="{ 'is-error': (getParsedContent(msg) as McpToolContent).is_error }">
              {{ (getParsedContent(msg) as McpToolContent).result || t('chat.message.mcp.noResult') }}
            </div>
          </div>

          <div v-if="msg.type === 'ReviewTool'" class="tool-actions-wrapper">
            <div v-if="!getToolDecision(msg)" class="tool-actions">
              <el-button type="danger" plain @click="submitDecision(msg.id, 'reject')">
                {{ t('chat.message.mcp.reject') }}
              </el-button>
              <div class="right-actions">
                <el-button type="warning" plain @click="submitDecision(msg.id, 'edit')">
                  {{ t('chat.message.mcp.editAndApprove') }}
                </el-button>
                <el-button type="primary" @click="submitDecision(msg.id, 'approve')">
                  {{ t('chat.message.mcp.approve') }}
                </el-button>
              </div>
            </div>

            <div v-else class="tool-decision-result">
              <h4>{{ t('chat.message.mcp.reviewResult') }}</h4>
              <el-alert
                :type="getToolDecision(msg)?.type === 'approve' ? 'success' : (getToolDecision(msg)?.type === 'reject' ? 'error' : 'warning')"
                :title="getDecisionText(getToolDecision(msg))"
                :description="getToolDecision(msg)?.message || ''"
                :closable="false"
                show-icon
              />
            </div>
          </div>
        </div>
        <div v-else class="parse-error">
          {{ t('chat.message.mcp.parseError') }}
        </div>
      </el-tab-pane>

      <!-- AI 安全审核 Tab（仅 McpTool + 有对应 SecurityReview 时显示） -->
      <el-tab-pane
        v-if="activeSecurityReviewContent"
        :key="'security_review_' + activeSecurityReviewContent.tool_call_id"
        :label="'🛡️ ' + $t('agent.securityReviewPassed')"
        :name="securityReviewTabName"
      >
        <div class="tool-detail-container">
          <div class="tool-header">
            <h3>{{ activeSecurityReviewContent.tool_name }}</h3>
            <el-tag
              :type="activeSecurityReviewContent.passed ? 'success' : 'danger'"
              size="default"
              effect="light"
              class="security-review-status-tag"
            >
              {{ activeSecurityReviewContent.passed ? $t('agent.securityReviewPassed') : $t('agent.securityReviewFailed') }}
            </el-tag>
            <p class="tool-desc">{{ activeSecurityReviewContent.passed ? $t('agent.securityReviewDesc') : $t('agent.securityReviewFailedDesc') }}</p>
          </div>

          <el-descriptions :column="1" border size="default" class="security-review-descriptions">
            <el-descriptions-item :label="$t('agent.securityReviewRiskLevel')">
              <el-tag
                :type="riskLevelTagType"
                size="small"
                effect="plain"
              >
                {{ activeSecurityReviewContent.risk_level.toUpperCase() }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item :label="$t('agent.securityReviewReason')">
              <div class="security-review-reason">{{ activeSecurityReviewContent.reason }}</div>
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-tab-pane>

      <!-- 子代理追踪 Tab（仅 task 工具 + 有步骤时显示） -->
      <el-tab-pane
        v-if="activeTaskSubSteps.length > 0"
        :key="'subagent_' + taskToolCallId"
        :label="'🤖 ' + $t('chat.subagent.tracking')"
        :name="subagentTabName"
      >
        <div class="tool-detail-container">
          <TaskSubAgentPanel
            :steps="activeTaskSubSteps"
            :security-review-map="securityReviewMap"
            :review-tool-map="reviewToolMap"
          />
        </div>
      </el-tab-pane>
    </el-tabs>
    <el-empty v-else :description="t('chat.message.mcp.noToolInfo')" />

    <!-- 拖拽调整大小手柄 -->
    <div class="resize-handle" @mousedown.prevent="startResize">
      <svg viewBox="0 0 16 16" width="12" height="12" class="resize-icon">
        <path d="M0 16 L16 0 M5 16 L16 5 M10 16 L16 10 M15 16 L16 15" stroke="currentColor" stroke-width="1" fill="none" opacity="0.4"/>
      </svg>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useMcpStore } from '@/stores/mcpStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import type { SubMessage, McpToolContent, ReviewToolContent, ToolDecision, SchemaProperty, TaskSubStepContent, Message, SecurityReviewContent } from '@/api/types';
import { ElMessage, ElMessageBox } from 'element-plus';
import TaskSubAgentPanel from '../task/TaskSubAgentPanel.vue';

const { t } = useI18n();
const mcpStore = useMcpStore();
const interactionStore = useChatInteractionStore();
const sessionStore = useChatSessionStore();

const props = defineProps<{
  visible: boolean;
  parentMessageId: string | null;
  initialSubMessageId?: string;
  mode?: 'review_all' | 'single';
  /** 直接传入父消息（用于子代理面板等场景），优先于 parentMessageId 查找 */
  parentMessage?: Message | null;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const internalVisible = ref(false);
const activeTabId = ref('');
const editForms = ref<Record<string, Record<string, unknown>>>({});

// ── 拖拽缩放 ──
const dialogWidth = ref(800);
const dialogHeight = ref(0); // 0 = 自动高度，拖拽后变为固定值
const resizeState = { active: false, startX: 0, startY: 0, startW: 0, startH: 0 };

function startResize(e: MouseEvent) {
  const el = document.querySelector('.mcp-tool-dialog') as HTMLElement;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  resizeState.active = true;
  resizeState.startX = e.clientX;
  resizeState.startY = e.clientY;
  resizeState.startW = rect.width;
  resizeState.startH = rect.height;
  // 首次拖拽时用当前真实高度初始化
  if (dialogHeight.value === 0) dialogHeight.value = rect.height;
  document.addEventListener('mousemove', onResize);
  document.addEventListener('mouseup', stopResize);
  document.body.style.userSelect = 'none';
}

function onResize(e: MouseEvent) {
  if (!resizeState.active) return;
  const dx = e.clientX - resizeState.startX;
  const dy = e.clientY - resizeState.startY;
  dialogWidth.value = Math.max(500, Math.min(window.innerWidth * 0.95, resizeState.startW + dx));
  dialogHeight.value = Math.max(350, Math.min(window.innerHeight * 0.94, resizeState.startH + dy));
}

function stopResize() {
  resizeState.active = false;
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
  document.body.style.userSelect = '';
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onResize);
  document.removeEventListener('mouseup', stopResize);
});

const liveParentMessage = computed(() => {
  if (props.parentMessage) return props.parentMessage;
  if (!props.parentMessageId) return null;
  return sessionStore.currentChatMessages.find(m => m.id === props.parentMessageId) || null;
});

const toolMessages = computed(() => {
  if (!liveParentMessage.value) return [];
  const allTools = liveParentMessage.value.sub_messages.filter(sm => sm.type === 'McpTool' || sm.type === 'ReviewTool');

  if (props.mode === 'review_all') {
    return allTools.filter(sm => {
      if (sm.type !== 'ReviewTool') return false;
      const content = getParsedContent(sm) as ReviewToolContent | null;
      return content && !content.decision;
    });
  } else {
    const initialMsg = allTools.find(sm => sm.id === props.initialSubMessageId);
    if (!initialMsg) return [];

    const initialContent = getParsedContent(initialMsg) as McpToolContent | ReviewToolContent | null;
    const targetToolCallId = initialContent?.tool_call_id;

    if (!targetToolCallId) return [initialMsg];

    return allTools.filter(sm => {
      const content = getParsedContent(sm) as McpToolContent | ReviewToolContent | null;
      return content?.tool_call_id === targetToolCallId;
    });
  }
});

/** 从当前 toolMessages 中找到 task 工具的 tool_call_id */
const taskToolCallId = computed(() => {
  for (const msg of toolMessages.value) {
    const content = getParsedContent(msg) as McpToolContent | null;
    if (content?.name === 'task' && content?.tool_call_id) {
      return content.tool_call_id;
    }
  }
  return null;
});

const subagentTabName = computed(() =>
  taskToolCallId.value ? `__subagent__` : ''
);

/** 当前工具对应 SecurityReview 内容（从 toolMessages 的所有 tool_call_id 推导）*/
const activeSecurityReviewContent = computed(() => {
  if (props.mode === 'review_all') return null;
  for (const msg of toolMessages.value) {
    if (msg.type !== 'McpTool' && msg.type !== 'ReviewTool') continue;
    try {
      let toolCallId: string | undefined;
      if (msg.type === 'McpTool') {
        toolCallId = (getParsedContent(msg) as McpToolContent | null)?.tool_call_id;
      } else {
        toolCallId = (getParsedContent(msg) as ReviewToolContent | null)?.tool_call_id;
      }
      if (toolCallId) {
        const sr = securityReviewMap.value.get(toolCallId);
        if (sr) return sr;
      }
    } catch { /* ignore */ }
  }
  return null;
});

const securityReviewTabName = computed(() =>
  activeSecurityReviewContent.value ? `__security_review__` : ''
);

/** 风险等级对应的 el-tag type */
const riskLevelTagType = computed(() => {
  const level = activeSecurityReviewContent.value?.risk_level;
  switch (level) {
    case 'low': return 'success';
    case 'medium': return 'warning';
    case 'high': return 'danger';
    case 'critical': return 'danger';
    default: return 'info';
  }
});

/** parentMessage 中所有 SecurityReview 子消息的 tool_call_id → content 映射 */
const securityReviewMap = computed(() => {
  const map = new Map<string, SecurityReviewContent>();
  const msg = liveParentMessage.value;
  if (!msg) return map;
  for (const sm of msg.sub_messages) {
    if (sm.type === 'SecurityReview') {
      try {
        const content = JSON.parse(sm.content) as SecurityReviewContent;
        map.set(content.tool_call_id, content);
      } catch { /* ignore */ }
    }
  }
  return map;
});

/** parentMessage 中所有 ReviewTool 子消息的 tool_call_id → content 映射 */
const reviewToolMap = computed(() => {
  const map = new Map<string, ReviewToolContent>();
  const msg = liveParentMessage.value;
  if (!msg) return map;
  for (const sm of msg.sub_messages) {
    if (sm.type === 'ReviewTool') {
      try {
        const content = JSON.parse(sm.content) as ReviewToolContent;
        map.set(content.tool_call_id, content);
      } catch { /* ignore */ }
    }
  }
  return map;
});

/** task 工具对应的子代理追踪步骤 */
const activeTaskSubSteps = computed(() => {
  if (!liveParentMessage.value || !taskToolCallId.value) return [];
  const toolCallId = taskToolCallId.value;
  return liveParentMessage.value.sub_messages.filter(sm =>
    sm.type === 'TaskSubStep' && sm.config?.task_group_id === toolCallId
  ).sort((a, b) => {
    try {
      const ca: TaskSubStepContent = JSON.parse(a.content);
      const cb: TaskSubStepContent = JSON.parse(b.content);
      return ca.step_order - cb.step_order;
    } catch {
      return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
    }
  });
});

watch(() => toolMessages.value, (newVal) => {
  if (internalVisible.value && props.mode === 'review_all') {
    if (newVal.length === 0) {
      handleClose();
    } else if (!newVal.find(m => m.id === activeTabId.value)) {
      activeTabId.value = newVal[0].id;
    }
  }
});

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal && toolMessages.value.length > 0) {
    const targetId = toolMessages.value.find(m => m.id === props.initialSubMessageId) ? props.initialSubMessageId : toolMessages.value[0].id;
    activeTabId.value = targetId || '';
    initForms();
  }
});

function handleClose() {
  emit('update:visible', false);
}

function getParsedContent(msg: SubMessage): McpToolContent | ReviewToolContent | null {
  try {
    return JSON.parse(msg.content);
  } catch {
    return null;
  }
}

function getToolDescription(msg: SubMessage): string {
  const content = getParsedContent(msg);
  if (!content) return '';
  if (msg.type === 'ReviewTool') {
    return (content as ReviewToolContent).description || '';
  }
  return '';
}

function getTabLabel(msg: SubMessage): string {
  const content = getParsedContent(msg);
  const name = content?.name || 'Unknown';
  const prefix = msg.type === 'ReviewTool' ? '⏳' : '🛠️';
  return `${prefix} ${name}`;
}

/**
 * 获取工具的 Input Schema 属性映射。
 * 优先从 submessage.content 中获取，若不存在则回退到 mcpStore 查找。
 */
function getToolSchemaProperties(msg: SubMessage): Record<string, SchemaProperty> {
  const content = getParsedContent(msg);
  if (content && content.input_schema) {
    return content.input_schema;
  }

  // Fallback to store if input_schema is missing in content
  const toolName = content?.name;
  if (!toolName) return {};

  for (const server of mcpStore.activeUserMcpServices) {
    const tool = mcpStore.currentServerTools.find(t => t.name === toolName);
    if (tool && tool.input_schema && typeof tool.input_schema === 'object' && 'properties' in tool.input_schema) {
      return (tool.input_schema.properties as Record<string, SchemaProperty>) || {};
    }
  }
  return {};
}

function getSchemaProperty(msg: SubMessage, propName: string): SchemaProperty | undefined {
  const props = getToolSchemaProperties(msg);
  return props[propName];
}

function getCombinedArgKeys(msg: SubMessage): string[] {
  const keys = new Set<string>(Object.keys(editForms.value[msg.id] || {}));
  const schemaProps = getToolSchemaProperties(msg);
  Object.keys(schemaProps).forEach(k => keys.add(k));
  return Array.from(keys);
}

function isPropRequired(msg: SubMessage, propName: string): boolean {
  const toolName = getParsedContent(msg)?.name;
  if (!toolName) return false;

  // Check local schema first
  const localSchema = getParsedContent(msg)?.input_schema;
  if (localSchema) {
     // Note: The local schema provided in example is just properties map, required array is usually in the root of JSON schema.
     // If the backend sends the full schema structure in input_schema, we should check `required`.
     // But based on example `input_schema: {"a": {...}}`, it seems it sends the properties map directly.
     // We might not have 'required' info here unless backend sends it.
     // Fallback to store logic for 'required' check if possible.
  }

  // Fallback to store
  for (const server of mcpStore.activeUserMcpServices) {
    const tool = mcpStore.currentServerTools.find(t => t.name === toolName);
    if (tool && tool.input_schema && typeof tool.input_schema === 'object' && 'required' in tool.input_schema) {
      const requiredArr = tool.input_schema.required as string[];
      return Array.isArray(requiredArr) && requiredArr.includes(propName);
    }
  }
  return false;
}

/**
 * 根据Schema定义转换数据类型，确保表单模型的数据类型正确。
 */
function convertValueBySchema(value: unknown, schema?: SchemaProperty): unknown {
  if (value === null || value === undefined) return schema?.default ?? value;
  if (!schema || !schema.type) return value;

  switch (schema.type) {
    case 'integer':
    case 'number':
      // 如果是字符串则转换，如果是数字则直接返回
      const num = Number(value);
      return isNaN(num) ? value : num;
    case 'boolean':
      if (typeof value === 'string') {
        return value === 'true';
      }
      return Boolean(value);
    default:
      return value;
  }
}

function initForms() {
  const forms: Record<string, Record<string, unknown>> = {};
  toolMessages.value.forEach(msg => {
    const content = getParsedContent(msg);
    let argsObj: Record<string, unknown> = {};

    if (content) {
      if (msg.type === 'McpTool') {
        const mcpContent = content as McpToolContent;
        if (typeof mcpContent.arguments === 'string') {
          try {
            argsObj = JSON.parse(mcpContent.arguments);
          } catch {
            argsObj = {};
          }
        } else if (typeof mcpContent.arguments === 'object') {
          argsObj = mcpContent.arguments;
        }
      } else if (msg.type === 'ReviewTool') {
        const reviewContent = content as ReviewToolContent;
        argsObj = reviewContent.arguments || {};
      }
    }

    const schemaProps = getToolSchemaProperties(msg);
    const processedArgs: Record<string, unknown> = {};

    // 处理已有的参数值
    for (const key in argsObj) {
      const propSchema = schemaProps[key];
      processedArgs[key] = convertValueBySchema(argsObj[key], propSchema);
    }

    // 初始化Schema中定义但Arguments中缺失的参数（使用默认值）
    for (const key in schemaProps) {
        if (processedArgs[key] === undefined && schemaProps[key].default !== undefined) {
            processedArgs[key] = schemaProps[key].default;
        }
    }

    forms[msg.id] = processedArgs;
  });
  editForms.value = forms;
}

function getToolDecision(msg: SubMessage): ToolDecision | null {
  const content = getParsedContent(msg);
  if (msg.type === 'ReviewTool' && content) {
    return (content as ReviewToolContent).decision || null;
  }
  return null;
}

/**
 * 判断值是否为多行内容（包含换行符的字符串，或复杂对象）
 */
function isMultilineValue(val: unknown): boolean {
  if (typeof val === 'string' && val.includes('\n')) return true;
  if (typeof val === 'object' && val !== null) return true;
  return false;
}

function getDecisionText(decision: ToolDecision | null): string {
  if (!decision) return '';
  switch (decision.type) {
    case 'approve': return t('chat.message.mcp.decisionApprove');
    case 'edit': return t('chat.message.mcp.decisionEdit');
    case 'reject': return t('chat.message.mcp.decisionReject');
    default: return '';
  }
}

async function submitDecision(subMessageId: string, type: 'approve' | 'edit' | 'reject') {
  if (!liveParentMessage.value) return;

  const decision: ToolDecision = { type };

  if (type === 'edit') {
    const msg = toolMessages.value.find(m => m.id === subMessageId);
    const content = msg ? getParsedContent(msg) : null;
    const toolName = content?.name || 'Unknown';

    decision.edited_action = {
      name: toolName,
      args: editForms.value[subMessageId] || {}
    };
  } else if (type === 'reject') {
    try {
      const { value } = await ElMessageBox.prompt(
        t('chat.message.mcp.rejectReasonPrompt'),
        t('chat.message.mcp.reject'),
        {
          confirmButtonText: t('common.action.confirm'),
          cancelButtonText: t('common.action.cancel'),
          inputType: 'textarea',
          inputPlaceholder: t('chat.message.mcp.rejectReasonPlaceholder'),
        }
      );
      // 如果用户输入了理由，则使用用户的输入，否则使用默认文案
      decision.message = value?.trim() ? value.trim() : "User rejected the tool call.";
    } catch {
      // 用户点击了取消，中止提交操作
      return;
    }
  }

  try {
    await interactionStore.submitToolReview(liveParentMessage.value.id, subMessageId, decision);
    ElMessage.success(t('chat.message.mcp.reviewSubmitted'));

    if (props.mode === 'single') {
      handleClose();
    }
  } catch (error) {
    ElMessage.error(t('chat.message.mcp.reviewFailed'));
  }
}
</script>

<style scoped>
/* Dialog sizing via CSS vars — width from el-dialog prop, height from custom property */
:deep(.mcp-tool-dialog) {
  min-width: 500px;
  min-height: 350px;
  max-width: 95vw;
  max-height: 94vh;
  height: var(--dialog-height, auto);
  display: flex;
  flex-direction: column;
}
:deep(.mcp-tool-dialog .el-dialog__body) {
  padding-top: 8px;
  overflow-y: auto;
  flex: 1;
  max-height: calc(94vh - 120px);
}

/* 拖拽手柄 */
.resize-handle {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 22px;
  height: 22px;
  cursor: nwse-resize;
  display: flex;
  align-items: flex-end;
  justify-content: flex-end;
  padding: 0 2px 2px 0;
  z-index: 1;
}
.resize-handle:hover .resize-icon {
  opacity: 0.8;
}

.tool-detail-container {
  padding: 10px;
}
.tool-header h3 {
  margin: 0 0 8px 0;
  font-size: 16px;
}
.tool-desc {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 16px;
}
h4 {
  font-size: 14px;
  margin: 16px 0 8px 0;
  color: var(--el-text-color-primary);
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding-bottom: 4px;
}
.prop-desc {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  line-height: 1.2;
  margin-top: 4px;
}
.no-args {
  font-size: 13px;
  color: var(--el-text-color-placeholder);
  padding: 8px 0;
}
.readonly-args-box {
  background-color: var(--color-background-soft);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 12px;
}
.arg-row {
  margin-bottom: 12px;
  font-size: 13px;
}
.arg-row:last-child {
  margin-bottom: 0;
}
.arg-row.is-multiline {
  margin-bottom: 16px;
}
.arg-key {
  display: block;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 4px;
  text-transform: none;
}
.arg-val {
  display: block;
  color: var(--el-text-color-primary);
  word-break: break-all;
  font-family: monospace;
  font-size: 13px;
}
.arg-val-inline {
  display: inline;
  padding: 2px 6px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
}
.arg-val:not(.arg-val-inline) {
  background: var(--el-fill-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px 10px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  line-height: 1.5;
}
.result-box {
  background-color: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
  line-height: 1.5;
}
.result-box.is-error {
  color: var(--el-color-error);
  background-color: var(--el-color-error-light-9);
}
.tool-actions-wrapper {
  margin-top: 24px;
}
.tool-actions {
  display: flex;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.right-actions {
  display: flex;
  gap: 12px;
}
.tool-decision-result {
  margin-top: 24px;
}
.tool-decision-result h4 {
  margin-bottom: 12px;
}
.parse-error {
  padding: 20px;
  text-align: center;
  color: var(--el-color-error);
}

.security-review-status-tag {
  margin-bottom: 8px;
}

.security-review-descriptions {
  margin-top: 12px;
}

.security-review-reason {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-size: 13px;
}
</style>
