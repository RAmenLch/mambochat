// frontend/mambo/src/composables/useTaskSubSteps.ts
// 子 Agent（task 工具）追踪步骤：store 实时数据 + 按需拉取的历史数据合并。
//
// 背景：
// - 后端主查询在 SQL 层排除 TaskSubStep（crud/message_crud.py），刷新后 store 里没有历史步骤，
//   必须走 GET /messages/{id}/task-substeps；
// - 生成过程中步骤经 SSE 逐条写入 store；
// - 两者必须按 id 合并，否则「刷新发生在生成中途」时只能看到其中一部分。

import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import type {
  Message,
  MessageRole,
  MessageStatus,
  ReviewToolContent,
  SecurityReviewContent,
  SubMessage,
  SubMessageType,
  TaskSubStepContent,
} from '@/api/types'
import { getMessageTaskSubSteps } from '@/api/chatService'

/** 拉取结果缓存：key = `${messageId}:${taskGroupId}` */
const stepCache = new Map<string, SubMessage[]>()

function timestampOf(sub: SubMessage): number {
  const value = Date.parse(sub.createdAt ?? '')
  return Number.isNaN(value) ? 0 : value
}

/** 按 step_order 排序，解析失败时退回创建时间 */
export function sortTaskSubSteps(steps: SubMessage[]): SubMessage[] {
  return [...steps].sort((a, b) => {
    try {
      const ca = JSON.parse(a.content) as TaskSubStepContent
      const cb = JSON.parse(b.content) as TaskSubStepContent
      return ca.step_order - cb.step_order
    } catch {
      return timestampOf(a) - timestampOf(b)
    }
  })
}

/** 多来源合并（按 id 去重，后者覆盖前者），再统一排序 */
export function mergeTaskSubSteps(...sources: SubMessage[][]): SubMessage[] {
  const byId = new Map<string, SubMessage>()
  for (const list of sources) {
    for (const sm of list) {
      byId.set(sm.id, sm)
    }
  }
  return sortTaskSubSteps([...byId.values()])
}

/**
 * @param message 承载步骤的父消息（可为虚拟消息）
 * @param taskGroupId task 工具的 tool_call_id
 * @param enabled 是否启用拉取（通常是弹窗 visible），未传时视为启用
 */
export function useTaskSubSteps(
  message: Ref<Message | null | undefined>,
  taskGroupId: Ref<string | null>,
  enabled?: Ref<boolean | undefined>,
) {
  const remoteSteps = ref<SubMessage[]>([])
  const isLoading = ref(false)
  let requestSeq = 0

  /** store 中实时推送的步骤 */
  const storeSteps = computed<SubMessage[]>(() => {
    const groupId = taskGroupId.value
    const msg = message.value
    if (!groupId || !msg) return []
    return msg.sub_messages.filter(
      sm => sm.type === 'TaskSubStep' && sm.config?.task_group_id === groupId,
    )
  })

  watch(
    [
      taskGroupId,
      () => message.value?.id,
      () => (enabled ? enabled.value !== false : true),
    ],
    async ([groupId, messageId, active]) => {
      if (!active || !groupId || !messageId) {
        remoteSteps.value = []
        return
      }

      const cacheKey = `${messageId}:${groupId}`
      const cached = stepCache.get(cacheKey)
      if (cached) {
        remoteSteps.value = cached
        return
      }

      const seq = ++requestSeq
      isLoading.value = true
      try {
        const fetched = await getMessageTaskSubSteps(messageId, groupId)
        if (seq !== requestSeq) return
        stepCache.set(cacheKey, fetched)
        remoteSteps.value = fetched
      } catch (error) {
        if (seq === requestSeq) remoteSteps.value = []
        console.error('Failed to fetch task substeps:', error)
      } finally {
        if (seq === requestSeq) isLoading.value = false
      }
    },
    { immediate: true },
  )

  const steps = computed(() => mergeTaskSubSteps(remoteSteps.value, storeSteps.value))
  const hasSteps = computed(() => steps.value.length > 0)

  return { steps, hasSteps, isLoading }
}

/** 与主 Agent（UsageInfo）一致的时长格式 */
export function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}s`
  const totalSec = Math.round(sec)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`
  const h = Math.floor(m / 60)
  const restM = m % 60
  return restM > 0 ? `${h}h ${restM}m` : `${h}h`
}

/**
 * 子任务耗时（近似值）：取所有步骤时间戳的跨度；
 * 任务仍在进行时以当前时间收尾，并每秒刷新，与主 Agent 耗时展示逻辑一致。
 */
export function useTaskDuration(steps: Ref<SubMessage[]>, isRunning: Ref<boolean>) {
  const now = ref(Date.now())
  let timer: number | undefined

  watch(
    isRunning,
    running => {
      if (running && !timer) {
        timer = window.setInterval(() => { now.value = Date.now() }, 1000)
      } else if (!running && timer) {
        window.clearInterval(timer)
        timer = undefined
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    if (timer) window.clearInterval(timer)
  })

  const range = computed<{ start: number; end: number } | null>(() => {
    let start = Number.POSITIVE_INFINITY
    let end = Number.NEGATIVE_INFINITY
    for (const sm of steps.value) {
      const t = timestampOf(sm)
      if (!t) continue
      if (t < start) start = t
      if (t > end) end = t
    }
    if (!Number.isFinite(start) || !Number.isFinite(end)) return null
    return { start, end }
  })

  /** 形如 `1m 23s`；无可用时间戳时返回空串 */
  const durationText = computed(() => {
    const r = range.value
    if (!r) return ''
    const end = isRunning.value ? Math.max(now.value, r.end) : r.end
    return formatDuration(Math.max(end - r.start, 0) / 1000)
  })

  return { durationText }
}

/** ReviewTool 映射条目：携带真实 sub_message_id 以便子代理面板提交审核 */
export interface ReviewToolMapEntry {
  content: ReviewToolContent
  sub_message_id: string
}

/** 从消息中收集 SecurityReview：tool_call_id → content */
export function collectSecurityReviewMap(
  message: Message | null | undefined,
): Map<string, SecurityReviewContent> {
  const map = new Map<string, SecurityReviewContent>()
  if (!message) return map
  for (const sm of message.sub_messages) {
    if (sm.type !== 'SecurityReview') continue
    try {
      const content = JSON.parse(sm.content) as SecurityReviewContent
      map.set(content.tool_call_id, content)
    } catch { /* ignore */ }
  }
  return map
}

/** 从消息中收集 ReviewTool：tool_call_id → { content, sub_message_id } */
export function collectReviewToolMap(
  message: Message | null | undefined,
): Map<string, ReviewToolMapEntry> {
  const map = new Map<string, ReviewToolMapEntry>()
  if (!message) return map
  for (const sm of message.sub_messages) {
    if (sm.type !== 'ReviewTool') continue
    try {
      const content = JSON.parse(sm.content) as ReviewToolContent
      map.set(content.tool_call_id, { content, sub_message_id: sm.id })
    } catch { /* ignore */ }
  }
  return map
}

/**
 * 把 TaskSubStep 步骤数组转换为虚拟 Message（Reasoning / Normal / McpTool 三类子消息），
 * 供气泡组件直接渲染。子代理内部的 AI/人工审核按 sub_tool_call_id 绑定回步骤。
 */
export function buildSubAgentVirtualMessage(
  steps: SubMessage[],
  securityReviewMap?: Map<string, SecurityReviewContent>,
  reviewToolMap?: Map<string, ReviewToolMapEntry>,
): Message {
  const subMessages: SubMessage[] = []

  for (let i = 0; i < steps.length; i++) {
    const sm = steps[i]
    let stepData: TaskSubStepContent
    try {
      stepData = JSON.parse(sm.content) as TaskSubStepContent
    } catch {
      continue
    }

    if (stepData.display_type === 'reasoning') {
      subMessages.push({
        ...sm,
        type: 'Reasoning' as SubMessageType,
        content: stepData.content,
        config: { is_collapsed: false, is_minimal: true },
      } as SubMessage)
      continue
    }

    if (stepData.display_type === 'text') {
      subMessages.push({
        ...sm,
        type: 'Normal' as SubMessageType,
        content: stepData.content,
        config: { is_collapsed: false },
      } as SubMessage)
      continue
    }

    if (stepData.display_type !== 'tool_call') continue // tool_result 已合并到 tool_call

    // 匹配 tool_result（全数组搜索，step_order 可能交叉）
    let resultText: string | null = null
    for (let j = 0; j < steps.length; j++) {
      if (j === i) continue
      try {
        const next = JSON.parse(steps[j].content) as TaskSubStepContent
        if (next.display_type !== 'tool_result') continue
        if (stepData.sub_tool_call_id && next.sub_tool_call_id === stepData.sub_tool_call_id) {
          resultText = next.content
          break
        }
        // 降级兜底：无 sub_tool_call_id 时用 tool_name 匹配
        if (!stepData.sub_tool_call_id && !next.sub_tool_call_id && next.tool_name === stepData.tool_name) {
          resultText = next.content
          break
        }
      } catch { /* skip */ }
    }

    const toolCallId = `${stepData.tool_call_id}_s_${stepData.step_order}`
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
    } as SubMessage)

    // 绑定 AI 安全审核
    if (stepData.sub_tool_call_id && securityReviewMap) {
      const review = securityReviewMap.get(stepData.sub_tool_call_id)
      if (review) {
        subMessages.push({
          id: crypto.randomUUID(),
          type: 'SecurityReview' as SubMessageType,
          content: JSON.stringify({ ...review, tool_call_id: toolCallId }),
          config: { is_collapsed: false, context_participation_length: 0 },
          createdAt: sm.createdAt,
          messageId: sm.messageId,
          sortOrder: 2,
          status: 'completed',
        } as SubMessage)
      }
    }

    // 绑定人工审核（保留真实 sub_message_id，审核提交依赖它）
    if (stepData.sub_tool_call_id && reviewToolMap) {
      const rtoolEntry = reviewToolMap.get(stepData.sub_tool_call_id)
      if (rtoolEntry) {
        subMessages.push({
          id: rtoolEntry.sub_message_id,
          type: 'ReviewTool' as SubMessageType,
          content: JSON.stringify({ ...rtoolEntry.content, tool_call_id: toolCallId }),
          config: { is_collapsed: false, context_participation_length: 0 },
          createdAt: sm.createdAt,
          messageId: sm.messageId,
          sortOrder: 2,
          status: 'completed',
        } as SubMessage)
      }
    }
  }

  return {
    id: steps[0]?.messageId || '',
    createdAt: steps[0]?.createdAt || new Date().toISOString(),
    role: 'assistant' as MessageRole,
    chatId: '',
    sortOrder: 0,
    sub_messages: subMessages,
    status: 'completed' as MessageStatus,
    parentId: null,
    lastActiveAt: steps[0]?.createdAt || new Date().toISOString(),
    sibling_ids: [],
    sibling_index: 0,
  }
}
