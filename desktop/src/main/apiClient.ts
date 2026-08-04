/**
 * API Client Manager — WebSocket client that connects to a remote MamboChat
 * server and registers the local filesystem as an API backend.
 *
 * Runs entirely in the Electron main process using Node.js built-in WebSocket.
 * No Python subprocess needed.
 */

import { BrowserWindow } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import * as os from 'os'
import * as crypto from 'crypto'
import { execFile as execFileCb, execFileSync } from 'child_process'
import { promisify } from 'util'
import http from 'http'
import https from 'https'
import type { AppConfig } from './config'
import { AppConfigManager } from './config'
import log from './log'

const execFileAsync = promisify(execFileCb)

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ApiClientStatus {
  running: boolean
  connected: boolean
  connecting: boolean
  backendId?: string
  error?: string
}

interface ClientCommand {
  type: 'command'
  request_id: string
  method: string
  params: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// ApiClientManager (Singleton)
// ---------------------------------------------------------------------------

export class ApiClientManager {
  private static instance: ApiClientManager | null = null

  private ws: WebSocket | null = null
  private stopping = false
  private _connected = false
  private _connecting = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectDelay = 5000
  private currentBackendId = ''
  private currentRootDir = ''
  private editWhitelist: string[] = []
  private editBlacklist: string[] = []
  private lastConfig: AppConfig | null = null

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

  /** Start the API client — connect WebSocket to the remote server. */
  async start(config: AppConfig): Promise<void> {
    if (this.ws && (this._connected || this._connecting)) {
      return
    }

    const { url, apiClient } = config.remote
    if (!apiClient.backendId || !apiClient.apiKey) {
      throw new Error('Backend ID or API key is missing. Register with the server first.')
    }

    this.stopping = false
    this.lastConfig = config
    this.currentBackendId = apiClient.backendId
    this.currentRootDir = apiClient.rootDir || os.homedir()

    const wsUrl = this.httpToWs(url)
    const fullUrl = `${wsUrl}/api/api-client/ws/${apiClient.backendId}`

    log.info(`[ApiClient] Connecting to ${fullUrl} ...`)
    this._connecting = true
    this.broadcastStatus()

    try {
      await this.connect(fullUrl, apiClient.apiKey)
      this.reconnectDelay = 5000
    } catch (err) {
      this._connecting = false
      this.broadcastStatus()
      if (!this.stopping) {
        this.scheduleReconnect(config)
      }
      throw err
    }
  }

  /** Stop the API client. */
  async stop(): Promise<void> {
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
    log.info('[ApiClient] Stopped')
  }

  /** Get current status. */
  getStatus(): ApiClientStatus {
    return {
      running: !!this.ws || this._connecting,
      connected: this._connected,
      connecting: this._connecting,
      backendId: this.currentBackendId || undefined,
      error: this._connected ? undefined : (this._connecting ? undefined : 'Not connected'),
    }
  }

  /**
   * Register this PC as an API backend on the remote server.
   * Idempotent — if already registered (backendId exists locally and on server),
   * returns the existing credentials.
   */
  async register(serverUrl: string, rootDir: string): Promise<{ backendId: string; apiKey: string }> {
    const cleanUrl = serverUrl.replace(/\/+$/, '')
    const configManager = AppConfigManager.getInstance()
    const config = configManager.load()
    const existingId = config.remote.apiClient.backendId
    const existingKey = config.remote.apiClient.apiKey

    // If we have existing credentials, verify they still work on the server.
    // If the stored key is masked (from a previous bug), force re-registration.
    if (existingId && existingKey && existingKey !== '********') {
      const exists = await this.checkBackendExists(cleanUrl, existingId)
      if (exists) {
        log.info(`[ApiClient] Backend ${existingId} already exists on server, reusing`)
        return { backendId: existingId, apiKey: existingKey }
      }
      log.info(`[ApiClient] Backend ${existingId} no longer exists on server, re-registering`)
    }

    // Create a new API backend on the server
    const hostname = os.hostname()
    const newApiKey = crypto.randomUUID()
    const body = JSON.stringify({
      name: `Desktop-${hostname}`,
      backendType: 'api',
      configData: {
        api_key: newApiKey,
      },
    })

    const result = await this.httpRequest(cleanUrl, 'POST', '/api/backends/', body)
    const data = JSON.parse(result)

    const backendId = data.id as string
    // Server always masks api_key in response (returns "********"), so use the
    // key we generated. Only trust the response if it differs from the mask.
    const returnedKey = data.configData?.api_key as string | undefined
    const apiKey = (returnedKey && returnedKey !== '********') ? returnedKey : newApiKey
    if (!backendId) {
      throw new Error('Server did not return backend ID')
    }

    log.info(`[ApiClient] Registered backend: ${backendId}`)
    return { backendId, apiKey }
  }

  // ---------------------------------------------------------------------------
  // WebSocket connection
  // ---------------------------------------------------------------------------

  private connect(url: string, apiKey: string): Promise<void> {
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
        log.info('[ApiClient] WebSocket opened, sending auth')
        ws.send(JSON.stringify({ type: 'auth', api_key: apiKey }))
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
            log.info('[ApiClient] Authenticated successfully')

            // Send client info
            ws.send(JSON.stringify({
              type: 'register_info',
              info: {
                root_dir: this.currentRootDir,
                hostname: os.hostname(),
                platform: os.platform(),
                pid: process.pid,
              },
            }))

            this.broadcastStatus()
            resolve()
          } else if (msgType === 'welcome') {
            log.info(`[ApiClient] Server: ${msg.message || 'welcome'}`)
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
        log.error('[ApiClient] WebSocket error:', event)
        clearTimeout(timeout)
        if (!authDone) {
          this._connecting = false
          this.ws = null
          reject(new Error('WebSocket connection failed'))
        }
      }

      ws.onclose = (event) => {
        log.info(`[ApiClient] WebSocket closed (code=${event.code}, reason=${event.reason})`)
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
        if (wasConnected && !this.stopping && this.lastConfig) {
          this.scheduleReconnect(this.lastConfig)
        }
      }
    })
  }

  private scheduleReconnect(config: AppConfig): void {
    if (this.stopping || this.reconnectTimer) return

    log.info(`[ApiClient] Reconnecting in ${this.reconnectDelay / 1000}s ...`)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (!this.stopping) {
        this.start(config).catch(() => {
          this.reconnectDelay = Math.min(this.reconnectDelay * 2, 60000)
        })
      }
    }, this.reconnectDelay)
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
        case 'tree':          result = this.handleTree(params); break
        case 'ls':            result = this.handleLs(params); break
        case 'read_file':     result = this.handleReadFile(params); break
        case 'write_file':    result = this.handleWriteFile(params); break
        case 'edit_file':     result = this.handleEditFile(params); break
        case 'grep_files':    result = this.handleGrepFiles(params); break
        case 'glob_files':    result = this.handleGlobFiles(params); break
        case 'upload_files':  result = this.handleUploadFiles(params); break
        case 'download_files':result = this.handleDownloadFiles(params); break
        case 'execute':       result = await this.handleExecute(params); break
        case 'delete_file':   result = this.handleDelete(params); break
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

  private handleTree(params: Record<string, unknown>): Record<string, unknown> {
    const vpath = (params.path as string) || '/workspace'
    const depth = (params.depth as number) ?? 3
    const ignoreDirs: string[] = (params.ignore_dirs as string[]) ?? []
    const base = this.resolvePath(vpath)

    if (depth < 1) {
      return { tree: `Invalid depth value: ${depth}. Depth must be a positive integer (>= 1).` }
    }

    if (!fs.existsSync(base) || !fs.statSync(base).isDirectory()) {
      return { tree: `Error: Not a directory: ${vpath}`, error_code: 'NOT_DIR' }
    }

    interface TreeEntry { name: string; depth: number; marker: string }
    const entries: TreeEntry[] = []

    const walk = (dir: string, currentDepth: number): void => {
      if (currentDepth > depth) return
      let dirents: fs.Dirent[]
      try { dirents = fs.readdirSync(dir, { withFileTypes: true }) }
      catch { return }

      // Directories first, then files (case-insensitive sort)
      dirents.sort((a, b) => {
        if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
      })

      for (const d of dirents) {
        if (ignoreDirs.includes(d.name)) {
          entries.push({ name: d.name + '/', depth: currentDepth, marker: 'ignore' })
          continue
        }
        if (d.isDirectory()) {
          if (currentDepth + 1 > depth) {
            // At depth limit: check if non-empty
            const full = path.join(dir, d.name)
            let hasChildren = false
            try {
              const sub = fs.readdirSync(full, { withFileTypes: true })
              hasChildren = sub.length > 0
            } catch { /* ignore */ }
            entries.push({
              name: d.name + '/',
              depth: currentDepth,
              marker: hasChildren ? 'depth_exceeded' : 'empty',
            })
          } else {
            const full = path.join(dir, d.name)
            let hasChildren = false
            try {
              const sub = fs.readdirSync(full, { withFileTypes: true })
              hasChildren = sub.length > 0
            } catch { /* ignore */ }
            if (!hasChildren) {
              entries.push({ name: d.name + '/', depth: currentDepth, marker: 'empty' })
            } else {
              entries.push({ name: d.name + '/', depth: currentDepth, marker: '' })
              walk(full, currentDepth + 1)
            }
          }
        } else {
          let sizeStr = ''
          try {
            const st = fs.statSync(path.join(dir, d.name))
            sizeStr = ` (${this.formatSize(st.size)})`
          } catch { /* ignore */ }
          entries.push({ name: d.name + sizeStr, depth: currentDepth, marker: '' })
        }
      }
    }

    walk(base, 1)

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
      let display = entry.name + (markerSuffix[entry.marker] || '')

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

  private handleLs(params: Record<string, unknown>): Record<string, unknown> {
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
      const entries = fs.readdirSync(physical).sort()
      for (const entry of entries) {
        const full = path.join(physical, entry)
        let stat: fs.Stats
        try { stat = fs.statSync(full) } catch { continue }
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

  private handleReadFile(params: Record<string, unknown>): Record<string, unknown> {
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
      return { error: `File not found: ${vpath}`, error_code: 'NOT_FOUND' }
    }
    if (fs.statSync(physical).isDirectory()) {
      return { error: `Path is a directory, not a file: ${vpath}`, error_code: 'IS_DIR' }
    }

    const ext = path.extname(physical).toLowerCase()
    const fileType = this.FILE_TYPE_MAP[ext] || 'text'

    if (fileType !== 'text') {
      // Binary / multimedia file: read as base64
      try {
        const raw = fs.readFileSync(physical)
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
      buf = fs.readFileSync(physical)
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

    const lines = content.split('\n')
    const start = offset
    const end = (limit != null) ? Math.min(start + limit, lines.length) : lines.length

    if (start >= lines.length) {
      return { error: `Line offset ${offset} exceeds file length (${lines.length} lines)`, error_code: 'INVALID' }
    }

    const selected = lines.slice(start, end)
    const resultLines = includeLineNumbers
      ? (() => {
          const width = Math.max(3, String(start + selected.length).length)
          return selected.map((line, i) => {
            const num = String(i + start + 1).padStart(width)
            return `${num}  ${line}`
          })
        })()
      : selected

    return {
      content: selected.join('\n'),
      lines: resultLines,
      total_lines: lines.length,
      offset: start,
      limit,
      encoding: 'utf-8',
      file_type: 'text',
      mime_type: '',
    }
  }

  private handleWriteFile(params: Record<string, unknown>): Record<string, unknown> {
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
        const existingBuf = fs.readFileSync(physical!)
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
      fs.writeFileSync(physical!, content, 'utf-8')
      return { path: vpath, success: true }
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }
  }

  private handleEditFile(params: Record<string, unknown>): Record<string, unknown> {
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

    if (!fs.existsSync(physical!) || !fs.statSync(physical!).isFile()) {
      return { error: `File not found: ${vpath}. To create a new file, use write().`, error_code: 'NOT_FOUND' }
    }

    let editBuf: Buffer
    try {
      editBuf = fs.readFileSync(physical!)
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
      fs.writeFileSync(physical!, newContent, 'utf-8')
      return { path: vpath, occurrences, success: true }
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }
  }

  private handleGrepFiles(params: Record<string, unknown>): Record<string, unknown> {
    const pattern = (params.pattern as string) || ''
    const vpath = (params.path as string) || '/workspace'
    const glob = (params.glob as string) || undefined
    const regex = (params.regex as boolean) ?? true
    const offset = (params.offset as number) ?? 0
    const limit = (params.limit as number) ?? undefined
    const ignoreDirs: string[] = (params.ignore_dirs as string[]) ?? []
    const base = this.resolvePath(vpath)

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
    const MAX_GREP_MATCHES = 1000

    // 1) Try ripgrep (fast native search)
    const rgMatches = this._ripgrepGrep(pattern, base, isDir ? glob : undefined, regex)
    if (rgMatches !== null) {
      // Post-filter rg output: --glob uses gitignore semantics (not POSIX),
      // and ignore_dirs must be applied uniformly across both search paths.
      const filtered: object[] = []
      for (const m of rgMatches) {
        if (filtered.length >= MAX_GREP_MATCHES) break
        const mpath = (m as { path: string }).path
        // ignore_dirs: parent-segment check (mirrors the backends' _in_ignored_dir)
        if (ignoreDirs.length > 0) {
          const rel = mpath.startsWith('/workspace/')
            ? mpath.slice('/workspace/'.length)
            : mpath.replace(/^\//, '')
          const parentSegs = rel.split('/').slice(0, -1)
          if (parentSegs.some(seg => ignoreDirs.includes(seg))) continue
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
      const sliced = offset > 0 ? filtered.slice(offset) : filtered
      const limited = limit !== undefined ? sliced.slice(0, limit) : sliced
      return { matches: limited, truncated: limited.length < filtered.length }
    }

    // 2) Node.js fallback
    const matches: object[] = []
    const maxFileSize = 10 * 1024 * 1024
    let skipped = 0

    const searchFile = (filePath: string, displayPath: string): void => {
      if (matches.length >= MAX_GREP_MATCHES) return
      if (limit !== undefined && matches.length >= limit) return
      if (glob) {
        const relPath = displayPath.startsWith(vpath)
          ? displayPath.slice(vpath.length).replace(/^\//, '')
          : displayPath
        if (!this.fnmatch(relPath, glob)) return
      }
      try {
        const stat = fs.statSync(filePath)
        if (stat.size > maxFileSize) return
        const content = fs.readFileSync(filePath, 'utf-8')
        const lines = content.split('\n')
        for (let i = 0; i < lines.length; i++) {
          if (matches.length >= MAX_GREP_MATCHES) break
          if (limit !== undefined && matches.length >= limit) break
          if (!testFn(lines[i])) continue
          if (skipped < offset) { skipped++; continue }
          matches.push({
            path: displayPath,
            line: i + 1,
            text: lines[i],
          })
        }
      } catch { /* skip unreadable files */ }
    }

    if (fs.existsSync(base) && fs.statSync(base).isFile()) {
      const displayPath = '/workspace/' + path.relative(this.currentRootDir, base).replace(/\\/g, '/')
      searchFile(base, displayPath)
    } else if (fs.existsSync(base) && fs.statSync(base).isDirectory()) {
      for (const [fp, isDir] of this.walkDir(base, -1, 1, ignoreDirs)) {
        if (isDir) continue
        const relPath = '/workspace/' + path.relative(this.currentRootDir, fp).replace(/\\/g, '/')
        searchFile(fp, relPath)
      }
    }

    log.info(`[ApiClient] handleGrepFiles: found ${matches.length} matches`)
    const truncated = (limit !== undefined && limit > 0 && matches.length >= limit) || matches.length >= MAX_GREP_MATCHES
    return { matches, truncated }
  }

  private handleGlobFiles(params: Record<string, unknown>): Record<string, unknown> {
    const pattern = (params.pattern as string) || '*'
    const vpath = (params.path as string) || '/workspace'
    const base = this.resolvePath(vpath)

    if (!fs.existsSync(base)) {
      return { error: `Path not found: ${vpath}`, error_code: 'NOT_FOUND' }
    }
    if (!fs.statSync(base).isDirectory()) {
      return { error: `Not a directory: ${vpath}`, error_code: 'NOT_DIR' }
    }

    const results: object[] = []
    const effectivePattern = pattern.replace(/^\//, '')

    // Align with local/ssh backends: glob does not filter ignore_dirs.
    for (const [fp, isDir] of this.walkDir(base, -1, 1, [])) {
      if (isDir) continue
      const rel = path.relative(base, fp).replace(/\\/g, '/')
      if (!this.fnmatch(rel, effectivePattern)) continue
      try {
        const stat = fs.statSync(fp)
        const vp = '/workspace/' + path.relative(this.currentRootDir, fp).replace(/\\/g, '/')
        results.push({
          path: vp,
          is_dir: false,
          size: stat.size,
          modified_at: stat.mtime.toISOString(),
        })
      } catch { /* skip */ }
    }

    results.sort((a: any, b: any) => a.path.localeCompare(b.path))
    return { items: results }
  }

  private handleUploadFiles(params: Record<string, unknown>): { results: object[] } {
    const files = (params.files as Array<{ path: string; content_b64: string }>) || []
    const results: object[] = []

    for (const item of files) {
      try {
        this.checkEditPermission(item.path)
        const physical = this.resolvePath(item.path)
        const content = Buffer.from(item.content_b64, 'base64')
        fs.mkdirSync(path.dirname(physical), { recursive: true })
        fs.writeFileSync(physical, content)
        results.push({ path: item.path, error: null })
      } catch (e) {
        results.push({ path: item.path, error: String(e) })
      }
    }
    return { results }
  }

  private handleDownloadFiles(params: Record<string, unknown>): { results: object[] } {
    const paths = (params.paths as string[]) || []
    const results: object[] = []

    for (const vpath of paths) {
      try {
        const physical = this.resolvePath(vpath)
        if (!fs.existsSync(physical) || !fs.statSync(physical).isFile()) {
          results.push({ path: vpath, error: 'file_not_found' })
          continue
        }
        const content = fs.readFileSync(physical)
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

  private async handleExecute(params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const command = (params.command as string) || ''
    const timeout = (params.timeout as number) || undefined

    try {
      const shellCmd = process.platform === 'win32' ? 'cmd.exe' : '/bin/sh'
      const shellArgs = process.platform === 'win32' ? ['/c', command] : ['-c', command]
      const { stdout, stderr } = await execFileAsync(shellCmd, shellArgs, {
        timeout,
        maxBuffer: 100 * 1024 * 1024,
        cwd: this.currentRootDir,
      })
      const outputParts: string[] = []
      if (stdout) outputParts.push(stdout.trimEnd())
      if (stderr) {
        for (const line of stderr.trimEnd().split('\n')) {
          outputParts.push(`[stderr] ${line}`)
        }
      }
      let output = outputParts.join('\n') || '<no output>'

      const truncated = output.length > 100000
      if (truncated) output = output.slice(0, 100000) + '\n... (output truncated)'

      return { output, exit_code: 0, truncated }
    } catch (e: any) {
      if (e.killed) {
        return { output: `Command timed out after ${timeout} seconds`, exit_code: -1, truncated: false }
      }
      return {
        output: e.stdout || e.stderr || `Error executing command: ${e.message}`,
        exit_code: e.code ?? -1,
        truncated: false,
      }
    }
  }

  private handleDelete(params: Record<string, unknown>): Record<string, unknown> {
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
      fs.unlinkSync(physical!)
      return { path: vpath, success: true }
    } catch (e) {
      return { error: String(e), error_code: 'IO_ERROR' }
    }
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

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
      return path.normalize(this.currentRootDir)
    }

    const segments = requestedPath.split('/').filter(s => s && s !== '.' && s !== '..')
    const resolved = path.join(this.currentRootDir, ...segments)
    const normalized = path.normalize(resolved)

    // Prevent path traversal
    if (!normalized.startsWith(path.normalize(this.currentRootDir))) {
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

  /** Recursive directory walker. Yields [filepath, isDir, isUnexpanded]. */
  private *walkDir(
    directory: string,
    maxDepth = -1,
    currentDepth = 1,
    ignoreDirs?: string[],
  ): Generator<[string, boolean, boolean]> {
    const effectiveIgnore = ignoreDirs ?? []
    let entries: fs.Dirent[]
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true })
      entries.sort((a, b) => a.name.localeCompare(b.name))
    } catch {
      return
    }

    for (const entry of entries) {
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
        yield* this.walkDir(fullPath, maxDepth, currentDepth + 1, ignoreDirs)
      }
    }
  }

  /** Try ripgrep for fast grep. Returns parsed matches or null to fall back. */
  private _ripgrepGrep(
    pattern: string,
    basePath: string,
    glob: string | undefined,
    regex: boolean,
  ): object[] | null {
    try {
      const args: string[] = ['--json', '--no-heading', '--hidden', '--no-ignore']
      if (!regex) args.push('-F')
      if (glob) args.push('--glob', glob)
      args.push('--', pattern, basePath)

      const stdout = execFileSync('rg', args, {
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

          const relPath = path.relative(this.currentRootDir, ftext).replace(/\\/g, '/')
          matches.push({
            path: '/workspace/' + relPath,
            line: ln,
            text: lt,
          })
        } catch { /* skip malformed JSON */ }
      }
      return matches
    } catch (err: any) {
      if (err.status === 1) return []  // rg exit 1 = no matches
      return null  // rg unavailable or error → fall back to Node.js traversal
    }
  }

  /** Simple fnmatch-style glob matching.
   *  - ** matches zero or more directory levels (crosses /)
   *  - * matches any characters except /
   *  - ? matches a single character except /
   */
  private fnmatch(name: string, pattern: string): boolean {
    let escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&')
    escaped = escaped.replace(/\*\*\//g, '\x01')
    escaped = escaped.replace(/\/\*\*/g, '\x02')
    escaped = escaped.replace(/\*\*/g, '\x03')
    escaped = escaped.replace(/\*/g, '\x04')
    escaped = escaped.replace(/\?/g, '\x05')
    escaped = escaped.replace(/\x01/g, '(.*/)?')
    escaped = escaped.replace(/\x02/g, '(/.*)?')
    escaped = escaped.replace(/\x03/g, '.*')
    escaped = escaped.replace(/\x04/g, '[^/]*')
    escaped = escaped.replace(/\x05/g, '[^/]')
    const re = new RegExp('^' + escaped + '$')
    return re.test(name)
  }

  /** Convert http:// to ws:// and https:// to wss:// */
  private httpToWs(url: string): string {
    const clean = url.replace(/\/+$/, '')
    if (clean.startsWith('https://')) return clean.replace('https://', 'wss://')
    if (clean.startsWith('http://')) return clean.replace('http://', 'ws://')
    return clean
  }

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

  /** Check if a backend exists on the remote server. */
  private async checkBackendExists(serverUrl: string, backendId: string): Promise<boolean> {
    try {
      await this.httpRequest(serverUrl, 'GET', `/api/backends/${backendId}`)
      return true
    } catch {
      return false
    }
  }

  /** Broadcast status change to all renderer windows. */
  private broadcastStatus(): void {
    const status = this.getStatus()
    BrowserWindow.getAllWindows().forEach(win => {
      if (!win.isDestroyed()) {
        win.webContents.send('apibackend:status', status)
      }
    })
  }
}
