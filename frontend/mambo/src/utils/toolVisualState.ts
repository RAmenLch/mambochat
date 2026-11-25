// frontend/mambo/src/utils/toolVisualState.ts
// 工具气泡的统一视觉状态：由「子消息生命周期状态」+「工具结果语义」共同推导。
//
// 为什么需要它：
// - 后端在用户中断 / 生成异常时会把仍未产出结果的工具子消息置为 failed，
//   但内容里没有 result / is_error；
// - 工具真正失败时是「生命周期 completed + 内容 is_error=true」。
// 只看 is_error 会把中断显示成成功，只看 status 又会漏掉工具错误。

import type { SubMessage, McpToolContent } from '@/api/types'

export type ToolVisualState = 'generating' | 'error' | 'interrupted' | 'success'

function parseMcpContent(tool: SubMessage): McpToolContent | null {
  if (tool.type !== 'McpTool') return null
  try {
    return JSON.parse(tool.content) as McpToolContent
  } catch {
    return null
  }
}

/**
 * 工具气泡视觉状态：
 * - generating：仍在生成（尚未落地结果）
 * - error：产出了结果且结果为错误
 * - interrupted：未产出结果即结束（用户中断 / 生成异常）
 * - success：正常完成
 */
export function getToolVisualState(tool: SubMessage): ToolVisualState {
  if (tool.status === 'generating') return 'generating'
  const content = parseMcpContent(tool)
  if (content?.is_error) return 'error'
  if (tool.status === 'failed') return content?.result ? 'error' : 'interrupted'
  return 'success'
}
