<!-- frontend/mambo/src/components/chat/message/TailToolPanel.vue -->
<!--
  尾部工具汇总面板（config.is_tail_tool）：这类子消息不参与正文 / 时间线渲染，
  仅在助手消息底部以可折叠的小面板展示工具调用结果。
  content 形如： {"status":"ok"|"error", "calls":[{"task","arguments","tool_call_id","status","output","error"}], "error":null}
-->
<template>
  <div
    v-if="calls.length > 0 || topError"
    class="tail-tool-panel"
    :class="{ 'is-error': hasError }"
  >
    <!-- 头部：点击展开 / 折叠 -->
    <div class="tail-tool-header" @click="isExpanded = !isExpanded">
      <el-icon class="tail-tool-arrow">
        <ArrowRight v-if="!isExpanded" />
        <ArrowDown v-else />
      </el-icon>
      <span class="tail-tool-title">{{ t('chat.message.tailToolPanel.title') }}</span>
      <span v-if="calls.length > 0" class="tail-tool-count">
        · {{ t('chat.message.tailToolPanel.taskCount', { n: calls.length }) }}
      </span>
    </div>

    <!-- 内容区：默认折叠 -->
    <div v-show="isExpanded" class="tail-tool-body">
      <!-- 顶层错误 -->
      <div v-if="topError" class="tail-tool-call is-error">
        <div class="tail-tool-row">
          <span class="tail-tool-label is-error">{{ t('chat.message.tailToolPanel.error') }}</span>
          <pre class="tail-tool-text is-error">{{ topError }}</pre>
        </div>
      </div>

      <!-- 单个工具调用 -->
      <div
        v-for="(call, index) in calls"
        :key="call.tool_call_id || index"
        class="tail-tool-call"
        :class="{ 'is-error': isErrorCall(call) }"
      >
        <div class="tail-tool-call-head">
          <span class="tail-tool-task">{{ call.task || '-' }}</span>
          <span class="tail-tool-status" :class="{ 'is-error': isErrorCall(call) }">
            {{ t('chat.message.tailToolPanel.status') }}: {{ call.status || '-' }}
          </span>
        </div>
        <div class="tail-tool-row" v-if="hasArgs(call)">
          <span class="tail-tool-label">{{ t('chat.message.tailToolPanel.arguments') }}</span>
          <pre class="tail-tool-text">{{ formatArgs(call.arguments) }}</pre>
        </div>
        <div class="tail-tool-row" v-if="call.output">
          <span class="tail-tool-label">{{ t('chat.message.tailToolPanel.output') }}</span>
          <pre class="tail-tool-text">{{ call.output }}</pre>
        </div>
        <div class="tail-tool-row" v-if="call.error">
          <span class="tail-tool-label is-error">{{ t('chat.message.tailToolPanel.error') }}</span>
          <pre class="tail-tool-text is-error">{{ call.error }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SubMessage } from '@/api/types'
import { ArrowRight, ArrowDown } from '@element-plus/icons-vue'

/** 单条尾部工具调用（后端 SubMessage.content JSON 结构） */
interface TailToolCall {
  task?: string
  arguments?: Record<string, unknown>
  tool_call_id?: string
  status?: string
  output?: string | null
  error?: string | null
}

/** 尾部工具子消息 content 的 JSON 结构 */
interface TailToolContent {
  status?: string
  calls?: TailToolCall[]
  error?: string | null
}

const props = defineProps<{
  /** 携带 config.is_tail_tool === true 的子消息（可能多条） */
  subMessages: SubMessage[]
}>()

const { t } = useI18n()
const isExpanded = ref(false)

/** 安全解析所有尾部工具子消息，非法 / 残缺 JSON 直接忽略 */
const parsed = computed(() => {
  const calls: TailToolCall[] = []
  const errors: string[] = []
  let hasError = false

  for (const sm of props.subMessages) {
    if (sm.type !== 'Normal' || sm.config?.is_tail_tool !== true) continue
    if (!sm.content) continue
    try {
      const content = JSON.parse(sm.content) as TailToolContent
      if (!content || typeof content !== 'object') continue
      if (content.status === 'error') hasError = true
      if (content.error) {
        errors.push(content.error)
        hasError = true
      }
      if (Array.isArray(content.calls)) {
        for (const call of content.calls) {
          if (!call || typeof call !== 'object') continue
          if (call.status === 'error') hasError = true
          calls.push(call)
        }
      }
    } catch {
      // 忽略非法 JSON
    }
  }

  return { calls, topError: errors.join('\n'), hasError }
})

const calls = computed(() => parsed.value.calls)
const topError = computed(() => parsed.value.topError)
const hasError = computed(() => parsed.value.hasError)

function isErrorCall(call: TailToolCall): boolean {
  return call.status === 'error'
}

function hasArgs(call: TailToolCall): boolean {
  const a = call.arguments
  return !!a && typeof a === 'object' && Object.keys(a).length > 0
}

function formatArgs(args?: Record<string, unknown>): string {
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args ?? '')
  }
}
</script>

<style scoped>
.tail-tool-panel {
  /* 默认：淡紫色底 + 紫色左边框，与正文视觉区分；缩小存在感，不占整行 */
  --tail-tool-bg: rgba(146, 128, 214, 0.07);
  --tail-tool-accent: #b3a9d8;

  display: inline-block;
  align-self: flex-start;
  width: fit-content;
  max-width: 100%;
  margin-top: 6px;
  border-left: 2px solid var(--tail-tool-accent);
  background-color: var(--tail-tool-bg);
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
  overflow: hidden;
}

.tail-tool-panel.is-error {
  --tail-tool-bg: var(--el-color-error-light-9);
  --tail-tool-accent: var(--el-color-error-light-3);
}

/* ========== 头部 ========== */
.tail-tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  cursor: pointer;
  user-select: none;
  font-weight: 600;
  color: var(--el-text-color-regular);
  transition: color 0.2s;
}
.tail-tool-header:hover {
  color: var(--el-color-primary);
}
.tail-tool-arrow {
  font-size: 12px;
}
.tail-tool-count {
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

/* ========== 内容区 ========== */
.tail-tool-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 10px 8px 10px;
}

.tail-tool-call {
  padding: 6px 8px;
  background-color: var(--el-bg-color);
  border-left: 2px solid var(--tail-tool-accent);
  border-radius: 0 4px 4px 0;
}
.tail-tool-call.is-error {
  border-left-color: var(--el-color-error);
}

.tail-tool-call-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.tail-tool-task {
  font-weight: 600;
  color: var(--el-text-color-primary);
  word-break: break-all;
}
.tail-tool-status {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.tail-tool-status.is-error {
  color: var(--el-color-error);
}

.tail-tool-row {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}
.tail-tool-label {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}
.tail-tool-label.is-error {
  color: var(--el-color-error);
}
.tail-tool-text {
  flex: 1;
  min-width: 0;
  max-height: 160px;
  margin: 0;
  overflow: auto;
  font-family: inherit;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
}
.tail-tool-text.is-error {
  color: var(--el-color-error);
}
</style>
