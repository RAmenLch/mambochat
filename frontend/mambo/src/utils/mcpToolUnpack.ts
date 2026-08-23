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

export interface GoalLoopRoundInfo {
  round: number
  max: number
}

/**
 * 从 get_goal 的 result 文本解析轮次信息。
 * result 是 get_goal 返回的 JSON 序列化字符串：{"goal": {...}, "message": "..."}，
 * 恒为合法 JSON（mambo_agents 内部 json.dumps 生成、后端原样存储），因此纯结构化解析、
 * 不使用正则（正则需全文匹配，容易命中 objective 正文里的"第 X/Y 轮"字样）。
 *
 * 轮次来源（全部为结构化字段）：
 *   - preset 模式（mambo_agents 0.3.0b3+）：goal.current_round 已是展示轮次，直接使用；
 *   - LLM 模式：goal.rounds 是已完成的轮数，展示轮次 = rounds + 1；
 *   - 旧版 preset 数据（无 current_round、rounds 恒为 0）无法得出真实轮次，返回 null
 *     降级为通用文案，避免误显示"第 1 轮"。
 * 解析失败（goal 缺失 / 非 JSON / 结构变化）返回 null，由调用方降级处理。
 */
export function parseGoalLoopRound(
  result: string | null | undefined,
): GoalLoopRoundInfo | null {
  if (!result) return null

  let payload: { goal?: { rounds?: unknown; max_rounds?: unknown; current_round?: unknown; created_by?: unknown } | null } | null
  try {
    payload = JSON.parse(result) as typeof payload
  } catch {
    /* 非 JSON（理论不发生），按无法解析处理 */
    return null
  }

  const goal = payload?.goal
  if (!goal || typeof goal.max_rounds !== 'number' || goal.max_rounds < 1) return null

  // preset 模式：current_round 已是展示轮次（mambo_agents 0.3.0b3+）
  if (typeof goal.current_round === 'number' && goal.current_round >= 1) {
    return { round: goal.current_round, max: goal.max_rounds }
  }

  // 旧版 preset 数据：rounds 恒为 0，无法得出真实轮次
  if (goal.created_by === 'preset') return null

  // LLM 模式：rounds 是已完成的轮数，展示轮次 = rounds + 1
  if (typeof goal.rounds === 'number' && goal.rounds >= 0) {
    return { round: goal.rounds + 1, max: goal.max_rounds }
  }

  return null
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
