<!-- frontend/mambo/src/components/chat/dialogs/McpToolDialog.vue -->
<template>
  <el-dialog
    v-model="internalVisible"
    :title="t('chat.message.toolCall')"
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
            <el-form label-position="top" :disabled="msg.type === 'McpTool'">
              <template v-for="(propDef, propName) in getToolSchemaProperties(getParsedContent(msg)?.name)" :key="propName">
                <el-form-item :label="String(propName)" :required="isPropRequired(getParsedContent(msg)?.name, String(propName))">
                  <el-input-number
                    v-if="propDef.type === 'integer' || propDef.type === 'number'"
                    v-model="editForms[msg.id][String(propName)]"
                    controls-position="right"
                  />
                  <el-switch
                    v-else-if="propDef.type === 'boolean'"
                    v-model="editForms[msg.id][String(propName)]"
                  />
                  <el-input
                    v-else
                    v-model="editForms[msg.id][String(propName)]"
                    type="textarea"
                    autosize
                  />
                  <div class="prop-desc" v-if="propDef.description">{{ propDef.description }}</div>
                </el-form-item>
              </template>
              <div v-if="Object.keys(getToolSchemaProperties(getParsedContent(msg)?.name)).length === 0" class="no-args">
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

          <div v-if="msg.type === 'ReviewTool'" class="tool-actions">
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
import type { SubMessage, Message, McpToolContent, ReviewToolContent, ToolDecision } from '@/api/types';
import { ElMessage } from 'element-plus';

interface SchemaProperty {
  type: string;
  description?: string;
  [key: string]: unknown;
}

const { t } = useI18n();
const mcpStore = useMcpStore();
const interactionStore = useChatInteractionStore();

const props = defineProps<{
  visible: boolean;
  parentMessage: Message | null;
  initialSubMessageId?: string;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
}>();

const internalVisible = ref(false);
const activeTabId = ref('');
const editForms = ref<Record<string, Record<string, unknown>>>({});

const toolMessages = computed(() => {
  if (!props.parentMessage) return [];
  return props.parentMessage.sub_messages.filter(sm => sm.type === 'McpTool' || sm.type === 'ReviewTool');
});

watch(() => props.visible, (newVal) => {
  internalVisible.value = newVal;
  if (newVal && toolMessages.value.length > 0) {
    activeTabId.value = props.initialSubMessageId || toolMessages.value[0].id;
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
        }
      } else if (msg.type === 'ReviewTool') {
        const reviewContent = content as ReviewToolContent;
        argsObj = reviewContent.arguments || {};
      }
    }

    forms[msg.id] = JSON.parse(JSON.stringify(argsObj));
  });
  editForms.value = forms;
}

function getToolSchemaProperties(toolName?: string): Record<string, SchemaProperty> {
  if (!toolName) return {};
  for (const server of mcpStore.activeUserMcpServices) {
    const tool = mcpStore.currentServerTools.find(t => t.name === toolName);
    if (tool && tool.input_schema && typeof tool.input_schema === 'object' && 'properties' in tool.input_schema) {
      return (tool.input_schema.properties as Record<string, SchemaProperty>) || {};
    }
  }
  return {};
}

function isPropRequired(toolName: string | undefined, propName: string): boolean {
  if (!toolName) return false;
  for (const server of mcpStore.activeUserMcpServices) {
    const tool = mcpStore.currentServerTools.find(t => t.name === toolName);
    if (tool && tool.input_schema && typeof tool.input_schema === 'object' && 'required' in tool.input_schema) {
      const requiredArr = tool.input_schema.required as string[];
      return Array.isArray(requiredArr) && requiredArr.includes(propName);
    }
  }
  return false;
}

async function submitDecision(subMessageId: string, type: 'approve' | 'edit' | 'reject') {
  if (!props.parentMessage) return;

  const decision: ToolDecision = { type };

  if (type === 'edit') {
    decision.edited_action = editForms.value[subMessageId];
  } else if (type === 'reject') {
    decision.message = "User rejected the tool call.";
  }

  try {
    await interactionStore.submitToolReview(props.parentMessage.id, subMessageId, decision);
    ElMessage.success(t('chat.message.reviewSubmitted', '审核已提交'));

    const remainingReviews = toolMessages.value.filter(sm => sm.type === 'ReviewTool' && sm.id !== subMessageId);
    if (remainingReviews.length === 0) {
      handleClose();
    } else {
      activeTabId.value = remainingReviews[0].id;
    }
  } catch (error) {
    ElMessage.error(t('chat.message.reviewFailed', '审核提交失败'));
  }
}
</script>

<style scoped>
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
.tool-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.right-actions {
  display: flex;
  gap: 12px;
}
.parse-error {
  padding: 20px;
  text-align: center;
  color: var(--el-color-error);
}
</style>
