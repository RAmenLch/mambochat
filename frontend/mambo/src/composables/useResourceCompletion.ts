// composables/useResourceCompletion.ts
// Monaco 输入框的资源补全（路径补全 + 内容续写）
// 触发方式：输入时自动弹出（有候选才显示）+ Tab 键强制打开候选列表。
// 仅对通过 registerResourceCompletion 绑定 agentId 的编辑器生效；
// 未挂载 ResourceBackend 时后端返回 enabled=false，前端自然无候选。

import loader from '@monaco-editor/loader'
import type { editor, languages, IDisposable } from 'monaco-editor'
import i18n from '@/i18n'
import {
  completeResourcePath,
  completeResourceContent,
} from '@/api/resourceCompletionService'
import type {
  ResourceCompletePathResponse,
  ResourceContentCompleteResponse,
} from '@/api/types/resourceCompletionTypes'

// --- 模块级单例状态 ---

let monacoInstance: any = null
let providerRegistered = false
let providerDisposable: IDisposable | null = null

/** editor 实例 → 绑定的 agentId（未绑定的编辑器不触发补全） */
const agentByEditor = new WeakMap<editor.IStandaloneCodeEditor, string>()

/** 已完成注册（provider + Tab 绑定）的编辑器集合，保证幂等 */
const registeredEditors = new WeakSet<editor.IStandaloneCodeEditor>()

/** 防抖：击键停顿后才发请求，避免连续输入打满接口 */
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let pendingResolvers: Array<() => void> = []
let requestSeq = 0

/** 结果缓存：同一 (类型, agentId, prefix) 3 秒内直接复用 */
const cache = new Map<string, { ts: number; data: any }>()
const CACHE_TTL = 3000

const DEBOUNCE_MS = 250
/** 光标前文本过长时截断，避免无意义的大前缀请求 */
const MAX_PREFIX_LEN = 200

function debounce(ms: number): Promise<void> {
  return new Promise((resolve) => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      // 旧请求立即结束，由 seq 判断自行丢弃
      const resolvers = pendingResolvers
      pendingResolvers = []
      resolvers.forEach((r) => r())
    }
    pendingResolvers.push(resolve)
    debounceTimer = setTimeout(() => {
      const resolvers = pendingResolvers
      pendingResolvers = []
      debounceTimer = null
      resolvers.forEach((r) => r())
    }, ms)
  })
}

function getCached(key: string): any | null {
  const entry = cache.get(key)
  if (entry && Date.now() - entry.ts < CACHE_TTL) return entry.data
  return null
}

function setCached(key: string, data: any) {
  cache.set(key, { ts: Date.now(), data })
}

async function fetchPath(agentId: string, prefix: string): Promise<ResourceCompletePathResponse | null> {
  const key = `path|${agentId}|${prefix}`
  const cached = getCached(key)
  if (cached) return cached
  try {
    const data = await completeResourcePath({ agent_id: agentId, prefix })
    setCached(key, data)
    return data
  } catch {
    return null
  }
}

async function fetchContent(agentId: string, prefix: string): Promise<ResourceContentCompleteResponse | null> {
  const key = `content|${agentId}|${prefix}`
  const cached = getCached(key)
  if (cached) return cached
  try {
    const data = await completeResourceContent({ agent_id: agentId, prefix })
    setCached(key, data)
    return data
  } catch {
    return null
  }
}

// --- Completion Provider ---

const provider: languages.CompletionItemProvider = {
  provideCompletionItems: async (model, position) => {
    const monaco = monacoInstance
    if (!monaco) return { suggestions: [] }

    const editor = monaco.editor
      .getEditors()
      .find((e: editor.IStandaloneCodeEditor) => e.getModel() === model)
    const agentId = editor ? agentByEditor.get(editor) : undefined
    if (!agentId) return { suggestions: [] }

    // 光标前的整行文本作为前缀（路径补全 / 内容续写共用）
    const lineText = model.getValueInRange({
      startLineNumber: position.lineNumber,
      startColumn: 1,
      endLineNumber: position.lineNumber,
      endColumn: position.column,
    })
    const prefix =
      lineText.length > MAX_PREFIX_LEN ? lineText.slice(lineText.length - MAX_PREFIX_LEN) : lineText

    const seq = ++requestSeq
    await debounce(DEBOUNCE_MS)
    if (seq !== requestSeq) return { suggestions: [] }

    // 含 '/' 时按路径补全（此时内容续写无意义）
    const isPathInput = prefix.includes('/')
    const [pathResp, contentResp] = await Promise.all([
      fetchPath(agentId, prefix),
      isPathInput ? Promise.resolve(null) : fetchContent(agentId, prefix),
    ])
    if (seq !== requestSeq) return { suggestions: [] }

    const suggestions: languages.CompletionItem[] = []

    if (pathResp?.enabled) {
      const kind = monaco.languages.CompletionItemKind
      pathResp.items.forEach((item) => {
        const insertText = item.is_dir ? `${item.name}/` : item.name
        suggestions.push({
          label: item.name,
          kind: item.is_dir ? kind.Folder : kind.File,
          detail: item.path ? `${item.path} / ${item.name}` : item.name,
          insertText,
          // 过滤交给后端：filterText 设为输入前缀，避免被 Monaco 本地过滤误杀
          filterText: prefix,
          // 替换光标前的输入段
          range: {
            startLineNumber: position.lineNumber,
            startColumn: position.column - prefix.length,
            endLineNumber: position.lineNumber,
            endColumn: position.column,
          },
          sortText: `0_${item.name}`,
        })
      })
    }

    if (contentResp?.enabled) {
      const contentLabel = i18n.global.t('chat.input.completionContent')
      contentResp.items.forEach((item) => {
        const label = item.snippet.replace(/\s+/g, ' ').trim().slice(0, 32) || '...'
        suggestions.push({
          label,
          kind: monaco.languages.CompletionItemKind.Snippet,
          detail: item.resource_path ? `${item.resource_path} · ${contentLabel}` : contentLabel,
          // 整段替换：前缀 + 续写片段，与下方 range 保持一致
          insertText: prefix + item.snippet,
          filterText: prefix,
          // 替换光标前的输入段（保留用户输入的前缀）
          range: {
            startLineNumber: position.lineNumber,
            startColumn: position.column - prefix.length,
            endLineNumber: position.lineNumber,
            endColumn: position.column,
          },
          sortText: `1_${label}`,
        })
      })
    }

    return { suggestions }
  },
}

// --- Tab 触发 ---

function registerTabTrigger(ed: editor.IStandaloneCodeEditor) {
  ed.addAction({
    id: 'resource-completion-trigger-tab',
    label: 'Trigger Resource Completion',
    keybindings: [monacoInstance.KeyCode.Tab],
    // 建议框未打开时 Tab 才用于触发；打开后交给 Monaco 内置的“接受建议”行为
    precondition: '!suggestWidgetVisible',
    run: (e) => e.trigger('keyboard', 'editor.action.triggerSuggest', {}),
  })
}

// --- 对外 API ---

/** 将编辑器与 agentId 绑定，确保补全 provider 已注册（全局仅注册一次），并绑定 Tab 触发。 */
export function registerResourceCompletion(editor: editor.IStandaloneCodeEditor, agentId: string) {
  agentByEditor.set(editor, agentId)
  if (registeredEditors.has(editor)) return
  registeredEditors.add(editor)

  const bindTab = () => {
    if (monacoInstance) registerTabTrigger(editor)
  }

  if (providerRegistered) {
    bindTab()
    return
  }
  providerRegistered = true
  loader.init().then((monaco) => {
    monacoInstance = monaco
    providerDisposable = monaco.languages.registerCompletionItemProvider('markdown', provider)
    bindTab()
  })
}

/** 解绑编辑器（provider 本体保持注册，回调内按 WeakMap 判断后直接返回空）。 */
export function unregisterResourceCompletion(editor: editor.IStandaloneCodeEditor) {
  agentByEditor.delete(editor)
}

export function useResourceCompletion() {
  return {
    registerResourceCompletion,
    unregisterResourceCompletion,
  }
}
