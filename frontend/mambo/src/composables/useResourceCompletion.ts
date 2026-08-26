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

/** editor 实例 → 绑定的补全配置（未绑定的编辑器不触发补全） */
interface CompletionBinding {
  agentId: string
  /** 内容续写开关：仅 real backend 为 resource 的 Agent 为 true（local/ssh/api 只做路径补全） */
  contentEnabled: boolean
}
const agentByEditor = new WeakMap<editor.IStandaloneCodeEditor, CompletionBinding>()

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

// --- 候选前缀生成 ---

function generatePrefixCandidates(lineText: string): string[] {
  const candidates: string[] = [lineText]

  // 含 '/' 时：从每个 '/' 位置截取子串（如 '1. /a/b' → ['1. /a/b', '/a/b', '/b']）
  if (lineText.includes('/')) {
    for (let i = 1; i < lineText.length; i++) {
      if (lineText[i] === '/') {
        candidates.push(lineText.slice(i))
      }
    }
  }

  // 从词边界（空白、常见标点）截取子串
  const boundaryRe = /[\s.,;:!?()[\]{}'"<>]/g
  let match: RegExpExecArray | null
  while ((match = boundaryRe.exec(lineText)) !== null) {
    const idx = match.index + 1
    if (idx < lineText.length) {
      candidates.push(lineText.slice(idx))
    }
  }

  // 去重，保持从长到短的顺序
  const seen = new Set<string>()
  return candidates.filter((c) => {
    if (seen.has(c)) return false
    seen.add(c)
    return true
  })
}

// --- Completion Provider ---

const provider: languages.CompletionItemProvider = {
  provideCompletionItems: async (model, position) => {
    const monaco = monacoInstance
    if (!monaco) return { suggestions: [] }

    const editor = monaco.editor
      .getEditors()
      .find((e: editor.IStandaloneCodeEditor) => e.getModel() === model)
    const binding = editor ? agentByEditor.get(editor) : undefined
    if (!binding) return { suggestions: [] }

    const lineText = model.getValueInRange({
      startLineNumber: position.lineNumber,
      startColumn: 1,
      endLineNumber: position.lineNumber,
      endColumn: position.column,
    })
    const fullPrefix =
      lineText.length > MAX_PREFIX_LEN ? lineText.slice(lineText.length - MAX_PREFIX_LEN) : lineText

    const seq = ++requestSeq
    await debounce(DEBOUNCE_MS)
    if (seq !== requestSeq) return { suggestions: [] }

    const candidates = generatePrefixCandidates(fullPrefix)
    const { agentId, contentEnabled } = binding

    let pathResp: ResourceCompletePathResponse | null = null
    let contentResp: ResourceContentCompleteResponse | null = null
    let matchedPrefix = fullPrefix

    for (const cand of candidates) {
      const isPath = cand.includes('/')
      const [pResp, cResp] = await Promise.all([
        fetchPath(agentId, cand),
        isPath || !contentEnabled ? Promise.resolve(null) : fetchContent(agentId, cand),
      ])
      if (seq !== requestSeq) return { suggestions: [] }

      if ((pResp?.items?.length ?? 0) > 0 || (cResp?.items?.length ?? 0) > 0) {
        pathResp = pResp
        contentResp = cResp
        matchedPrefix = cand
        break
      }
    }

    const suggestions: languages.CompletionItem[] = []

    if (pathResp?.enabled) {
      const kind = monaco.languages.CompletionItemKind
      const lastSlashIdx = matchedPrefix.lastIndexOf('/')
      const rangeStartCol =
        lastSlashIdx === matchedPrefix.length - 1
          ? position.column // trailing slash: 在光标处追加
          : lastSlashIdx >= 0
            ? position.column - (matchedPrefix.length - lastSlashIdx - 1) // 替换最后一段
            : position.column - matchedPrefix.length // 无 '/' 兜底

      pathResp.items.forEach((item) => {
        const insertText = item.is_dir ? `${item.name}/` : item.name
        suggestions.push({
          label: item.name,
          kind: item.is_dir ? kind.Folder : kind.File,
          detail: item.path ? `${item.path} / ${item.name}` : item.name,
          insertText,
          filterText: matchedPrefix,
          range: {
            startLineNumber: position.lineNumber,
            startColumn: rangeStartCol,
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
          insertText: matchedPrefix + item.snippet,
          filterText: matchedPrefix,
          range: {
            startLineNumber: position.lineNumber,
            startColumn: position.column - matchedPrefix.length,
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

/** 将编辑器与补全配置绑定，确保补全 provider 已注册（全局仅注册一次），并绑定 Tab 触发。 */
export function registerResourceCompletion(
  editor: editor.IStandaloneCodeEditor,
  agentId: string,
  contentEnabled = true,
) {
  agentByEditor.set(editor, { agentId, contentEnabled })
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
