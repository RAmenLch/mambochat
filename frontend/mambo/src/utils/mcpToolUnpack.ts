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
