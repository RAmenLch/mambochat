// frontend/mambo/src/utils/chatExport.ts
// 会话导出 / 导入的共用逻辑（桌面与移动端一致）：
// - JSON：后端按可导入格式生成（mambochat.chat-export）
// - Markdown / HTML：前端基于已加载的消息拼装
// 下载统一走 Blob + a[download]，不依赖 Electron。

import type { Chat, Message } from '@/api/types'
import { exportChatJson } from '@/api/chatService'
import { getResourceDetails } from '@/api/resourceService'

export type ChatExportFormat = 'json' | 'markdown' | 'html'

export function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  }
  return text.replace(/[&<>"']/g, m => map[m])
}

function triggerDownload(content: string | Blob, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** 导出文件名：`{会话名}_{日期}.{ext}` */
export function exportFilename(chatName: string, ext: string): string {
  const safeName = (chatName || 'chat').replace(/[/\\?%*:|"<>]/g, '_')
  const timestamp = new Date().toISOString().slice(0, 10)
  return `${safeName}_${timestamp}.${ext}`
}

/** 完整系统提示词 = 会话提示词 + 挂载资源的当前版本内容 */
export async function resolveExportSystemPrompt(chat: Chat | null | undefined): Promise<string> {
  if (!chat) return ''
  const basePrompt = chat.systemPrompt || ''
  const resourceIds = chat.resource_prompt_list || []
  if (resourceIds.length === 0) return basePrompt

  try {
    const resources = await Promise.all(
      resourceIds.map(id => getResourceDetails(id).catch(() => null)),
    )
    const contents = resources
      .filter(r => r && r.latest_version && r.latest_version.content)
      .map(r => r!.latest_version!.content as string)
    return [basePrompt, ...contents].join('\n\n').trim()
  } catch (error) {
    console.error('Failed to fetch resources for export:', error)
    return basePrompt
  }
}

/** 消息正文（仅 Normal / File，按顺序拼接） */
function messageText(msg: Message): string {
  return msg.sub_messages
    .filter(sm => sm.type === 'Normal' || sm.type === 'File')
    .map(sm => sm.content)
    .join('\n')
}

export function buildMarkdownExport(systemPrompt: string, messages: Message[]): string {
  let md = `# System Prompt\n\n${systemPrompt}\n\n---\n\n# Chat History\n\n`
  messages.forEach(msg => {
    const roleTitle = msg.role === 'user' ? 'User' : 'Assistant'
    md += `## ${roleTitle}\n\n${messageText(msg)}\n\n`
  })
  return md
}

export function buildHtmlExport(systemPrompt: string, chatName: string, messages: Message[]): string {
  const messagesHtml = messages.map(msg => {
    const roleClass = msg.role === 'user' ? 'user-message' : 'assistant-message'
    const roleLabel = msg.role === 'user' ? 'User' : 'Assistant'
    const content = msg.sub_messages
      .filter(sm => sm.type === 'Normal' || sm.type === 'File')
      .map(sm => `<div class="message-content">${escapeHtml(sm.content).replace(/\n/g, '<br>')}</div>`)
      .join('')
    return `
          <div class="message ${roleClass}">
            <div class="message-role">${roleLabel}</div>
            ${content}
          </div>
        `
  }).join('')

  return `
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
          <meta charset="UTF-8">
          <title>${escapeHtml(chatName)}</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; background: #f9f9f9; }
            .container { background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
            h1 { border-bottom: 2px solid #eee; padding-bottom: 10px; }
            .system-prompt { background: #f0f7ff; padding: 15px; border-radius: 6px; border-left: 4px solid #409eff; margin-bottom: 30px; white-space: pre-wrap; }
            .message { margin-bottom: 20px; padding: 15px; border-radius: 6px; }
            .message-role { font-weight: bold; margin-bottom: 8px; font-size: 0.9em; opacity: 0.8; }
            .user-message { background: #e6f7ff; border: 1px solid #bae7ff; }
            .assistant-message { background: #f6ffed; border: 1px solid #b7eb8f; }
            .message-content { white-space: pre-wrap; }
          </style>
        </head>
        <body>
          <div class="container">
            <h1>${escapeHtml(chatName)}</h1>
            <div class="system-prompt"><strong>System Prompt:</strong><br/>${escapeHtml(systemPrompt).replace(/\n/g, '<br/>')}</div>
            <div class="chat-history">${messagesHtml}</div>
          </div>
        </body>
        </html>
      `
}

/**
 * 导出一个会话并触发下载。
 * @throws 网络/生成失败时抛出，由调用方提示
 */
export async function exportChat(
  chat: Chat | null | undefined,
  messages: Message[],
  format: ChatExportFormat,
): Promise<void> {
  if (!chat) return
  const chatName = chat.name || 'chat'

  if (format === 'json') {
    const blob = await exportChatJson(chat.id)
    triggerDownload(blob, exportFilename(chatName, 'json'), 'application/json')
    return
  }

  const systemPrompt = await resolveExportSystemPrompt(chat)
  if (format === 'markdown') {
    triggerDownload(
      buildMarkdownExport(systemPrompt, messages),
      exportFilename(chatName, 'md'),
      'text/markdown',
    )
    return
  }

  triggerDownload(
    buildHtmlExport(systemPrompt, chatName, messages),
    exportFilename(chatName, 'html'),
    'text/html',
  )
}
