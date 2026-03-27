<!-- frontend/mambo/src/components/chat/dialogs/McpToolDialog.vue -->
<template>
  <el-dialog
    v-model="internalVisible"
    :title="mode === 'review_all' ? t('chat.message.batchReview', '批量审核工具') : t('chat.message.toolCall', '工具调用')"
    width="600px"
    destroy-on-close
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
            <h4>{{ t('chat.message.arguments', '参数') }}</h4>

            <!-- Read-only view for completed McpTool -->
            <div v-if="msg.type === 'McpTool'">
              <div v-if="Object.keys(editForms[msg.id] || {}).length > 0" class="readonly-args-box">
                <div v-for="(val, key) in editForms[msg.id]" :key="key" class="arg-row">
                  <span class="arg-key">{{ key }}:</span>
                  <span class="arg-val">{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
                </div>
              </div>
              <div v-else class="no-args">{{ t('chat.message.noArguments', '无参数配置') }}</div>
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
                {{ t('chat.message.noArguments', '无参数配置') }}
              </div>
            </el-form>
          </div>

          <div v-if="msg.type === 'McpTool'" class="tool-result">
            <h4>{{ t('chat.message.result', '返回结果') }}</h4>
            <div class="result-box" :class="{ 'is-error': (getParsedContent(msg) as McpToolContent).is_error }">
              {{ (getParsedContent(msg) as McpToolContent).result || t('chat.message.noResult', '无返回结果') }}
            </div>
          </div>

          <div v-if="msg.type === 'ReviewTool'" class="tool-actions-wrapper">
            <div v-if="!getToolDecision(msg)" class="tool-actions">
              <el-button type="danger" plain @click="submitDecision(msg.id, 'reject')">
                {{ t('chat.message.reject', '拒绝调用') }}
              </el-button>
              <div class="right-actions">
                <el-button type="warning" plain @click="submitDecision(msg.id, 'edit')">
                  {{ t('chat.message.editAndApprove', '修改并同意') }}
                </el-button>
                <el-button type="primary" @click="submitDecision(msg.id, 'approve')">
                  {{ t('chat.message.approve', '同意调用') }}
                </el-button>
              </div>
            </div>

            <div v-else class="tool-decision-result">
              <h4>{{ t('chat.message.reviewResult', '审核结果') }}</h4>
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
          {{ t('chat.message.parseError', '解析失败') }}
        </div>
      </el-tab-pane>
    </el-tabs>
    <el-empty v-else :description="t('chat.message.noToolInfo', '无工具调用信息')" />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useMcpStore } from '@/stores/mcpStore';
import { useChatInteractionStore } from '@/stores/chatInteractionStore';
import { useChatSessionStore } from '@/stores/chatSessionStore';
import type { SubMessage, McpToolContent, ReviewToolContent, ToolDecision, SchemaProperty } from '@/api/types';
import { ElMessage, ElMessageBox } from 'element-plus';

const { t } = useI18n();
const mcpStore = useMcpStore();
const interactionStore = useChatInteractionStore();
const sessionStore = useChatSessionStore();

const props = defineProps<{
  visible: boolean;
  parentMessageId: string | null;
  initialSubMessageId?: string;
  mode?: 'review_all' | 'single';
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const internalVisible = ref(false);
const activeTabId = ref('');
const editForms = ref<Record<string, Record<string, unknown>>>({});

const liveParentMessage = computed(() => {
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

function getDecisionText(decision: ToolDecision | null): string {
  if (!decision) return '';
  switch (decision.type) {
    case 'approve': return t('chat.message.decisionApprove', '已同意调用');
    case 'edit': return t('chat.message.decisionEdit', '已修改并同意');
    case 'reject': return t('chat.message.decisionReject', '已拒绝调用');
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
        t('chat.message.rejectReasonPrompt', '请输入拒绝理由（可选）：'),
        t('chat.message.reject', '拒绝调用'),
        {
          confirmButtonText: t('common.action.confirm', '确定'),
          cancelButtonText: t('common.action.cancel', '取消'),
          inputType: 'textarea',
          inputPlaceholder: t('chat.message.rejectReasonPlaceholder', '若不提供，将使用默认理由...'),
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
    ElMessage.success(t('chat.message.reviewSubmitted', '审核已提交'));

    if (props.mode === 'single') {
      handleClose();
    }
  } catch (error) {
    ElMessage.error(t('chat.message.reviewFailed', '审核提交失败'));
  }
}
</script>

<style scoped>
/* ... existing styles ... */
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
  display: flex;
  margin-bottom: 8px;
  font-size: 13px;
}
.arg-row:last-child {
  margin-bottom: 0;
}
.arg-key {
  font-weight: 600;
  color: var(--el-text-color-regular);
  width: 120px;
  flex-shrink: 0;
}
.arg-val {
  color: var(--el-text-color-primary);
  word-break: break-all;
  font-family: monospace;
}
.result-box {
  background-color: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
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
</style>
