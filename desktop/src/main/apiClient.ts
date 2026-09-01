/**
 * API Client Manager — WebSocket clients that connect to a remote MamboChat
 * server and register the local filesystem as API backends.
 *
 * Supports multiple simultaneous clients: each client is an independent
 * WebSocket connection with its own backend ID, API key and root directory.
 * Runs entirely in the Electron main process using Node.js built-in WebSocket.
 * No Python subprocess needed.
 */

import { BrowserWindow } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import * as os from 'os'
import * as crypto from 'crypto'
import { execFile as execFileCb, spawn, type ChildProcess } from 'child_process'
import { promisify, TextDecoder } from 'util'
import http from 'http'
import https from 'https'
import type { AppConfig } from './config'
import { AppConfigManager } from './config'
import log from './log'
import fg from 'fast-glob'

const execFileAsync = promisify(execFileCb)

/**
 * Directories skipped by default during recursive scans (grep / glob / tree)
 * to avoid freezing the main process on huge dependency/vendor trees.
 * Explicitly requested sub-paths under these directories are still reachable.
 */
const DEFAULT_IGNORE_DIRS = [
  'node_modules', '.venv', 'venv', 'dist', '.git', '__pycache__',
  '.idea', '.cache', '.next', 'build', 'release', '.mypy_cache', '.pytest_cache',
]

/** Hard cap on files visited by a single recursive scan (anti-freeze guard). */
const MAX_WALK_FILES = 100000

/** Convert http:// to ws:// and https:// to wss:// */
function httpToWs(url: string): string {
  const clean = url.replace(/\/+$/, '')
  if (clean.startsWith('https://')) return clean.replace('https://', 'wss://')
  if (clean.startsWith('http://')) return clean.replace('http://', 'ws://')
  return clean
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiClientStatus {
  running: boolean
  connected: boolean
  connecting: boolean
  backendId?: string
  name?: string
  rootDir?: string
  error?: string
}

interface ClientCommand {
  type: 'command'
  request_id: string
  method: string
  params: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// ApiClientConnection — one WebSocket connection (one backend on the server)
// ---------------------------------------------------------------------------

class ApiClientConnection {
  readonly backendId: string
  readonly apiKey: string
  rootDir: string
  name: string

  private ws: WebSocket | null = null
  private stopping = false
  private _connected = false
  private _connecting = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectDelay = 5000
  private lastError: string | null = null
  private editWhitelist: string[] = []
  private editBlacklist: string[] = []

  private readonly FILE_TYPE_MAP: Record<string, string> = {
    '.png': 'image', '.jpeg': 'image', '.jpg': 'image', '.webp': 'image',
    '.gif': 'image', '.heic': 'image', '.heif': 'image',
    '.mp4': 'video', '.mpeg': 'video', '.mov': 'video', '.avi': 'video',
    '.flv': 'video', '.mpg': 'video', '.webm': 'video', '.wmv': 'video', '.3gpp': 'video',
    '.wav': 'audio', '.mp3': 'audio', '.aiff': 'audio', '.aac': 'audio',
    '.ogg': 'audio', '.flac': 'audio',
    '.pdf': 'file', '.ppt': 'file', '.pptx': 'file',
  }

  private readonly MIME_MAP: Record<string, string> = {
    '.png': 'image/png', '.jpeg': 'image/jpeg', '.jpg': 'image/jpeg',
    '.webp': 'image/webp', '.gif': 'image/gif', '.heic': 'image/heic', '.heif': 'image/heif',
    '.mp4': 'video/mp4', '.mpeg': 'video/mpeg', '.mov': 'video/quicktime',
    '.avi': 'video/x-msvideo', '.flv': 'video/x-flv', '.mpg': 'video/mpeg',
    '.webm': 'video/webm', '.wmv': 'video/x-ms-wmv', '.3gpp': 'video/3gpp',
    '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.aiff': 'audio/aiff',
    '.aac': 'audio/aac', '.ogg': 'audio/ogg', '.flac': 'audio/flac',
    '.pdf': 'application/pdf', '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  }

  constructor(backendId: string, apiKey: string, rootDir: string, name = '') {
    this.backendId = backendId
    this.apiKey = apiKey
    this.rootDir = rootDir || os.homedir()
    this.name = name
  }

  /** Update mutable config (root dir / label) before (re)connecting. */
  configure(rootDir: string, name = ''): void {
    this.rootDir = rootDir || os.homedir()
    this.name = name
  }

  getStatus(): ApiClientStatus {
    return {
      running: !!this.ws || this._connecting,
      connected: this._connected,
      connecting: this._connecting,
      backendId: this.backendId,
      name: this.name || undefined,
      rootDir: this.rootDir || undefined,
      error: this._connected ? undefined : (this._connecting ? undefined : (this.lastError || 'Not connected')),
    }
  }

  /** Connect the WebSocket to the remote server. */
  async connect(serverUrl: string): Promise<void> {
    if (this.ws && (this._connected || this._connecting)) {
      return
    }

    this.stopping = false
    this.lastError = null

    const wsUrl = httpToWs(serverUrl)
    const fullUrl = `${wsUrl}/api/api-client/ws/${this.backendId}`

    log.info(`[ApiClient] Connecting to ${fullUrl} ...`)
    this._connecting = true
    this.broadcastStatus()

    try {
      await this.openSocket(fullUrl, serverUrl)
      this.reconnectDelay = 5000
    } catch (err) {
      this._connecting = false
      this.lastError = String(err)
      this.broadcastStatus()
      if (!this.stopping) {
        this.scheduleReconnect(serverUrl)
      }
      throw err
    }
  }

  /** Stop this client. */
  async disconnect(): Promise<void> {
    this.stopping = true
    this._connecting = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      try { this.ws.close() } catch { /* ignore */ }
      this.ws = null
    }
    this._connected = false
    this.broadcastStatus()
    log.info(`[ApiClient] Stopped backend=${this.backendId}`)
  }

  private openSocket(url: string, serverUrl: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url)
      this.ws = ws
      let authDone = false

      const timeout = setTimeout(() => {
        if (!authDone) {
          try { ws.close() } catch { /* ignore */ }
          reject(new Error('WebSocket connection timed out'))
        }
      }, 15000)

      ws.onopen = () => {
        log.info(`[ApiClient] WebSocket opened (backend=${this.backendId}), sending auth`)
        ws.send(JSON.stringify({ type: 'auth', api_key: this.apiKey }))
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string)
          const msgType = msg.type

          if (msgType === 'auth_ok') {
            authDone = true
            clearTimeout(timeout)
            this._connecting = false
            this._connected = true
            this.reconnectDelay = 5000
            log.info(`[ApiClient] Authenticated successfully (backend=${this.backendId})`)

            // Send client info
            ws.send(JSON.stringify({
              type: 'register_info',
              info: {
                root_dir: this.rootDir,
                hostname: os.hostname(),
                platform: os.platform(),
                pid: process.pid,
              },
            }))

            this.broadcastStatus()
            resolve()
          } else if (msgType === 'welcome') {
            log.info(`[ApiClient] Server (backend=${this.backendId}): ${msg.message || 'welcome'}`)
          } else if (msgType === 'command') {
            this.handleCommand(ws, msg as ClientCommand)
          } else {
            log.warn(`[ApiClient] Unknown message type: ${msgType}`)
          }
        } catch (err) {
          log.error('[ApiClient] Error parsing message:', err)
        }
      }

      ws.onerror = (event) => {
        log.error(`[ApiClient] WebSocket error (backend=${this.backendId}):`, event)
        clearTimeout(timeout)
        if (!authDone) {
          this._connecting = false
          this.ws = null
          reject(new Error('WebSocket connection failed'))
        }
      }

      ws.onclose = (event) => {
        log.info(`[ApiClient] WebSocket closed (backend=${this.backendId}, code=${event.code}, reason=${event.reason})`)
        clearTimeout(timeout)
        const wasConnected = this._connected
        this.ws = null
        this._connected = false
        this._connecting = false
        this.broadcastStatus()

        if (!authDone && !wasConnected) {
          reject(new Error(`WebSocket closed: code=${event.code}`))
        }

        // Auto-reconnect if connection drops after being established
        if (wasConnected && !this.stopping) {
          this.scheduleReconnect(serverUrl)
        }
      }
    })
  }

  private scheduleReconnect(serverUrl: string): void {
    if (this.stopping || this.reconnectTimer) return

    log.info(`[ApiClient] Reconnecting backend=${this.backendId} in ${this.reconnectDelay / 1000}s ...`)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (!this.stopping) {
        this.connect(serverUrl).catch(() => {
          this.reconnectDelay = Math.min(this.reconnectDelay * 2, 60000)
        })
      }
    }, this.reconnectDelay)
  }

  private broadcastStatus(): void {
    // Delegate to the manager-level broadcast (reads config for full list).
    ApiClientManager.getInstance().broadcastStatus()
  }

  // ---------------------------------------------------------------------------
  // Command dispatch
  // ---------------------------------------------------------------------------

  private async handleCommand(ws: WebSocket, cmd: ClientCommand): Promise<void> {
    const { request_id, method, params } = cmd
    log.info(`[ApiClient] Command received: ${method} request_id=${request_id}`, params)

    try {
      let result: unknown
      switch (method) {
        case 'tree':          result = await this.handleTree(params); break
        case 'ls':            result = await this.handleLs(params); break
        case 'read_file':     result = await this.handleReadFile(params); break
        case 'write_file':    result = await this.handleWriteFile(params); break
        case 'edit_file':     result = await this.handleEditFile(params); break
        case 'grep_files':    result = await this.handleGrepFiles(params); break
        case 'glob_files':    result = await this.handleGlobFiles(params); break
        case 'upload_files':  result = await this.handleUploadFiles(params); break
        case 'download_files':result = await this.handleDownloadFiles(params); break
        case 'execute':       result = await this.handleExecute(params, request_id); break
        case 'abort':         this.handleAbort(params); return  // 单向通知：不回复响应
        case 'delete_file':   result = await this.handleDelete(params); break
        default:              result = { error: `Unknown method: ${method}`, error_code: 'UNKNOWN_METHOD' }
      }
      log.info(`[ApiClient] Command done: ${method} request_id=${request_id}, sending response`)
      ws.send(JSON.stringify({ type: 'response', request_id, result }))
    } catch (err) {
      log.error(`[ApiClient] Command error: ${method}`, err)
      ws.send(JSON.stringify({
        type: 'error',
        request_id,
        message: String(err),
      }))
    }
  }

  // ---------------------------------------------------------------------------
  // File operation handlers
  // ---------------------------------------------------------------------------

  private async handleTree(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const vpath = (params.path as string) || '/workspace'
    const depth = (params.depth as number) ?? 3
    const ignoreDirs: string[] = (params.ignore_dirs as string[]) ?? []
    // Merge explicit ignore_dirs with anti-freeze defaults
    const mergedIgnore = [...new Set([...ignoreDirs, ...DEFAULT_IGNORE_DIRS])]

    if (depth < 1) {
      return { tree: `Invalid depth value: ${depth}. Depth must be a positive integer (>= 1).` }
    }

    // Root path "/" (or any all-slash path) — aligned with VirtualPath's rstrip('/') == '' check
    if (vpath.replace(/\/+$/, '') === '') {
      return { tree: `[PATH_IS_ROOT] 路径不能是根目录 '/'；请使用子目录如 '/workspace'`, error_code: 'PATH_IS_ROOT' }
    }

    // Outside workspace
    if (vpath !== '/workspace' && !vpath.startsWith('/workspace/')) {
      return { tree: `[OUTSIDE_WORKSPACE] 路径超出工作区，所有文件操作必须在 '/workspace/' 下进行`, error_code: 'OUTSIDE_WORKSPACE' }
    }

    const base = this.resolvePath(vpath)

    // Path does not exist
    if (!fs.existsSync(base)) {
      return { tree: `Path '${vpath}' not found.`, error_code: 'NOT_FOUND' }
    }
    // Path is a file, not a directory
    if (!fs.statSync(base).isDirectory()) {
      return { tree: `Path '${vpath}' is not a directory.`, error_code: 'NOT_DIR' }
    }

    interface TreeEntry { name: string; depth: number; marker: string }
    const entries: TreeEntry[] = []
    let walkCount = 0

    const walk = async (dir: string, currentDepth: number): Promise<void> => {
      if (currentDepth > depth) return
      let dirents: fs.Dirent[]
      try { dirents = await fs.promises.readdir(dir, { withFileTypes: true }) }
      catch { return }

      // Anti-freeze: let the event loop breathe every 128 entries
      if (++walkCount % 128 === 0) {
        await new Promise<void>(resolve => setImmediate(resolve))
      }

      // Directories first, then files (case-insensitive sort)
      dirents.sort((a, b) => {
        if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
      })

      for (const d of dirents) {
        if (mergedIgnore.includes(d.name)) {
          entries.push({ name: d.name + '/', depth: currentDepth, marker: 'ignore' })
          continue
        }
        if (d.isDirectory()) {
          const full = path.join(dir, d.name)
          let hasChildren = false
          try {
            const sub = await fs.promises.readdir(full, { withFileTypes: true })
            hasChildren = sub.length > 0
          } catch { /* ignore */ }
          if (currentDepth + 1 > depth) {
            entries.push({
              name: d.name + '/',
              depth: currentDepth,
              marker: hasChildren ? 'depth_exceeded' : 'empty',
            })
          } else if (!hasChildren) {
            entries.push({ name: d.name + '/', depth: currentDepth, marker: 'empty' })
          } else {
            entries.push({ name: d.name + '/', depth: currentDepth, marker: '' })
            await walk(full, currentDepth + 1)
          }
        } else {
          let sizeStr = ''
          try {
            const st = await fs.promises.stat(path.join(dir, d.name))
            sizeStr = ` (${this.formatSize(st.size)})`
          } catch { /* ignore */ }
          entries.push({ name: d.name + sizeStr, depth: currentDepth, marker: '' })
        }
      }
    }

    await walk(base, 1)

    if (entries.length === 0) {
      return { tree: `No files found in ${vpath}` }
    }

    // Format with tree connectors
    const markerSuffix: Record<string, string> = {
      empty: '/(empty)',
      ignore: '/(ignore)',
      depth_exceeded: '/(...)',
    }

    const lines = [vpath]
    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i]
      const suffix = markerSuffix[entry.marker] || ''
      let display = suffix ? entry.name.replace(/\/+$/, '') + suffix : entry.name

      // Determine connector: look ahead for more siblings at same depth
      let hasMoreSiblings = false
      for (let j = i + 1; j < entries.length; j++) {
        if (entries[j].depth < entry.depth) break
        if (entries[j].depth === entry.depth) { hasMoreSiblings = true; break }
      }
      const connector = hasMoreSiblings ? '├── ' : '└── '

      // Build prefix: for each parent depth level, check if active content remains
      let prefix = ''
      for (let level = 1; level < entry.depth; level++) {
        let active = false
        for (let j = i + 1; j < entries.length; j++) {
          if (entries[j].depth < level) break
          if (entries[j].depth === level) { active = true; break }
        }
        prefix += active ? '│   ' : '    '
      }
      lines.push(prefix + connector + display)
    }

    let result = lines.join('\n')
    if (result.length > 16000) {
      result = result.slice(0, 16000) + '\n... (tree truncated)'
    }
    return { tree: result }
  }

  private formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  private async handleLs(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const vpath = (params.path as string) || '/workspace'
    const physical = this.resolvePath(vpath)

    if (!fs.existsSync(physical)) {
      return { error: `Path not found: ${vpath}`, error_code: 'NOT_FOUND' }
    }
    if (!fs.statSync(physical).isDirectory()) {
      return { error: `Not a directory: ${vpath}`, error_code: 'NOT_DIR' }
    }

    const results: object[] = []
    try {
      const entries = (await fs.promises.readdir(physical)).sort()
      for (const entry of entries) {
        const full = path.join(physical, entry)
        let stat: fs.Stats
        try { stat = await fs.promises.stat(full) } catch { continue }
        const isDir = stat.isDirectory()
        const vp = (vpath.endsWith('/') ? vpath : vpath + '/') + entry
        results.push({
          path: vp,
          is_dir: isDir,
          size: stat.size,
          modified_at: stat.mtime.toISOString(),
        })
      }
    } catch { /* permission error, return empty */ }
    return { items: results }
  }

  private async handleReadFile(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const vpath = (params.path as string) || '/workspace'
    const offset = (params.offset as number) || 0
    const limit = (params.limit != null) ? (params.limit as number) : null
    const includeLineNumbers = (params.include_line_numbers as boolean) || false
    const physical = this.resolvePath(vpath)

    if (offset < 0) {
      return { error: `offset must be non-negative, got ${offset}`, error_code: 'INVALID' }
    }
    if (limit != null && limit < 1) {
      return { error: `limit must be >= 1, got ${limit}`, error_code: 'INVALID' }
    }

    log.info(`[ApiClient] handleReadFile: vpath=${vpath} physical=${physical} offset=${offset} limit=${limit}`)

    if (!fs.existsSync(physical)) {
      log.warn(`[ApiClient] handleReadFile: file not found at ${physical}`)
      return { error: `文件不存在`, error_code: 'NOT_FOUND' }
    }
    if (fs.statSync(physical).isDirectory()) {
      return { error: `目标是目录`, error_code: 'IS_DIR' }
    }

    const ext = path.extname(physical).toLowerCase()
    const fileType = this.FILE_TYPE_MAP[ext] || 'text'

    if (fileType !== 'text') {
      // Binary / multimedia file: read as base64
      try {
        const raw = await fs.promises.readFile(physical)
        const b64 = raw.toString('base64')
        const mime = this.MIME_MAP[ext] || 'application/octet-stream'
        log.info(`[ApiClient] handleReadFile: binary file type=${fileType} mime=${mime} size=${raw.length}`)
        return {
          content: b64,
          encoding: 'base64',
          file_type: fileType,
          mime_type: mime,
          total_lines: 1,
        }
      } catch (e) {
        return { error: `Failed to read binary file '${vpath}': ${e}`, error_code: 'IO_ERROR' }
      }
    }

    // Text file — probe before decoding
    let content: string
    let buf: Buffer
    try {
      buf = await fs.promises.readFile(physical)
    } catch {
      log.warn(`[ApiClient] handleReadFile: failed to read ${physical}`)
      return { error: `Failed to read file '${vpath}'`, error_code: 'IO_ERROR' }
    }

    // Null-byte probe: text files virtually never contain \x00
    const probeEnd = Math.min(buf.length, 4096)
    for (let i = 0; i < probeEnd; i++) {
      if (buf[i] === 0) {
        log.info(`[ApiClient] handleReadFile: null byte detected, not a text file`)
        return { error: `File '${vpath}' is not a valid UTF-8 text file.`, error_code: 'INVALID' }
      }
    }

    // Strict UTF-8 decode — fail on first invalid byte
    try {
      content = new TextDecoder('utf-8', { fatal: true }).decode(buf)
    } catch {
      log.info(`[ApiClient] handleReadFile: invalid UTF-8, not a text file`)
      return { error: `File '${vpath}' is not a valid UTF-8 text file.`, error_code: 'INVALID' }
    }
    log.info(`[ApiClient] handleReadFile: read ${content.length} chars`)

    const lines = this.splitLines(content)
    const start = offset
    const end = (limit != null) ? Math.min(start + limit, lines.length) : lines.length

    if (lines.length > 0 && start >= lines.length) {
      return { error: `偏移量 ${offset} 超过文件长度 (${lines.length} 行)`, error_code: 'INVALID' }
    }

    const selected = lines.slice(start, end)
    const resultLines = includeLineNumbers
      ? this.formatNumberedLines(selected, start + 1)
      : selected

    // 缓存友好：限制单次 read 返回的字符总量，避免大文件整份注入上下文
    const MAX_READ_CHARS = 10000
    content = selected.join('\n')
    let truncated = false
    if (content.length > MAX_READ_CHARS) {
      content = content.slice(0, MAX_READ_CHARS) + '\n... (content truncated)'
      truncated = true
    }

    return {
      content,
      lines: resultLines,
      total_lines: lines.length,
      offset: start,
      limit,
      truncated,
      encoding: 'utf-8',
      file_type: 'text',
      mime_type: '',
    }
  }

  private async handleWriteFile(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const vpath = (params.path as string) || ''
    const content = (params.content as string) || ''
    const overwrite = (params.overwrite as boolean) || false

    let physical: string
    try {
      this.checkEditPermission(vpath)
      physical = this.resolvePath(vpath)
    } catch (e) {
      const msg = String(e)
      if (msg.includes('Edit denied')) {
        return { error: msg, error_code: 'EDIT_NOT_ALLOWED' }
      }
      if (msg.includes('Path traversal')) {
        return { error: msg, error_code: 'PATH_TRAVERSAL' }
      }
      return { error: msg, error_code: 'IO_ERROR' }
    }

    if (fs.existsSync(physical!) && fs.statSync(physical!).isDirectory()) {
      return { error: `Path is a directory, not a file: ${vpath}`, error_code: 'IS_DIR' }
    }

    if (!overwrite && fs.existsSync(physical!)) {
      return { error: `File already exists: ${vpath}`, error_code: 'ALREADY_EXISTS' }
    }

    if (overwrite && fs.existsSync(physical!) && fs.statSync(physical!).isFile()) {
      try {
        const existingBuf = await fs.promises.readFile(physical!)
        const existingProbeEnd = Math.min(existingBuf.length, 4096)
        for (let i = 0; i < existingProbeEnd; i++) {
          if (existingBuf[i] === 0) {
            return { error: `Cannot write to binary file: ${vpath}`, error_code: 'INVALID' }
          }
        }
        new TextDecoder('utf-8', { fatal: true }).decode(existingBuf)
      } catch {
        return { error: `Cannot write to binary file: ${vpath}`, error_code: 'INVALID' }
      }
    }

    try {
      fs.mkdirSync(path.dirname(physical!), { recursive: true })
      await fs.promises.writeFile(physical!, content, 'utf-8')
      return { path: vpath, success: true }
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }
  }

  private async handleEditFile(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const vpath = (params.path as string) || ''
    const oldStr = (params.old_string as string) || ''
    const newStr = (params.new_string as string) || ''
    const replaceAll = (params.replace_all as boolean) || false

    if (!oldStr) {
      return { error: 'old_string cannot be empty', error_code: 'INVALID' }
    }

    let physical: string
    try {
      this.checkEditPermission(vpath)
      physical = this.resolvePath(vpath)
    } catch (e) {
      const msg = String(e)
      if (msg.includes('Edit denied')) {
        return { error: msg, error_code: 'EDIT_NOT_ALLOWED' }
      }
      if (msg.includes('Path traversal')) {
        return { error: msg, error_code: 'PATH_TRAVERSAL' }
      }
      return { error: msg, error_code: 'IO_ERROR' }
    }

    if (!fs.existsSync(physical!)) {
      return { error: `File not found: ${vpath}. To create a new file, use write().`, error_code: 'NOT_FOUND' }
    }
    if (!fs.statSync(physical!).isFile()) {
      return { error: `目标是目录，无法编辑`, error_code: 'IS_DIR' }
    }

    let editBuf: Buffer
    try {
      editBuf = await fs.promises.readFile(physical!)
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }

    const editProbeEnd = Math.min(editBuf.length, 4096)
    for (let i = 0; i < editProbeEnd; i++) {
      if (editBuf[i] === 0) {
        return { error: `Cannot edit binary file: ${vpath}`, error_code: 'INVALID' }
      }
    }

    let content: string
    try {
      content = new TextDecoder('utf-8', { fatal: true }).decode(editBuf)
    } catch {
      return { error: `Cannot edit binary file: ${vpath}`, error_code: 'INVALID' }
    }

    const normalizedOld = oldStr.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const normalizedNew = newStr.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const normalizedContent = content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

    const occurrences = normalizedContent.split(normalizedOld).length - 1

    if (occurrences === 0) {
      return { error: 'old_string not found in file', error_code: 'OLD_STR_NOT_FOUND' }
    }

    if (occurrences > 1 && !replaceAll) {
      return { error: `old_string appears ${occurrences} times. Use replace_all=True to replace all occurrences, or provide more context to match a single one.`, error_code: 'MULTI_OCCURRENCES' }
    }

    const newContent = replaceAll
      ? normalizedContent.replaceAll(normalizedOld, normalizedNew)
      : normalizedContent.slice(0, normalizedContent.indexOf(normalizedOld)) + normalizedNew + normalizedContent.slice(normalizedContent.indexOf(normalizedOld) + normalizedOld.length)

    try {
      await fs.promises.writeFile(physical!, newContent, 'utf-8')
      return { path: vpath, occurrences, success: true }
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }
  }

  private async handleGrepFiles(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const pattern = (params.pattern as string) || ''
    const vpath = (params.path as string) || '/workspace'
    const glob = (params.glob as string) || undefined
    const regex = (params.regex as boolean) ?? true
    const offset = (params.offset as number) ?? 0
    const limit = (params.limit as number) ?? undefined
    const ignoreDirs: string[] = (params.ignore_dirs as string[]) ?? []
    // Merge explicit ignore_dirs with anti-freeze defaults (dedup, explicit first)
    const mergedIgnore = [...new Set([...ignoreDirs, ...DEFAULT_IGNORE_DIRS])]

    // Empty pattern is invalid
    if (!pattern) {
      return { error: `搜索模式不能为空`, error_code: 'INVALID' }
    }

    // Root path "/" (or any all-slash path) — aligned with VirtualPath's rstrip('/') == '' check
    if (vpath.replace(/\/+$/, '') === '') {
      return { error: `路径不能是根目录 '/'；请使用子目录如 '/workspace'`, error_code: 'PATH_IS_ROOT' }
    }

    const base = this.resolvePath(vpath)

    // Path does not exist
    if (!fs.existsSync(base)) {
      return { error: `路径不存在`, error_code: 'NOT_FOUND' }
    }

    let testFn: (line: string) => boolean
    if (regex) {
      try {
        const re = new RegExp(pattern)
        testFn = (line: string) => re.test(line)
      } catch {
        return { error: `Invalid regex pattern: ${pattern}`, error_code: 'INVALID' }
      }
    } else {
      testFn = (line: string) => line.includes(pattern)
    }

    log.info(`[ApiClient] handleGrepFiles: vpath=${vpath} physical=${base} pattern=${pattern} regex=${regex} glob=${glob}`)

    const isDir = fs.existsSync(base) && fs.statSync(base).isDirectory()
    const MAX_GREP_MATCHES = 200

    // 1) Try ripgrep (fast native search)
    const rgMatches = await this._ripgrepGrep(pattern, base, isDir ? glob : undefined, regex, mergedIgnore)
    if (rgMatches !== null) {
      // Post-filter rg output: --glob uses gitignore semantics (not POSIX),
      // and ignore_dirs must be applied uniformly across both search paths.
      const filtered: object[] = []
      for (const m of rgMatches) {
        const mpath = (m as { path: string }).path
        // ignore_dirs: parent-segment check (mirrors the backends' _in_ignored_dir)
        if (mergedIgnore.length > 0) {
          const rel = mpath.startsWith('/workspace/')
            ? mpath.slice('/workspace/'.length)
            : mpath.replace(/^\//, '')
          const parentSegs = rel.split('/').slice(0, -1)
          if (parentSegs.some(seg => mergedIgnore.includes(seg))) continue
        }
        // POSIX glob post-filter
        if (glob && isDir) {
          const relPath = mpath.startsWith(vpath)
            ? mpath.slice(vpath.length).replace(/^\//, '')
            : mpath
          if (!this.fnmatch(relPath, glob)) continue
        }
        filtered.push(m)
      }
      // Sort by (path, line) — mirrors local.py's
      // matches.sort(key=lambda m: (str(m.path), m.line))
      filtered.sort((a, b) => {
        const pa = (a as { path: string }).path
        const pb = (b as { path: string }).path
        if (pa !== pb) return pa < pb ? -1 : 1
        return (a as { line: number }).line - (b as { line: number }).line
      })
      const effectiveLimit = limit !== undefined ? Math.min(limit, MAX_GREP_MATCHES) : MAX_GREP_MATCHES
      const sliced = offset > 0 ? filtered.slice(offset) : filtered
      const limited = limit !== undefined ? sliced.slice(0, limit) : sliced
      return {
        matches: limited,
        truncated: (offset + effectiveLimit) < filtered.length,
        total: filtered.length,
      }
    }

    // 2) Node.js fallback
    const matches: object[] = []
    const maxFileSize = 10 * 1024 * 1024
    let scannedCount = 0

    const searchFile = async (filePath: string, displayPath: string): Promise<void> => {
      if (matches.length >= MAX_GREP_MATCHES) return
      if (glob) {
        const relPath = displayPath.startsWith(vpath)
          ? displayPath.slice(vpath.length).replace(/^\//, '')
          : displayPath
        if (!this.fnmatch(relPath, glob)) return
      }
      try {
        const stat = await fs.promises.stat(filePath)
        if (stat.size > maxFileSize) return
        const content = await fs.promises.readFile(filePath, 'utf-8')
        const lines = content.split('\n')
        for (let i = 0; i < lines.length; i++) {
          if (matches.length >= MAX_GREP_MATCHES) break
          if (!testFn(lines[i])) continue
          matches.push({
            path: displayPath,
            line: i + 1,
            text: lines[i],
          })
        }
      } catch { /* skip unreadable files */ }
    }

    if (fs.existsSync(base) && fs.statSync(base).isFile()) {
      const displayPath = '/workspace/' + path.relative(this.rootDir, base).replace(/\\/g, '/')
      await searchFile(base, displayPath)
    } else if (fs.existsSync(base) && fs.statSync(base).isDirectory()) {
      for await (const [fp, isDir] of this.walkDir(base, -1, 1, mergedIgnore)) {
        if (isDir) continue
        // Anti-freeze: breathe every 128 files during the sync-heavy fallback
        if (++scannedCount % 128 === 0) {
          await new Promise<void>(resolve => setImmediate(resolve))
        }
        const relPath = '/workspace/' + path.relative(this.rootDir, fp).replace(/\\/g, '/')
        await searchFile(fp, relPath)
      }
    }

    log.info(`[ApiClient] handleGrepFiles: found ${matches.length} matches`)
    const total = matches.length
    const effectiveLimit = limit !== undefined ? Math.min(limit, MAX_GREP_MATCHES) : MAX_GREP_MATCHES
    const sliced = offset > 0 ? matches.slice(offset) : matches
    const limited = limit !== undefined ? sliced.slice(0, limit) : sliced
    const truncated = (offset + effectiveLimit) < total || total >= MAX_GREP_MATCHES
    return { matches: limited, truncated, total }
  }

  private async handleGlobFiles(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const pattern = (params.pattern as string) || ''
    const vpath = (params.path as string) || '/workspace'

    // 空 pattern 直接拒绝（对齐 local.py 与 handleGrepFiles：INVALID，而非默认 '*' 返回根目录）
    if (!pattern) {
      return { error: `搜索模式不能为空`, error_code: 'INVALID' }
    }

    const base = this.resolvePath(vpath)

    if (!fs.existsSync(base)) {
      return { error: `Path not found: ${vpath}`, error_code: 'NOT_FOUND' }
    }
    if (!fs.statSync(base).isDirectory()) {
      return { error: `Not a directory: ${vpath}`, error_code: 'NOT_DIR' }
    }

    const results: object[] = []
    const effectivePattern = pattern.replace(/^\//, '')

    // fast-glob：与 pathlib.Path.glob() 语义对齐（本地后端 local.py 即为 pathlib 实现）。
    //  - dot:true        使 * 匹配隐藏项（pathlib 的 fnmatch 无点文件特判）
    //  - onlyFiles:false 目录也作为匹配结果返回
    //  - ignore          剪枝巨型依赖/虚拟目录（对应原 walkDir 的 DEFAULT_IGNORE_DIRS 防冻结剪枝）
    const entries = await fg(effectivePattern, {
      cwd: base,
      onlyFiles: false,
      dot: true,
      unique: true,
      followSymbolicLinks: false,
      suppressErrors: true,
      ignore: DEFAULT_IGNORE_DIRS.flatMap(d => [`**/${d}`, `**/${d}/**`]),
    })

    // pathlib 桥接：末尾 '**' 只匹配目录（fast-glob 的 '**' 是 globstar、含文件）；
    // 裸 '**' 还额外包含基准目录自身（pathlib 返回 '.'）。
    let rels = entries.map(e => e.split('\\').join('/'))
    const dirOnly = effectivePattern === '**' || effectivePattern.endsWith('/**')
    if (dirOnly) {
      rels = rels.filter(r => {
        try { return fs.statSync(path.join(base, r)).isDirectory() } catch { return false }
      })
    }
    if (effectivePattern === '**') {
      rels = ['.', ...rels]
    }

    for (const rel of rels) {
      if (results.length >= MAX_WALK_FILES) break
      try {
        const physical = path.join(base, rel)
        const stat = await fs.promises.stat(physical)
        const isDir = stat.isDirectory()
        const vp = '/workspace/' + path.relative(this.rootDir, physical).replace(/\\/g, '/')
        results.push({
          path: vp,
          is_dir: isDir,
          size: isDir ? 0 : stat.size,
          modified_at: stat.mtime.toISOString(),
        })
      } catch { /* skip unreadable entries */ }
    }

    results.sort((a: any, b: any) => a.path.localeCompare(b.path))
    return { items: results }
  }

  private async handleUploadFiles(params: Record<string, unknown>): Promise<{ results: object[] }> {
    const files = (params.files as Array<{ path: string; content_b64: string }>) || []
    const results: object[] = []

    for (const item of files) {
      try {
        this.checkEditPermission(item.path)
        const physical = this.resolvePath(item.path)
        const content = Buffer.from(item.content_b64, 'base64')
        await fs.promises.mkdir(path.dirname(physical), { recursive: true })
        await fs.promises.writeFile(physical, content)
        results.push({ path: item.path, error: null })
      } catch (e) {
        results.push({ path: item.path, error: String(e) })
      }
    }
    return { results }
  }

  private async handleDownloadFiles(params: Record<string, unknown>): Promise<{ results: object[] }> {
    const paths = (params.paths as string[]) || []
    const results: object[] = []

    for (const vpath of paths) {
      try {
        const physical = this.resolvePath(vpath)
        if (!fs.existsSync(physical) || !fs.statSync(physical).isFile()) {
          results.push({ path: vpath, error: 'file_not_found' })
          continue
        }
        const content = await fs.promises.readFile(physical)
        results.push({
          path: vpath,
          content_b64: content.toString('base64'),
          error: null,
        })
      } catch (e) {
        results.push({ path: vpath, error: String(e) })
      }
    }
    return { results }
  }

  private runningExecs = new Map<string, ChildProcess>()

  /** Kill the whole process tree rooted at *child* (not just the shell wrapper):
   *  - Windows: taskkill /T /F terminates cmd.exe and all descendants.
   *  - POSIX: detached:true makes the shell a process-group leader, so a
   *    negative pid kills the entire group (shell + children).
   */
  private killProcessTree(child: ChildProcess): void {
    if (!child.pid) return
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' })
      } else {
        process.kill(-child.pid, 'SIGKILL')
      }
    } catch {
      // Process already exited — nothing to kill.
    }
  }

  /** Abort a running execute command (single-direction notification). */
  private handleAbort(params: Record<string, unknown>): void {
    const requestId = (params.request_id as string) || ''
    const child = this.runningExecs.get(requestId)
    if (!child) {
      log.info(`[ApiClient] Abort ignored: no running exec for request_id=${requestId}`)
      return
    }
    log.info(`[ApiClient] Aborting exec request_id=${requestId} pid=${child.pid}`)
    this.killProcessTree(child)
  }

  private async handleExecute(params: Record<string, unknown>, requestId: string): Promise<Record<string, unknown>> {
    const command = (params.command as string) || ''
    // The server sends the timeout in SECONDS (aligned with the Python backends'
    // subprocess.run semantics), but Node's timer is in MILLISECONDS — convert,
    // otherwise a 150s timeout becomes 150ms and fast commands are killed randomly.
    const timeout = (params.timeout as number) || 120
    const timeoutMs = timeout * 1000
    const maxBuffer = 100 * 1024 * 1024

    // Decode raw bytes with UTF-8 first: modern CLIs emit UTF-8 by default,
    // and UTF-8 strict decoding rejects most non-UTF-8 byte streams.  GBK
    // must not be tried first — it leniently "decodes" most UTF-8 bytes into
    // mojibake without raising, so the UTF-8 fallback would never trigger.
    // TextDecoder('gbk') requires full-icu, which Electron ships with.
    const decode = (buf: Buffer): string => {
      try {
        return new TextDecoder('utf-8', { fatal: true }).decode(buf).replace(/\r\n/g, '\n')
      } catch {
        return new TextDecoder(process.platform === 'win32' ? 'gbk' : 'utf-8')
          .decode(buf).replace(/\r\n/g, '\n')
      }
    }

    return await new Promise<Record<string, unknown>>((resolve) => {
      let stdout = Buffer.alloc(0)
      let stderr = Buffer.alloc(0)
      let timedOut = false
      let truncated = false

      // On Windows, use cmd.exe /d /s /c "<command>": the /s flag strips only
      // the outermost quotes, so the command string reaches cmd.exe verbatim
      // (inner quotes survive, mirrors LocalBackend's shell=True). execFile
      // would rebuild the command line via libuv argv quoting, escaping " as
      // \" — cmd.exe has no backslash escaping, so quoted arguments (e.g.
      // findstr "a b c") get mangled. POSIX keeps the list form: execve
      // passes argv directly, no escaping. detached:true makes the child a
      // process-group leader (POSIX setsid) so the whole tree can be killed.
      const child = spawn(
        process.platform === 'win32' ? 'cmd.exe' : '/bin/sh',
        process.platform === 'win32' ? ['/d', '/s', '/c', command] : ['-c', command],
        { detached: true, windowsHide: true, cwd: this.rootDir, stdio: ['ignore', 'pipe', 'pipe'] },
      )
      this.runningExecs.set(requestId, child)

      const timer = setTimeout(() => {
        timedOut = true
        this.killProcessTree(child)
      }, timeoutMs)

      const append = (buf: Buffer, isErr: boolean): void => {
        if (truncated) return
        const next = Buffer.concat([isErr ? stderr : stdout, buf])
        if (next.length > maxBuffer) {
          truncated = true
          this.killProcessTree(child)
          return
        }
        if (isErr) stderr = next
        else stdout = next
      }
      child.stdout?.on('data', (d: Buffer) => append(d, false))
      child.stderr?.on('data', (d: Buffer) => append(d, true))

      const finish = (): void => {
        clearTimeout(timer)
        this.runningExecs.delete(requestId)
      }

      child.on('close', (code) => {
        finish()
        if (timedOut) {
          resolve({ output: `Command timed out after ${timeout} seconds`, exit_code: -1, truncated: false })
          return
        }
        const outputParts: string[] = []
        if (stdout.length > 0) outputParts.push(decode(stdout).trimEnd())
        if (stderr.length > 0) {
          for (const line of decode(stderr).trimEnd().split('\n')) {
            outputParts.push(`[stderr] ${line}`)
          }
        }
        let output = outputParts.join('\n') || '<no output>'
        if (truncated || output.length > 100000) {
          output = output.slice(0, 100000) + '\n... (output truncated)'
          truncated = true
        }
        resolve({ output, exit_code: code ?? -1, truncated })
      })

      child.on('error', (err) => {
        finish()
        resolve({ output: `Error executing command: ${err.message}`, exit_code: -1, truncated: false })
      })
    })
  }

  private async handleDelete(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const vpath = (params.path as string) || ''

    let physical: string
    try {
      this.checkEditPermission(vpath)
      physical = this.resolvePath(vpath)
    } catch (e) {
      const msg = String(e)
      if (msg.includes('Edit denied')) {
        return { error: msg, error_code: 'EDIT_NOT_ALLOWED' }
      }
      if (msg.includes('Path traversal')) {
        return { error: msg, error_code: 'PATH_TRAVERSAL' }
      }
      return { error: msg, error_code: 'IO_ERROR' }
    }

    if (!fs.existsSync(physical!)) {
      return { error: `File not found: ${vpath}`, error_code: 'NOT_FOUND' }
    }

    const stat = fs.statSync(physical!)
    if (stat.isDirectory()) {
      return { error: `Path is a directory, not a file: ${vpath}`, error_code: 'IS_DIR' }
    }

    try {
      await fs.promises.unlink(physical!)
      return { path: vpath, success: true }
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /** Split text into lines with Python str.splitlines() semantics:
   *  - splits on \n, \r\n, \r and other Unicode line breaks
   *  - a trailing line break does NOT produce an empty last line
   *  - empty content yields zero lines
   */
  private splitLines(content: string): string[] {
    if (content === '') return []
    const parts = content.split(/\r\n|[\n\v\f\r\x85\u2028\u2029]/)
    if (parts.length > 0 && parts[parts.length - 1] === '') {
      parts.pop()
    }
    return parts
  }

  /** Format lines with 6-char right-aligned line numbers + Tab (cat -n style).
   *  Lines longer than 5000 chars are split into numbered chunks (42.1, 42.2).
   */
  private formatNumberedLines(lines: string[], startLine: number): string[] {
    const width = 6
    const maxLineLength = 5000
    const out: string[] = []
    for (let i = 0; i < lines.length; i++) {
      const num = i + startLine
      const line = lines[i]
      if (line.length <= maxLineLength) {
        out.push(String(num).padStart(width) + '\t' + line)
      } else {
        const chunkCount = Math.ceil(line.length / maxLineLength)
        for (let ci = 0; ci < chunkCount; ci++) {
          const chunk = line.slice(ci * maxLineLength, (ci + 1) * maxLineLength)
          const marker = ci > 0 ? `${num}.${ci}` : String(num)
          out.push(marker.padStart(width) + '\t' + chunk)
        }
      }
    }
    return out
  }

  /** Resolve a virtual path to a physical path within rootDir. */
  private resolvePath(requestedPath: string): string {
    if (!requestedPath) requestedPath = '/'
    if (!requestedPath.startsWith('/')) requestedPath = '/' + requestedPath

    // Strip the /workspace virtual mount point prefix
    if (requestedPath === '/workspace') {
      requestedPath = '/'
    } else if (requestedPath.startsWith('/workspace/')) {
      requestedPath = requestedPath.slice('/workspace'.length)
    }

    if (requestedPath === '/') {
      return path.normalize(this.rootDir)
    }

    const segments = requestedPath.split('/').filter(s => s && s !== '.' && s !== '..')
    const resolved = path.join(this.rootDir, ...segments)
    const normalized = path.normalize(resolved)

    // Prevent path traversal
    if (!normalized.startsWith(path.normalize(this.rootDir))) {
      throw new Error(`Path traversal not allowed: ${requestedPath}`)
    }
    return normalized
  }

  /** Check if a file path is allowed for write/edit operations. */
  private checkEditPermission(virtualPath: string): void {
    const pathStr = virtualPath
    if (this.editWhitelist.length > 0) {
      const allowed = this.editWhitelist.some(p =>
        pathStr === p.replace(/\/+$/, '') || pathStr.startsWith(p.replace(/\/+$/, '') + '/')
      )
      if (!allowed) {
        throw new Error(`Edit denied: Path '${pathStr}' is not in the edit whitelist.`)
      }
    }
    if (this.editBlacklist.length > 0) {
      const forbidden = this.editBlacklist.some(p =>
        pathStr === p.replace(/\/+$/, '') || pathStr.startsWith(p.replace(/\/+$/, '') + '/')
      )
      if (forbidden) {
        throw new Error(`Edit denied: Path '${pathStr}' is in the edit blacklist.`)
      }
    }
  }

  /** Recursive directory walker. Yields [filepath, isDir, isUnexpanded].
   *  Async + periodic event-loop yields so scanning huge trees never freezes
   *  the Electron main-process UI thread.
   */
  private async *walkDir(
    directory: string,
    maxDepth = -1,
    currentDepth = 1,
    ignoreDirs?: string[],
    visited = { count: 0 },
  ): AsyncGenerator<[string, boolean, boolean]> {
    const effectiveIgnore = ignoreDirs ?? []
    let entries: fs.Dirent[]
    try {
      entries = await fs.promises.readdir(directory, { withFileTypes: true })
      entries.sort((a, b) => a.name.localeCompare(b.name))
    } catch {
      return
    }

    for (const entry of entries) {
      // Anti-freeze: hard cap on visited files, and let the event loop breathe
      // every 256 entries so the UI stays responsive during deep scans.
      if (visited.count >= MAX_WALK_FILES) return
      if (++visited.count % 256 === 0) {
        await new Promise<void>(resolve => setImmediate(resolve))
      }

      const fullPath = path.join(directory, entry.name)
      const isDir = entry.isDirectory()

      let isUnexpanded = false
      if (isDir) {
        if (effectiveIgnore.includes(entry.name)) {
          isUnexpanded = true
        } else if (maxDepth !== -1 && currentDepth >= maxDepth) {
          isUnexpanded = true
        }
      }

      yield [fullPath, isDir, isUnexpanded]

      if (isDir && !isUnexpanded) {
        yield* this.walkDir(fullPath, maxDepth, currentDepth + 1, ignoreDirs, visited)
      }
    }
  }

  /** Try ripgrep for fast grep. Returns parsed matches or null to fall back.
   *  Async (execFile) so a slow scan never blocks the main-process UI thread.
   */
  private async _ripgrepGrep(
    pattern: string,
    basePath: string,
    glob: string | undefined,
    regex: boolean,
    ignoreDirs?: string[],
  ): Promise<object[] | null> {
    try {
      const args: string[] = ['--json', '--no-heading', '--hidden', '--no-ignore']
      if (!regex) args.push('-F')
      if (glob) args.push('--glob', glob)
      // Skip huge dependency/vendor dirs during unqualified scans
      for (const dir of ignoreDirs ?? []) {
        args.push('--glob', `!**/${dir}/**`, '--glob', `!${dir}/**`)
      }
      args.push('--', pattern, basePath)

      const { stdout } = await execFileAsync('rg', args, {
        timeout: 30000,
        maxBuffer: 50 * 1024 * 1024,
        encoding: 'utf-8',
      })

      const matches: object[] = []
      for (const line of stdout.split('\n')) {
        if (!line.trim()) continue
        try {
          const data = JSON.parse(line)
          if (data.type !== 'match') continue
          const pdata = data.data || {}
          const ftext = pdata.path?.text
          if (!ftext) continue
          const ln = pdata.line_number
          const lt = (pdata.lines?.text || '').replace(/\n$/, '')
          if (ln == null) continue

          const relPath = path.relative(this.rootDir, ftext).replace(/\\/g, '/')
          matches.push({
            path: '/workspace/' + relPath,
            line: ln,
            text: lt,
          })
        } catch { /* skip malformed JSON */ }
      }
      return matches
    } catch (err: any) {
      if (err.code === 1 || err.status === 1) return []  // rg exit 1 = no matches
      return null  // rg unavailable or error → fall back to Node.js traversal
    }
  }

  /** POSIX-style glob matching (pathlib-compatible), tested against a '/'-separated path.
   *  - ** matches zero or more directory levels (crosses /)
   *  - * matches any characters except /
   *  - ? matches a single character except /
   *  - [...] / [!...] character classes
   */
  private fnmatch(name: string, pattern: string): boolean {
    let re = ''
    let i = 0
    const n = pattern.length
    const esc = (c: string) => c.replace(/[.+^${}()|[\]\\]/g, '\\$&')
    while (i < n) {
      const c = pattern[i]
      i += 1
      if (c === '*') {
        if (pattern[i] === '*') {
          i += 1
          if (pattern[i] === '/') {
            i += 1
            re += '(?:.*/)?'
          } else {
            re += '.*'
          }
        } else {
          re += '[^/]*'
        }
      } else if (c === '?') {
        re += '[^/]'
      } else if (c === '[') {
        let j = i
        if (pattern[j] === '!' || pattern[j] === '^') j += 1
        if (pattern[j] === ']') j += 1
        while (j < n && pattern[j] !== ']') j += 1
        if (j >= n) {
          re += esc('[')
        } else {
          let stuff = pattern.slice(i, j)
          const negate = stuff.startsWith('!')
          if (negate || stuff.startsWith('^')) stuff = stuff.slice(1)
          stuff = stuff.replace(/\\/g, '\\\\')
          re += '[' + (negate ? '^' : '') + stuff + ']'
          i = j + 1
        }
      } else {
        re += esc(c)
      }
    }
    const regex = new RegExp('^' + re + '$')
    return regex.test(name)
  }
}

// ---------------------------------------------------------------------------
// ApiClientManager (Singleton) — manages multiple API client connections
// ---------------------------------------------------------------------------

export class ApiClientManager {
  private static instance: ApiClientManager | null = null

  private connections = new Map<string, ApiClientConnection>()

  private constructor() {}

  static getInstance(): ApiClientManager {
    if (!ApiClientManager.instance) {
      ApiClientManager.instance = new ApiClientManager()
    }
    return ApiClientManager.instance
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Start all API clients that have autoStart enabled and are registered.
   * Tolerant of individual failures — only throws if every client failed.
   */
  async start(config: AppConfig): Promise<void> {
    const clients = (config.remote?.apiClients ?? [])
      .filter(c => c.autoStart && c.backendId && c.apiKey)

    let firstError: Error | null = null
    let anyStarted = false
    for (const c of clients) {
      try {
        await this.startOne(config, c.backendId)
        anyStarted = true
      } catch (err) {
        if (!firstError) firstError = err instanceof Error ? err : new Error(String(err))
        log.warn(`[ApiClient] Failed to auto-start backend=${c.backendId}:`, err)
      }
    }
    if (!anyStarted && firstError && clients.length > 0) {
      throw firstError
    }
  }

  /** Start a single API client by backend ID. */
  async startOne(config: AppConfig, backendId: string): Promise<void> {
    const client = (config.remote?.apiClients ?? []).find(c => c.backendId === backendId)
    if (!client) {
      throw new Error(`API client '${backendId}' not found in config`)
    }
    if (!client.apiKey) {
      throw new Error(`API client '${backendId}' is missing an API key. Register with the server first.`)
    }

    let conn = this.connections.get(backendId)
    if (!conn) {
      conn = new ApiClientConnection(client.backendId, client.apiKey, client.rootDir || os.homedir(), client.name)
      this.connections.set(backendId, conn)
    } else {
      conn.configure(client.rootDir || os.homedir(), client.name)
    }

    await conn.connect(config.remote.url)
  }

  /** Stop all API clients. */
  async stop(): Promise<void> {
    await Promise.all([...this.connections.values()].map(c => c.disconnect()))
  }

  /** Stop a single API client by backend ID. */
  async stopOne(backendId: string): Promise<void> {
    const conn = this.connections.get(backendId)
    if (conn) {
      await conn.disconnect()
    }
  }

  /** Stop and forget a client (e.g. removed from config). */
  async remove(backendId: string): Promise<void> {
    const conn = this.connections.get(backendId)
    if (conn) {
      await conn.disconnect()
    }
    this.connections.delete(backendId)
  }

  /** Get status for every configured API client (aligned with config order). */
  getStatus(config?: AppConfig): ApiClientStatus[] {
    const list = config?.remote?.apiClients ?? []
    if (list.length === 0) {
      // Fallback: report live connections only
      return [...this.connections.values()].map(c => c.getStatus())
    }
    return list.map(c => {
      const conn = c.backendId ? this.connections.get(c.backendId) : undefined
      if (conn) {
        return conn.getStatus()
      }
      return {
        running: false,
        connected: false,
        connecting: false,
        backendId: c.backendId || undefined,
        name: c.name || undefined,
        rootDir: c.rootDir || undefined,
        error: c.backendId ? 'Not connected' : undefined,
      }
    })
  }

  /**
   * Register this PC as a new API backend on the remote server.
   * Always creates a fresh backend (the settings UI calls this per new card).
   */
  async register(serverUrl: string, rootDir: string, name?: string): Promise<{ backendId: string; apiKey: string }> {
    const cleanUrl = serverUrl.replace(/\/+$/, '')
    const hostname = os.hostname()
    const newApiKey = crypto.randomUUID()
    const label = (name || '').trim()
    const baseName = label ? `Desktop-${hostname}-${label}` : `Desktop-${hostname}`

    let backendId = ''
    let apiKey: string = newApiKey
    let lastErr: unknown = null

    // The server enforces unique backend names — retry with a suffix on collision.
    for (let attempt = 0; attempt < 5; attempt++) {
      const candidate = attempt === 0 ? baseName : `${baseName}-${attempt + 1}`
      const body = JSON.stringify({
        name: candidate,
        backendType: 'api',
        configData: {
          api_key: newApiKey,
        },
      })
      try {
        const result = await this.httpRequest(cleanUrl, 'POST', '/api/backends/', body)
        const data = JSON.parse(result)
        backendId = data.id as string
        // Server always masks api_key in response (returns "********"), so use
        // the key we generated. Only trust the response if it differs from the mask.
        const returnedKey = data.configData?.api_key as string | undefined
        apiKey = (returnedKey && returnedKey !== '********') ? returnedKey : newApiKey
        if (!backendId) {
          throw new Error('Server did not return backend ID')
        }
        log.info(`[ApiClient] Registered backend: ${backendId} (name=${candidate})`)
        break
      } catch (e) {
        lastErr = e
        const msg = String((e as Error)?.message || e)
        if (msg.includes('already exists') || msg.includes('Backend name already exists')) {
          continue
        }
        throw e
      }
    }

    if (!backendId) {
      throw new Error(`Failed to register backend: ${String(lastErr)}`)
    }
    return { backendId, apiKey }
  }

  // ---------------------------------------------------------------------------
  // HTTP helpers
  // ---------------------------------------------------------------------------

  /** Make an HTTP request to the remote server. */
  private httpRequest(baseUrl: string, method: string, urlPath: string, body?: string): Promise<string> {
    return new Promise((resolve, reject) => {
      const parsed = new URL(baseUrl)
      const isHttps = parsed.protocol === 'https:'
      const transport = isHttps ? https : http

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      if (body) {
        headers['Content-Length'] = String(Buffer.byteLength(body))
      }

      const options: http.RequestOptions = {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? 443 : 80),
        path: urlPath,
        method,
        headers,
        timeout: 15000,
      }

      const req = transport.request(options, (res) => {
        let data = ''
        res.on('data', (chunk: Buffer) => { data += chunk.toString() })
        res.on('end', () => {
          if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
            resolve(data)
          } else {
            reject(new Error(`HTTP ${res.statusCode}: ${data}`))
          }
        })
      })

      req.on('timeout', () => {
        req.destroy()
        reject(new Error('Request timed out'))
      })
      req.on('error', (err) => reject(err))

      if (body) req.write(body)
      req.end()
    })
  }

  /** Broadcast status changes to all renderer windows. */
  broadcastStatus(): void {
    const config = AppConfigManager.getInstance().load()
    const statuses = this.getStatus(config)
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) {
        win.webContents.send('apibackend:status', statuses)
      }
    })
  }
}
