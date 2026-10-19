// frontend/mambo/src/utils/webSearchResult.ts
import type { McpToolContent, ReviewToolContent, WebSearchDisplayItem } from '@/api/types'
import { unpackMcpToolCall } from './mcpToolUnpack'

/** 搜索工具名（含历史名 ddgs_search） */
const WEB_SEARCH_TOOL_NAMES = ['web_search', 'ddgs_search']

/** 单条搜索结果的展示模型（已合并后端 display 与 result 两种来源） */
export interface WebSearchEntry {
  title: string
  url: string
  /** 列表展示用的短摘要 */
  snippet: string
  /** 展开后可读的长摘要（来自 result，老数据可能为空） */
  summary: string
  /** 网页正文（后端开启 need_content 时有值） */
  content: string
  siteName: string | null
  siteIcon: string | null
  /** 已格式化为 YYYY-MM-DD */
  date: string | null
  score: number | null
  authority: number | null
}

export type WebSearchParsed =
  | { kind: 'list'; query: string; provider: string; items: WebSearchEntry[] }
  | { kind: 'error'; message: string }
  | { kind: 'message'; message: string }

/** 判断该工具调用是否为搜索结果（兼容 mcp_call_tool / tail_tool 包装） */
export function isWebSearchTool(
  content: McpToolContent | ReviewToolContent | null | undefined,
): boolean {
  if (!content) return false
  if ((content as McpToolContent).display?.kind === 'web_search') return true
  return WEB_SEARCH_TOOL_NAMES.includes(unpackMcpToolCall(content).effectiveName)
}

function safeParseJson(raw: string | null | undefined): unknown {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/** RFC3339 → YYYY-MM-DD（按 UTC 展示，避免时区造成日期漂移） */
export function formatSearchDate(raw: unknown): string | null {
  if (typeof raw !== 'string' || !raw.trim()) return null
  const text = raw.trim()
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(text)
  if (match) return match[1]
  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed.toISOString().slice(0, 10)
}

export function searchUrlHost(url: string): string {
  try {
    const host = new URL(url).hostname
    return host.startsWith('www.') ? host.slice(4) : host
  } catch {
    return url
  }
}

/** 站点名兜底：display.site_name → 域名 */
function resolveSiteName(siteName: unknown, url: string): string | null {
  if (typeof siteName === 'string' && siteName.trim()) return siteName.trim()
  if (!url) return null
  return searchUrlHost(url)
}

function toNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function toStringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/** 把 result 中的长摘要 / 正文按 URL 索引，供展开态使用 */
function indexResultEntries(rawResult: unknown): Map<string, Record<string, unknown>> {
  const index = new Map<string, Record<string, unknown>>()
  if (!Array.isArray(rawResult)) return index
  for (const entry of rawResult) {
    if (!entry || typeof entry !== 'object') continue
    const record = entry as Record<string, unknown>
    const url = toStringValue(record.url)
    if (url) index.set(url, record)
  }
  return index
}

function buildEntry(
  item: WebSearchDisplayItem | Record<string, unknown>,
  detail: Record<string, unknown> | undefined,
): WebSearchEntry {
  const record = item as unknown as Record<string, unknown>
  const url = toStringValue(record.url)
  const snippet = toStringValue(record.snippet)
  const summary = toStringValue(detail?.summary) || toStringValue(record.summary)
  return {
    title: toStringValue(record.title) || url,
    url,
    snippet: snippet || summary || toStringValue(detail?.snippet),
    summary: summary || snippet,
    content: toStringValue(detail?.content),
    siteName: resolveSiteName(record.site_name, url),
    siteIcon: typeof record.site_icon === 'string' && record.site_icon ? record.site_icon : null,
    date: formatSearchDate(record.date),
    score: toNumberOrNull(record.rerank_score),
    authority: toNumberOrNull(record.authority),
  }
}

/**
 * 解析搜索结果：
 * - 优先使用后端下发的 display 快照（含 snippet / site_icon / authority）；
 * - 老消息缺失 display 时回退解析 result JSON；
 * - 无法结构化（纯文本、非搜索工具、无结果）返回 null，调用方保持原始文本渲染。
 */
export function parseWebSearchResult(
  content: McpToolContent | ReviewToolContent | null | undefined,
): WebSearchParsed | null {
  if (!content || !isWebSearchTool(content)) return null

  const toolContent = content as McpToolContent
  const resultJson = safeParseJson(toolContent.result)

  if (resultJson && !Array.isArray(resultJson) && typeof resultJson === 'object') {
    const record = resultJson as Record<string, unknown>
    const error = toStringValue(record.error)
    if (error) return { kind: 'error', message: error }
    const message = toStringValue(record.message)
    if (message) return { kind: 'message', message }
  }

  const display = toolContent.display
  const displayItems = Array.isArray(display?.items) ? display!.items! : []
  const detailIndex = indexResultEntries(resultJson)

  let items: WebSearchEntry[]
  if (displayItems.length) {
    items = displayItems.map((item) => buildEntry(item, detailIndex.get(toStringValue(item.url))))
  } else if (Array.isArray(resultJson)) {
    items = resultJson
      .filter((entry): entry is Record<string, unknown> => !!entry && typeof entry === 'object')
      .map((entry) => buildEntry(entry, entry))
  } else {
    return null
  }

  if (!items.length) return null

  return {
    kind: 'list',
    query: display?.query || '',
    provider: display?.provider || '',
    items,
  }
}
