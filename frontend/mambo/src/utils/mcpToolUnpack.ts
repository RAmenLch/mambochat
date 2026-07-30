import type { McpToolContent, ReviewToolContent } from '@/api/types'

export interface UnpackedToolCall {
  /** 显示用的工具名称：mcp_call_tool → "serverName/toolName"，否则原样 */
  displayName: string
  /** 内层工具名（mcp_call_tool 时为 tool_name） */
  effectiveName: string
  /** MCP server 名，仅 mcp_call_tool 时有值 */
  serverName?: string
  /** 内层参数（mcp_call_tool 时为 arguments.arguments） */
  effectiveArgs: Record<string, unknown> | string
  /** 是否为 mcp_call_tool 包装调用 */
  isMcpWrapped: boolean
}

/**
 * 拆包 mcp_call_tool：将包装层的 server_name / tool_name / arguments 展开，
 * 返回内层工具的真实名称和参数。
 */
export function unpackMcpToolCall(
  content: McpToolContent | ReviewToolContent,
): UnpackedToolCall {
  if (content.name === 'mcp_call_tool') {
    let args: Record<string, unknown> = {}
    if (typeof content.arguments === 'string') {
      try {
        args = JSON.parse(content.arguments)
      } catch {
        /* keep empty */
      }
    } else if (content.arguments && typeof content.arguments === 'object') {
      args = content.arguments as Record<string, unknown>
    }

    const serverName = (args.server_name as string) || 'MCP'
    const toolName = (args.tool_name as string) || 'unknown'
    const innerArgs = (args.arguments as Record<string, unknown>) || {}

    return {
      displayName: `${serverName}/${toolName}`,
      effectiveName: toolName,
      serverName,
      effectiveArgs: innerArgs,
      isMcpWrapped: true,
    }
  }

  return {
    displayName: content.name,
    effectiveName: content.name,
    effectiveArgs: content.arguments,
    isMcpWrapped: false,
  }
}

function basename(p: string): string {
  const segs = p.replace(/\\/g, '/').split('/').filter(Boolean)
  return segs.length ? segs[segs.length - 1] : p
}

/** VirtualPath 可能被序列化为 { value: "..." } 对象，取实际字符串值 */
function extractPath(raw: unknown): string | null {
  if (raw == null) return null
  if (typeof raw === 'string') return raw
  if (typeof raw === 'object' && (raw as Record<string, unknown>).value != null) {
    return String((raw as Record<string, unknown>).value)
  }
  return String(raw)
}

function extractString(raw: unknown): string | null {
  if (raw == null) return null
  return String(raw)
}

/**
 * 提取工具参数摘要，用于在工具气泡上直接展示关键参数。
 * 仅对 read / edit / write / ls / grep / glob / delete 返回有效摘要，其余返回空字符串。
 */
export function getToolArgsSummary(content: McpToolContent | ReviewToolContent): string {
  const unpacked = unpackMcpToolCall(content)
  const name = unpacked.effectiveName

  let args: Record<string, unknown> = {}
  if (typeof unpacked.effectiveArgs === 'string') {
    try {
      args = JSON.parse(unpacked.effectiveArgs)
    } catch {
      /* keep empty */
    }
  } else {
    args = unpacked.effectiveArgs as Record<string, unknown>
  }

  switch (name) {
    case 'read': {
      const fp = extractPath(args?.file_path)
      if (fp == null) return ''
      const base = basename(fp)
      const off = args?.offset != null ? Number(args.offset) : 0
      const lim = args?.limit != null ? Number(args.limit) : 2000
      if (off !== 0 || lim !== 2000) {
        return `${base} L${off}-${off + lim}`
      }
      return base
    }
    case 'edit':
    case 'write': {
      const fp = extractPath(args?.file_path)
      return fp != null ? basename(fp) : ''
    }
    case 'ls':
    case 'delete': {
      const p = extractPath(args?.path)
      return p != null ? basename(p) : ''
    }
    case 'grep': {
      const p = extractString(args?.pattern)
      return p != null ? `"${p}"` : ''
    }
    case 'glob': {
      const p = extractString(args?.pattern)
      return p != null ? p : ''
    }
    default:
      return ''
  }
}
