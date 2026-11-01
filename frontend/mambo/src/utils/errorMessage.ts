// frontend/mambo/src/utils/errorMessage.ts
// Error 子消息（后端 ErrorContent）的解析与本地化，桌面端与移动端共用。

import i18n from '@/i18n'
import type { ErrorContent } from '@/api/types'

const ERROR_TYPE_PREFIX =
  /^(?:RuntimeError|ValueError|Exception|OSError|KeyError|TypeError|AttributeError|IndexError|ConnectionError|TimeoutError):\s*/

const ERROR_EXACT_MAP: Record<string, string> = {
  模型未返回任何摘要内容: 'chat.message.errorZipNoSummary',
  'DDG 返回了验证码页面，请稍后重试': 'chat.message.errorWebSearchCaptcha',
  会话未配置模型: 'chat.message.errorNoModelConfigured',
}

const ERROR_PREFIX_MATCHES: Array<{
  prefix: string
  key: string
  extract?: (body: string) => Record<string, string>
}> = [
  {
    prefix: '不支持的读取策略: ',
    key: 'chat.message.errorWebSearchStrategy',
    extract: (body) => ({ strategy: body.slice('不支持的读取策略: '.length).split('，')[0] }),
  },
  {
    prefix: '未能从全局设置 ',
    key: 'chat.message.errorModelConfigNotFound',
    extract: (body) => ({ keys: body.slice('未能从全局设置 '.length).split(' 中找到')[0] }),
  },
  {
    prefix: 'Agent 绑定的模型 ',
    key: 'chat.message.errorAgentModelNotFound',
    extract: (body) => ({ modelId: body.slice('Agent 绑定的模型 '.length).split(' 不存在')[0] }),
  },
]

export function parseErrorContent(content: string): ErrorContent | null {
  try {
    return JSON.parse(content) as ErrorContent
  } catch {
    return null
  }
}

/** 将后端错误文案映射为本地化提示，无法匹配时原样返回 */
export function parseErrorMessage(content: string): string {
  const parsed = parseErrorContent(content)
  const message = parsed?.message || content
  if (!message) return message

  const t = i18n.global.t

  if (message === '生成被用户取消。' || message === '生成被用户取消') {
    return t('chat.message.errorCancelled')
  }

  const UNHANDLED_PREFIX = '发生未处理的异常: '
  if (message.startsWith(UNHANDLED_PREFIX)) {
    return t('chat.message.errorUnhandled', {
      detail: message.slice(UNHANDLED_PREFIX.length),
    })
  }

  const typeMatch = message.match(ERROR_TYPE_PREFIX)
  const body = typeMatch ? message.slice(typeMatch[0].length) : message

  const exactKey = ERROR_EXACT_MAP[body]
  if (exactKey) return t(exactKey)

  for (const rule of ERROR_PREFIX_MATCHES) {
    if (body.startsWith(rule.prefix)) {
      const params = rule.extract ? rule.extract(body) : undefined
      return params ? t(rule.key, params) : t(rule.key)
    }
  }

  return message
}

export function parseErrorStackTrace(content: string): string {
  const parsed = parseErrorContent(content)
  return parsed?.stack_trace || ''
}
