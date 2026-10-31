// frontend/mambo/src/composables/useImageRuns.ts

import { computed, type ComputedRef, type Ref } from 'vue'
import type { Message, SubMessage } from '@/api/types'

/**
 * 生图「按次编组」聚合：
 *
 * - 一次 `image_generate_show`（或一次平台重跑）产出的多张图 = 一个 **run**；
 * - 同一位置的第 1/2/3 次生成共享一个 **slot**（插槽），前端用左右箭头在 run 之间切换；
 * - 只有 `Normal` / `Group` 两种展示形态参与该区域，其余（Mini_Avatar / Gal_Avatar /
 *   Spark）仍走原有渲染逻辑，避免与头像位、全局折叠打架。
 *
 * 归属推算：
 *   runId  = config.image_run_id ?? 从 McpTool 结果里的 file_id 反查出的 tool_call_id
 *   slotId = config.image_slot_id ?? runId（首次生成自成一插槽）
 */

const GALLERY_MODES = new Set(['Normal', 'Group'])

/** 一条龙生图工具名：只有它（以及平台重跑）产出的图片才提供“重新生成”入口 */
const IMAGE_TOOL_NAME = 'image_generate_show'

export interface ImageRun {
  runId: string
  slotId: string
  /** 本次生成已完成、可直接展示的图片（按创建时间排序） */
  files: SubMessage[]
  /** 本次生成中尚未落盘（等待中 / 超时失败）的图片子消息 */
  pendingFiles: SubMessage[]
  /** 本次生成使用的展示形态 */
  mode: string
  /** 本次生成的参数快照 */
  args: Record<string, any> | null
  /** 生成记录子消息 id（平台重跑才有） */
  recordId: string | null
  /** 首轮工具调用子消息 id（用于打开参数详情） */
  toolSubId: string | null
  /** 产出该 run 的工具名（image_generate_show / show ...） */
  toolName: string
  /** 是否可以用同一组参数重跑 */
  canRerun: boolean
  /** run 状态：completed / pending（等待落盘）/ failed（超时或失败） */
  status: 'completed' | 'pending' | 'failed'
  /** 可作为重跑 / 获取文件来源的子消息 id（图片优先，其次失败的待生成文件） */
  sourceSubId: string | null
  createdAt: number
}

export interface ImageRunSlot {
  slotId: string
  runs: ImageRun[]
  /** 当前置顶的 run */
  pinnedRunId: string
  /** 承载 `image_pinned_run_id` 的图片子消息 id（插槽内最早的一条） */
  pinnedHostId: string | null
}

interface ToolIndexEntry {
  sub: SubMessage
  name: string
  args: Record<string, any> | null
  fileIds: Set<string>
}

export interface ImageRunsAnalysis {
  slots: ImageRunSlot[]
  /** 已归入图片区域的 File 子消息 id（这些不再由正文分组渲染） */
  galleryFileIds: Set<string>
}

function parseJson<T = any>(raw: unknown): T | null {
  if (typeof raw !== 'string' || !raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function timestampOf(sub: SubMessage): number {
  const value = Date.parse(sub.createdAt ?? '')
  return Number.isNaN(value) ? 0 : value
}

function collectFileIds(content: any): Set<string> {
  const ids = new Set<string>()
  const result = parseJson<any>(content?.result)
  if (!result) return ids
  if (Array.isArray(result.files)) {
    for (const item of result.files) {
      if (item && typeof item.file_id === 'string' && item.file_id) ids.add(item.file_id)
    }
  } else if (typeof result.file_id === 'string' && result.file_id) {
    ids.add(result.file_id)
  }
  return ids
}

function analyze(message: Message | null | undefined): ImageRunsAnalysis {
  const empty: ImageRunsAnalysis = { slots: [], galleryFileIds: new Set() }
  const subs = message?.sub_messages ?? []
  if (subs.length === 0) return empty

  // 1. 索引 McpTool 子消息：run → 参数 / 产出文件 / 是否为重跑记录
  const tools = new Map<string, ToolIndexEntry>()
  const recordByRun = new Map<string, SubMessage>()
  for (const sm of subs) {
    if (sm.type !== 'McpTool') continue
    const content = parseJson<any>(sm.content)
    const runId = content?.tool_call_id
    if (typeof runId !== 'string' || !runId) continue
    tools.set(runId, {
      sub: sm,
      name: typeof content?.name === 'string' ? content.name : '',
      args: content?.arguments && typeof content.arguments === 'object' ? content.arguments : null,
      fileIds: collectFileIds(content),
    })
    if (sm.config?.is_image_run_record) recordByRun.set(runId, sm)
  }

  // 2. 老数据兜底：没有 image_run_id 时，用 file_id 反查它属于哪一次工具调用
  const runByFileId = new Map<string, string>()
  for (const [runId, entry] of tools) {
    for (const fileId of entry.fileIds) {
      if (!runByFileId.has(fileId)) runByFileId.set(fileId, runId)
    }
  }

  // 3. 逐条图片子消息归组：已完成图片与「等待落盘 / 超时失败」的子消息都参与编组，
  //    后者即使没有 file_info 也必须能进入图片区域（否则超时后区域直接消失）
  const fileSubs = subs
    .filter(sm => {
      if (sm.type !== 'File') return false
      if (sm.file_info?.mime_type?.startsWith('image/')) return true
      // 未落盘的待生成文件：只要有 run 归属或 pending 路径，就归入图片区域
      return (
        !sm.file_info &&
        (!!sm.config?.image_run_id || !!sm.config?.pending_file_path)
      )
    })
    .slice()
    .sort((a, b) => timestampOf(a) - timestampOf(b))

  const runFiles = new Map<string, SubMessage[]>()
  const runPending = new Map<string, SubMessage[]>()
  const runSlot = new Map<string, string>()
  const slotFirstFileId = new Map<string, string>()
  const slotPinnedRun = new Map<string, string>()

  for (const sm of fileSubs) {
    const config = sm.config ?? {}
    const mode = (config.show_tool_mode as string) || 'Normal'
    if (!GALLERY_MODES.has(mode)) continue

    const isImageFile = !!sm.file_info?.mime_type?.startsWith('image/')
    const runId =
      (config.image_run_id as string) || runByFileId.get(sm.content) || ''
    if (!runId) continue

    const slotId = (config.image_slot_id as string) || runId
    if (!runFiles.has(runId)) {
      runFiles.set(runId, [])
      runPending.set(runId, [])
      runSlot.set(runId, slotId)
    }
    if (isImageFile) runFiles.get(runId)!.push(sm)
    else runPending.get(runId)!.push(sm)

    if (!slotFirstFileId.has(slotId)) slotFirstFileId.set(slotId, sm.id)
    if (config.image_pinned_run_id && !slotPinnedRun.has(slotId)) {
      slotPinnedRun.set(slotId, config.image_pinned_run_id as string)
    }
  }

  /** 由子消息状态推导 run 状态：失败优先，其次等待中 */
  function resolveRunStatus(pendingFiles: SubMessage[], fallback: string): ImageRun['status'] {
    if (pendingFiles.some(sm => sm.status === 'failed')) return 'failed'
    if (pendingFiles.length > 0) return 'pending'
    if (fallback === 'failed') return 'failed'
    return 'completed'
  }

  // 4. 组装插槽：单 run 单图不占用该区域，交回原有渲染
  const runsBySlot = new Map<string, ImageRun[]>()
  for (const [runId, files] of runFiles) {
    const slotId = runSlot.get(runId)!
    const pendingFiles = runPending.get(runId) ?? []
    const config = (files[0] ?? pendingFiles[0])?.config ?? {}
    const record = recordByRun.get(runId)
    const tool = tools.get(runId)
    const run: ImageRun = {
      runId,
      slotId,
      files,
      pendingFiles,
      mode: (config.show_tool_mode as string) || 'Normal',
      args:
        (record && parseJson<any>(record.content)?.arguments) ||
        (config.image_run_args as Record<string, any> | null) ||
        tool?.args ||
        null,
      recordId: record?.id ?? null,
      toolSubId: tool?.sub.id ?? null,
      toolName: tool?.name || '',
      canRerun: Boolean(record) || tool?.name === IMAGE_TOOL_NAME,
      status: resolveRunStatus(pendingFiles, String(record?.status ?? '')),
      sourceSubId: files[0]?.id ?? pendingFiles[0]?.id ?? null,
      createdAt: timestampOf(files[0] ?? pendingFiles[0]),
    }
    if (!runsBySlot.has(slotId)) runsBySlot.set(slotId, [])
    runsBySlot.get(slotId)!.push(run)
  }

  // 4b. 失败的重跑没有图片子消息，但它记在插槽里，也要能切过去看到失败原因
  for (const [runId, record] of recordByRun) {
    if (runFiles.has(runId)) continue
    const recordConfig = record.config ?? {}
    const slotId = (recordConfig.image_slot_id as string) || runId
    const runs = runsBySlot.get(slotId)
    if (!runs) continue
    const content = parseJson<any>(record.content)
    runs.push({
      runId,
      slotId,
      files: [],
      pendingFiles: [],
      mode: (recordConfig.show_tool_mode as string) || 'Normal',
      args: content?.arguments ?? null,
      recordId: record.id,
      toolSubId: null,
      toolName: IMAGE_TOOL_NAME,
      canRerun: true,
      status: 'failed',
      sourceSubId: null,
      createdAt: timestampOf(record),
    })
  }

  const slots: ImageRunSlot[] = []
  const galleryFileIds = new Set<string>()
  for (const [slotId, runs] of runsBySlot) {
    runs.sort((a, b) => a.createdAt - b.createdAt)
    const worthGallery =
      runs.length > 1 ||
      runs.some(run => run.files.length > 1 || run.pendingFiles.length > 0 || run.canRerun)
    if (!worthGallery) continue
    const pinned = slotPinnedRun.get(slotId)
    const pinnedRunId =
      pinned && runs.some(run => run.runId === pinned) ? pinned : runs[runs.length - 1].runId
    slots.push({
      slotId,
      runs,
      pinnedRunId,
      pinnedHostId: slotFirstFileId.get(slotId) ?? null,
    })
    for (const run of runs) {
      for (const file of run.files) galleryFileIds.add(file.id)
      for (const file of run.pendingFiles) galleryFileIds.add(file.id)
    }
  }

  slots.sort((a, b) => (a.runs[0]?.createdAt ?? 0) - (b.runs[0]?.createdAt ?? 0))
  return { slots, galleryFileIds }
}

export function useImageRuns(message: Ref<Message | null | undefined>): {
  imageSlots: ComputedRef<ImageRunSlot[]>
  galleryFileIds: ComputedRef<Set<string>>
} {
  const analysis = computed(() => analyze(message.value))
  return {
    imageSlots: computed(() => analysis.value.slots),
    galleryFileIds: computed(() => analysis.value.galleryFileIds),
  }
}

/** 参数摘要：提示词截断 + 关键参数 */
export function describeRunArgs(args: Record<string, any> | null): string {
  if (!args) return ''
  const parts: string[] = []
  const prompt = typeof args.prompt === 'string' ? args.prompt.trim() : ''
  if (prompt) parts.push(prompt.length > 60 ? `${prompt.slice(0, 60)}…` : prompt)
  if (args.resolution) parts.push(String(args.resolution))
  if (args.count && Number(args.count) > 1) parts.push(`×${args.count}`)
  return parts.join(' · ')
}
