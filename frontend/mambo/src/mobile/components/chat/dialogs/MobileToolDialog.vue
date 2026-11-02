<!-- MobileToolDialog.vue — 移动端工具详情 & 审核弹窗（含参数编辑 + 拒绝原因） -->
<template>
  <Teleport to="body">
    <Transition name="sheet">
      <div v-if="visible" class="tool-overlay" @click="handleClose">
        <div class="tool-sheet" @click.stop>
          <div class="sheet-handle"></div>

          <!-- Header -->
          <div class="tool-header">
            <div class="tool-status-icon">
              <el-icon v-if="isReviewType && !currentDecision" color="var(--el-color-warning)" :size="22"><Warning /></el-icon>
              <el-icon v-else-if="isGenerating" class="is-loading" :size="22"><Loading /></el-icon>
              <el-icon v-else-if="mcpTool?.is_error" color="var(--el-color-danger)" :size="22"><CircleClose /></el-icon>
              <el-icon v-else color="var(--el-color-success)" :size="22"><CircleCheck /></el-icon>
            </div>
            <div class="tool-title-area">
              <span class="tool-name">{{ currentUnpacked.displayName }}</span>
              <span class="tool-desc" v-if="currentDescription">{{ currentDescription }}</span>
            </div>
          </div>

          <!-- Multi-tool tabs -->
          <div class="tool-tabs" v-if="toolMessages.length > 1">
            <button
              v-for="msg in toolMessages"
              :key="msg.id"
              class="tab-btn"
              :class="{ active: activeTabId === msg.id }"
              @click="activeTabId = msg.id"
            >{{ getTabLabel(msg) }}</button>
          </div>

          <div class="tool-body">
            <!-- 子 Agent 追踪步骤 -->
            <div class="tool-section subagent-section" v-if="taskSubSteps.length > 0 || taskSubStepsLoading">
              <button class="subagent-toggle" @click="subagentExpanded = !subagentExpanded">
                <el-icon :size="14">
                  <ArrowDown v-if="subagentExpanded" />
                  <ArrowRight v-else />
                </el-icon>
                <span class="subagent-title">🤖 {{ t('chat.subagent.tracking') }}</span>
                <span class="subagent-count">{{ t('chat.subagent.steps', { count: taskSubSteps.length }) }}</span>
                <span v-if="taskDurationText" class="subagent-count">{{ t('chat.subagent.elapsed', { duration: taskDurationText }) }}</span>
              </button>
              <MobileTaskSubAgentPanel
                v-if="subagentExpanded"
                :steps="taskSubSteps"
                :security-review-map="securityReviewMap"
                :review-tool-map="reviewToolMap"
              />
            </div>
            <!-- Editable Args (ReviewTool only) -->
            <div class="tool-section" v-if="isReviewType">
              <div class="section-label">{{ t('chat.message.mcp.arguments') }}{{ hasSchema ? t('chat.message.mcp.argEditable') : '' }}</div>
              <div v-if="hasSchema" class="args-form">
                <div v-for="(prop, key) in schemaProperties" :key="key" class="arg-field">
                  <label class="arg-label">{{ key }}</label>
                  <textarea
                    v-if="isMultilineSchema(prop)"
                    v-model="editForms[key]"
                    rows="2"
                    class="arg-input textarea"
                  ></textarea>
                  <input
                    v-else-if="prop?.type === 'number' || prop?.type === 'integer'"
                    v-model.number="editForms[key]"
                    type="number"
                    class="arg-input"
                  />
                  <label v-else-if="prop?.type === 'boolean'" class="arg-toggle">
                    <input type="checkbox" v-model="editForms[key]" />
                    <span class="toggle-track"></span>
                  </label>
                  <input
                    v-else
                    v-model="editForms[key]"
                    type="text"
                    class="arg-input"
                  />
                  <span class="arg-desc" v-if="prop?.description">{{ prop.description }}</span>
                </div>
              </div>
              <div v-else class="args-list">
                <div v-for="(val, key) in currentArgs" :key="key" class="arg-row">
                  <span class="arg-key">{{ key }}</span>
                  <textarea
                    v-model="editForms[key]"
                    rows="2"
                    class="arg-input textarea"
                  ></textarea>
                </div>
                <div v-if="!currentArgs || Object.keys(currentArgs).length === 0" class="empty-hint">{{ t('chat.message.mcp.noArguments') }}</div>
              </div>
            </div>

            <!-- Read-only Args (McpTool only) -->
            <div class="tool-section" v-if="!isReviewType">
              <div class="section-label">{{ t('chat.message.mcp.arguments') }}</div>
              <div v-if="currentArgs && Object.keys(currentArgs).length > 0" class="args-list">
                <div v-for="(val, key) in currentArgs" :key="key" class="arg-row">
                  <span class="arg-key">{{ key }}</span>
                  <pre
                    v-if="isMultiline(val)"
                    class="arg-val"
                    :class="{ 'is-expanded': expandedArgs[key] }"
                  >{{ formatArg(val) }}</pre>
                  <span v-else class="arg-val inline">{{ formatArg(val) }}</span>
                  <button
                    v-if="isMultiline(val) && isLongText(formatArg(val))"
                    class="expand-toggle"
                    @click="expandedArgs[key] = !expandedArgs[key]"
                  >
                    <el-icon :size="12">
                      <ArrowUp v-if="expandedArgs[key]" />
                      <ArrowDown v-else />
                    </el-icon>
                    <span v-if="expandedArgs[key]">{{ t('chat.message.mcp.collapseContent') }}</span>
                    <span v-else>{{ t('chat.message.mcp.expandFullContent', { count: formatArg(val).length }) }}</span>
                  </button>
                </div>
              </div>
              <div v-else class="empty-hint">{{ t('chat.message.mcp.noArguments') }}</div>
            </div>

            <!-- Result (McpTool only) -->
            <div v-if="activeMsg?.type === 'McpTool'" class="tool-section">
              <div class="section-label">{{ t('chat.message.mcp.result') }}</div>
              <template v-if="mcpTool?.media?.length">
                <div v-for="m in mcpTool.media" :key="m.file_id" class="mcp-tool-media">
                  <img v-if="m.file_type === 'image'" :src="mcpMediaUrl(m)" alt="" class="mcp-tool-media-img" />
                  <audio v-else-if="m.file_type === 'audio'" :src="mcpMediaUrl(m)" controls preload="metadata" class="mcp-tool-media-audio"></audio>
                  <video v-else-if="m.file_type === 'video'" :src="mcpMediaUrl(m)" controls preload="metadata" class="mcp-tool-media-video"></video>
                  <a v-else-if="m.file_type === 'file'" :href="mcpMediaUrl(m)" target="_blank" rel="noopener" class="mcp-tool-media-file">
                    {{ m.filename || m.file_type }}
                  </a>
                </div>
              </template>
              <div class="result-box" :class="{ 'is-error': mcpTool?.is_error, 'is-expanded': isResultExpanded }">
                {{ mcpTool?.result || t('chat.message.mcp.noResult') }}
              </div>
              <button
                v-if="isResultLong"
                class="expand-toggle"
                @click="isResultExpanded = !isResultExpanded"
              >
                <el-icon :size="12">
                  <ArrowUp v-if="isResultExpanded" />
                  <ArrowDown v-else />
                </el-icon>
                <span v-if="isResultExpanded">{{ t('chat.message.mcp.collapseContent') }}</span>
                <span v-else>{{ t('chat.message.mcp.expandFullContent', { count: mcpTool?.result?.length ?? 0 }) }}</span>
              </button>
            </div>

            <!-- Security Review -->
            <div v-if="securityReview" class="tool-section security-section" :class="{ 'is-failed': !securityReview.passed }">
              <div class="section-label">🛡️ {{ t('chat.message.mcp.securityReview') }}</div>
              <div class="security-info">
                <span class="security-level">{{ t('chat.message.mcp.riskLevel') }}: {{ securityReview.risk_level }}</span>
                <span class="security-reason">{{ securityReview.reason }}</span>
              </div>
            </div>

            <!-- Reject Reason -->
            <div v-if="showRejectInput" class="tool-section">
              <div class="section-label">{{ t('chat.message.mcp.rejectReason') }}</div>
              <textarea
                v-model="rejectReason"
                rows="3"
                :placeholder="t('chat.message.mcp.rejectReasonPrompt')"
                class="reject-textarea"
              ></textarea>
              <div class="reject-actions">
                <button class="mini-btn cancel" @click="showRejectInput = false">{{ t('common.action.cancel') }}</button>
                <button class="mini-btn confirm" @click="confirmReject">{{ t('chat.message.mcp.confirmReject') }}</button>
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="tool-actions" v-if="isReviewType && !currentDecision && !showRejectInput">
            <button class="action-btn reject" @click="showRejectInput = true">
              <el-icon :size="18"><Close /></el-icon>
              <span>{{ t('chat.message.mcp.reject') }}</span>
            </button>
            <button class="action-btn edit" @click="handleEditAndApprove">
              <el-icon :size="18"><Edit /></el-icon>
              <span>{{ t('chat.message.mcp.editAndApprove') }}</span>
            </button>
            <button class="action-btn approve" @click="handleApprove">
              <el-icon :size="18"><Select /></el-icon>
              <span>{{ t('chat.message.mcp.approve') }}</span>
            </button>
          </div>

          <button class="sheet-cancel" @click="handleClose">{{ t('common.action.close') }}</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Message, SubMessage, McpToolContent, ReviewToolContent, SecurityReviewContent, ToolDecision, MultimodalMedia } from '@/api/types'
import { useChatInteractionStore } from '@/stores/chatInteractionStore'
import { useChatSessionStore } from '@/stores/chatSessionStore'
import { useMcpStore } from '@/stores/mcpStore'
import { useTaskSubSteps, useTaskDuration, collectSecurityReviewMap, collectReviewToolMap } from '@/composables/useTaskSubSteps'
import { unpackMcpToolCall } from '@/utils/mcpToolUnpack'
import { resolveFileUrl } from '@/services/electronUrl'
import { ElMessage } from 'element-plus'
import { Warning, Loading, CircleClose, CircleCheck, Close, Edit, Select, ArrowUp, ArrowDown, ArrowRight } from '@element-plus/icons-vue'
import MobileTaskSubAgentPanel from '../task/MobileTaskSubAgentPanel.vue'

interface SchemaProperty {
  type?: string
  description?: string
  default?: unknown
  [key: string]: unknown
}

const props = defineProps<{
  visible: boolean
  parentMessageId: string | null
  /** 直接传入父消息（子代理面板等虚拟消息场景），优先于 parentMessageId */
  parentMessage?: Message | null
  initialSubMessageId?: string
  mode: 'review_all' | 'single'
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const interactionStore = useChatInteractionStore()
const sessionStore = useChatSessionStore()
const mcpStore = useMcpStore()

const activeTabId = ref<string>('')
const showRejectInput = ref(false)
const rejectReason = ref('')
const editForms = reactive<Record<string, any>>({})

const { t } = useI18n()

// --- 长参数 / 长结果的折叠与展开 ---
/** 超过该字符数或行数即视为长文本，默认限高展示 */
const LONG_TEXT_MAX_CHARS = 300
const LONG_TEXT_MAX_LINES = 8

const expandedArgs = reactive<Record<string, boolean>>({})
const isResultExpanded = ref(false)

function isLongText(text: string): boolean {
  return text.length > LONG_TEXT_MAX_CHARS || text.split('\n').length > LONG_TEXT_MAX_LINES
}

const parentMessage = computed<Message | null>(() => {
  if (props.parentMessage) return props.parentMessage
  if (!props.parentMessageId) return null
  return sessionStore.currentChatMessages.find((m: Message) => m.id === props.parentMessageId) || null
})

const toolMessages = computed<SubMessage[]>(() => {
  if (!parentMessage.value) return []
  const msg = parentMessage.value
  if (props.mode === 'review_all') {
    return msg.sub_messages.filter(sm => sm.type === 'McpTool' || sm.type === 'ReviewTool')
  }
  if (props.initialSubMessageId) {
    const target = msg.sub_messages.find(sm => sm.id === props.initialSubMessageId)
    return target ? [target] : []
  }
  return []
})

const activeMsg = computed(() => toolMessages.value.find(m => m.id === activeTabId.value) || toolMessages.value[0])

const currentTool = computed((): McpToolContent | ReviewToolContent | null => {
  if (!activeMsg.value) return null
  try { return JSON.parse(activeMsg.value.content) } catch { return null }
})

const currentUnpacked = computed(() => {
  if (!currentTool.value) return { displayName: 'Tool', effectiveName: 'Tool', isMcpWrapped: false, isTailTool: false, isWrapped: false, effectiveArgs: {} as Record<string, unknown>, serverName: undefined as string | undefined }
  return unpackMcpToolCall(currentTool.value)
})

const mcpTool = computed((): McpToolContent | null => {
  if (activeMsg.value?.type !== 'McpTool') return null
  return currentTool.value as McpToolContent
})

const isResultLong = computed(() => isLongText(mcpTool.value?.result || ''))

// --- 子 Agent（task 工具）追踪步骤 ---
/** 当前工具为 task 时的 tool_call_id（兼容拆包后的内层工具名） */
const taskToolCallId = computed<string | null>(() => {
  const content = mcpTool.value
  if (!content) return null
  if (content.name === 'task' || currentUnpacked.value.effectiveName === 'task') {
    return content.tool_call_id || null
  }
  return null
})

const { steps: taskSubSteps, isLoading: taskSubStepsLoading } = useTaskSubSteps(
  parentMessage,
  taskToolCallId,
  computed(() => props.visible),
)

const { durationText: taskDurationText } = useTaskDuration(
  taskSubSteps,
  computed(() => activeMsg.value?.status === 'generating'),
)

const securityReviewMap = computed(() => collectSecurityReviewMap(parentMessage.value))
const reviewToolMap = computed(() => collectReviewToolMap(parentMessage.value))

const subagentExpanded = ref(true)

/** 多模态媒体展示 url（后端已在 media.url 填充下载路径） */
function mcpMediaUrl(m: MultimodalMedia | null | undefined): string {
  if (!m?.url) return ''
  return resolveFileUrl(m.url) || ''
}

const currentArgs = computed(() => {
  if (!currentTool.value) return null
  const unpacked = currentUnpacked.value
  if (unpacked.isWrapped) {
    return unpacked.effectiveArgs as Record<string, unknown>
  }
  const args = (currentTool.value as any).arguments
  if (typeof args === 'string') {
    try { return JSON.parse(args) } catch { return { input: args } }
  }
  return args || {}
})

const schemaProperties = computed<Record<string, SchemaProperty>>(() => {
  const tool = currentTool.value as any
  // 1) Content 中直接有 input_schema（已打平的 map）
  if (tool?.input_schema && typeof tool.input_schema === 'object' && !Array.isArray(tool.input_schema)) {
    const firstVal = Object.values(tool.input_schema)[0]
    if (firstVal && typeof firstVal === 'object' && 'type' in firstVal) {
      return tool.input_schema as Record<string, SchemaProperty>
    }
  }
  // 2) Content 中 input_schema 是标准 JSON Schema（有 properties 字段）
  if (tool?.input_schema?.properties) {
    return tool.input_schema.properties as Record<string, SchemaProperty>
  }
  // 3) 回退到 mcpStore 查找
  const toolName = tool?.name
  if (toolName) {
    const serverTool = mcpStore.currentServerTools?.find((t: any) => t.name === toolName)
    if (serverTool?.input_schema?.properties) {
      return serverTool.input_schema.properties as Record<string, SchemaProperty>
    }
  }
  return {}
})

const hasSchema = computed(() => Object.keys(schemaProperties.value).length > 0)

const currentDescription = computed(() => {
  if (!activeMsg.value || activeMsg.value.type !== 'ReviewTool') return ''
  return (currentTool.value as ReviewToolContent)?.description || ''
})

const currentDecision = computed(() => {
  if (!activeMsg.value || activeMsg.value.type !== 'ReviewTool') return null
  return (currentTool.value as ReviewToolContent)?.decision || null
})

const isReviewType = computed(() => activeMsg.value?.type === 'ReviewTool')
const isGenerating = computed(() => activeMsg.value?.status === 'generating')

const securityReview = computed((): SecurityReviewContent | null => {
  if (!parentMessage.value || !activeMsg.value) return null
  const toolCallId = (currentTool.value as McpToolContent)?.tool_call_id
  if (!toolCallId) return null
  for (const sm of parentMessage.value.sub_messages) {
    if (sm.type === 'SecurityReview') {
      try {
        const content = JSON.parse(sm.content) as SecurityReviewContent
        if (content.tool_call_id === toolCallId) return content
      } catch { /* ignore */ }
    }
  }
  return null
})

watch(() => props.visible, (v) => {
  if (v && toolMessages.value.length > 0) {
    activeTabId.value = props.initialSubMessageId || toolMessages.value[0].id
    showRejectInput.value = false
    rejectReason.value = ''
    resetExpandedState()
    initEditForms()
  }
})

watch(activeTabId, () => {
  showRejectInput.value = false
  rejectReason.value = ''
  resetExpandedState()
  initEditForms()
})

function resetExpandedState() {
  for (const key of Object.keys(expandedArgs)) delete expandedArgs[key]
  isResultExpanded.value = false
}

function initEditForms() {
  const args = currentArgs.value
  for (const key of Object.keys(editForms)) delete editForms[key]
  if (!args) return
  if (hasSchema.value) {
    const schema = schemaProperties.value
    for (const key in schema) {
      editForms[key] = args[key] ?? schema[key]?.default ?? ''
    }
  }
  // Always include raw args as editable values
  for (const key in args) {
    if (!(key in editForms)) {
      editForms[key] = typeof args[key] === 'object' ? JSON.stringify(args[key], null, 2) : String(args[key] ?? '')
    }
  }
}

function getTabLabel(msg: SubMessage): string {
  try {
    const c = JSON.parse(msg.content)
    const unpacked = unpackMcpToolCall(c)
    return unpacked.displayName
  } catch { return 'Tool' }
}

function isMultiline(val: any): boolean {
  if (typeof val === 'string') return val.length > 60 || val.includes('\n')
  return typeof val === 'object'
}

function isMultilineSchema(prop: SchemaProperty): boolean {
  if (!prop) return false
  return prop.type === 'string' && (!prop.description || prop.description.length > 0)
}

function formatArg(val: any): string {
  if (typeof val === 'object') return JSON.stringify(val, null, 2)
  return String(val)
}

function handleClose() {
  emit('update:visible', false)
}

async function handleApprove() {
  if (!activeMsg.value || !props.parentMessageId) return
  try {
    await interactionStore.submitToolReview(props.parentMessageId, activeMsg.value.id, { type: 'approve' })
    ElMessage.success(t('chat.message.mcp.decisionApprove'))
    handleClose()
  } catch { ElMessage.error(t('common.error.operationFailed')) }
}

async function confirmReject() {
  if (!activeMsg.value || !props.parentMessageId) return
  const decision: ToolDecision = {
    type: 'reject',
    message: rejectReason.value.trim() || '用户拒绝了该工具调用。',
  }
  try {
    await interactionStore.submitToolReview(props.parentMessageId, activeMsg.value.id, decision)
    ElMessage.success(t('chat.message.mcp.decisionReject'))
    handleClose()
  } catch { ElMessage.error(t('common.error.operationFailed')) }
}

async function handleEditAndApprove() {
  if (!activeMsg.value || !props.parentMessageId) return
  const toolName = currentUnpacked.value.effectiveName
  const editedArgs: Record<string, unknown> = {}
  for (const key of Object.keys(editForms)) {
    const raw = editForms[key]
    if (hasSchema.value) {
      editedArgs[key] = raw
    } else {
      // No schema: try to parse back to original type
      try { editedArgs[key] = JSON.parse(raw) } catch { editedArgs[key] = raw }
    }
  }
  const decision: ToolDecision = {
    type: 'edit',
    edited_action: { name: toolName, args: editedArgs },
  }
  try {
    await interactionStore.submitToolReview(props.parentMessageId, activeMsg.value.id, decision)
    ElMessage.success(t('chat.message.mcp.decisionEdit'))
    handleClose()
  } catch { ElMessage.error(t('common.error.operationFailed')) }
}
</script>

<style scoped>
.tool-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  z-index: 2000;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.tool-sheet {
  width: 100%;
  max-width: 500px;
  max-height: 85vh;
  background: var(--color-background);
  border-radius: 16px 16px 0 0;
  padding: 8px 16px;
  padding-bottom: max(16px, env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sheet-handle {
  width: 36px;
  height: 4px;
  background: var(--el-border-color);
  border-radius: 2px;
  margin: 8px auto 12px;
  flex-shrink: 0;
}

.tool-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 4px 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.tool-status-icon { flex-shrink: 0; margin-top: 2px; }

.tool-title-area { flex: 1; min-width: 0; }

.tool-name { font-size: 17px; font-weight: 600; display: block; }

.tool-desc { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; line-height: 1.4; }

.tool-tabs {
  display: flex; gap: 4px; padding: 10px 0;
  overflow-x: auto; flex-shrink: 0; -webkit-overflow-scrolling: touch;
}

.tab-btn {
  padding: 6px 14px; border-radius: 16px;
  border: 1px solid var(--el-border-color-light); background: transparent;
  font-size: 13px; color: var(--el-text-color-secondary);
  white-space: nowrap; cursor: pointer; font-family: inherit; transition: all 0.15s; flex-shrink: 0;
}

.tab-btn.active { background: var(--el-color-primary); border-color: var(--el-color-primary); color: #fff; }

.tool-body { flex: 1; overflow-y: auto; padding: 4px 0; }

.tool-section { margin-bottom: 14px; }

.section-label {
  font-size: 12px; font-weight: 600; color: var(--el-text-color-secondary);
  text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;
}

/* 子 Agent 追踪步骤 */
.subagent-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--el-fill-color-blank);
}

.subagent-toggle {
  display: flex; align-items: center; gap: 6px; width: 100%;
  padding: 0; border: none; background: transparent;
  font-size: 13px; color: var(--el-text-color-regular); text-align: left;
}

.subagent-title { flex: 1; min-width: 0; }

.subagent-count {
  font-size: 11px; color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light); border-radius: 4px; padding: 1px 6px;
}

/* Editable form */
.args-form { display: flex; flex-direction: column; gap: 10px; }

.arg-field { display: flex; flex-direction: column; gap: 4px; }

.arg-label {
  font-size: 12px; font-weight: 600; color: var(--el-color-primary);
}

.arg-input {
  padding: 10px 12px; border: 1px solid var(--el-border-color); border-radius: 8px;
  font-size: 14px; font-family: inherit; outline: none;
  background: var(--el-fill-color-light); color: var(--el-text-color-primary);
}

.arg-input:focus { border-color: var(--el-color-primary); }

.arg-input.textarea { resize: vertical; font-family: 'SF Mono', Monaco, Menlo, monospace; font-size: 13px; }

.arg-toggle {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
}

.arg-toggle input { display: none; }

.arg-toggle .toggle-track {
  width: 44px; height: 24px; border-radius: 12px;
  background: var(--el-border-color); position: relative; transition: background 0.2s;
}

.arg-toggle .toggle-track::after {
  content: ''; position: absolute; top: 2px; left: 2px;
  width: 20px; height: 20px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.15); transition: transform 0.2s;
}

.arg-toggle input:checked + .toggle-track { background: var(--el-color-primary); }

.arg-toggle input:checked + .toggle-track::after { transform: translateX(20px); }

.arg-desc {
  font-size: 11px; color: var(--el-text-color-placeholder); line-height: 1.3;
}

/* Readonly args */
.args-list { display: flex; flex-direction: column; gap: 6px; }

.arg-row { padding: 8px 12px; background: var(--el-fill-color-light); border-radius: 8px; }

.arg-key { font-size: 11px; font-weight: 600; color: var(--el-color-primary); display: block; margin-bottom: 2px; }

.arg-val {
  font-size: 13px; color: var(--el-text-color-primary); margin: 0;
  white-space: pre-wrap; word-break: break-word;
  font-family: 'SF Mono', Monaco, Menlo, monospace; background: transparent;
  max-height: 160px; overflow-y: auto;
}

.arg-val.is-expanded { max-height: none; }

.arg-val.inline { font-family: inherit; max-height: none; overflow: visible; }

.expand-toggle {
  display: inline-flex; align-items: center; gap: 2px;
  margin-top: 6px; padding: 4px 8px;
  font-size: 12px; color: var(--el-color-primary);
  background: transparent; border: none; cursor: pointer;
}

.result-box {
  padding: 10px 12px; background: var(--el-fill-color-light); border-radius: 8px;
  font-size: 13px; max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
}

.result-box.is-expanded { max-height: none; }

.result-box.is-error {
  background: var(--el-color-danger-light-9); color: var(--el-color-danger);
  border: 1px solid var(--el-color-danger-light-5);
}
.mcp-tool-media { margin-top: 8px; }
.mcp-tool-media-img { display: block; max-width: 100%; max-height: 260px; border-radius: 8px; }
.mcp-tool-media-audio,
.mcp-tool-media-video { display: block; width: 100%; max-width: 400px; margin-top: 4px; }
.mcp-tool-media-file { color: var(--el-color-primary); text-decoration: underline; }

.security-section { border-radius: 8px; padding: 10px 12px; background: var(--el-color-success-light-9); }

.security-section.is-failed { background: var(--el-color-danger-light-9); }

.security-info { display: flex; flex-direction: column; gap: 4px; font-size: 13px; }

.security-level { font-weight: 600; }

.security-reason { color: var(--el-text-color-secondary); }

.empty-hint { font-size: 13px; color: var(--el-text-color-placeholder); font-style: italic; padding: 6px 0; }

/* Reject reason */
.reject-textarea {
  width: 100%; padding: 10px 12px; border: 1px solid var(--el-border-color); border-radius: 8px;
  font-size: 14px; font-family: inherit; resize: vertical; outline: none;
  box-sizing: border-box;
}

.reject-textarea:focus { border-color: var(--el-color-danger); }

.reject-actions { display: flex; gap: 8px; margin-top: 8px; }

.mini-btn {
  flex: 1; padding: 10px; border-radius: 8px; border: none; font-size: 14px;
  font-weight: 600; cursor: pointer; font-family: inherit;
}

.mini-btn.cancel { background: var(--el-fill-color-light); color: var(--el-text-color-secondary); }

.mini-btn.confirm { background: var(--el-color-danger); color: #fff; }

/* Action buttons */
.tool-actions {
  display: flex; gap: 10px; padding: 12px 0 8px;
  border-top: 1px solid var(--el-border-color-lighter); flex-shrink: 0;
}

.action-btn {
  flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px;
  padding: 12px 8px; border-radius: 12px; border: none;
  font-size: 14px; font-weight: 600; cursor: pointer; font-family: inherit; transition: all 0.15s;
}

.action-btn.reject { background: var(--el-color-danger-light-9); color: var(--el-color-danger); }

.action-btn.edit { background: var(--el-color-warning-light-9); color: var(--el-color-warning-dark-2); }

.action-btn.approve { background: var(--el-color-success-light-9); color: var(--el-color-success); }

.action-btn:active { transform: scale(0.96); }

.sheet-cancel {
  width: 100%; padding: 14px; margin-top: 4px; border: none; border-radius: 10px;
  background: var(--el-fill-color-light); font-size: 16px; font-weight: 600;
  color: var(--el-text-color-secondary); cursor: pointer; font-family: inherit; flex-shrink: 0;
}

.sheet-cancel:active { background: var(--el-fill-color); }

.is-loading { animation: rotating 2s linear infinite; }

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.sheet-enter-active { transition: all 0.25s ease-out; }
.sheet-leave-active { transition: all 0.2s ease-in; }
.sheet-enter-from .tool-sheet,
.sheet-leave-to .tool-sheet { transform: translateY(100%); }
.sheet-enter-from { opacity: 0; }
.sheet-leave-to { opacity: 0; }
</style>
