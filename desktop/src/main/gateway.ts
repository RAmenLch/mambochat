/**
 * Gateway server embedded in the Electron main process.
 *
 * Acts as a reverse proxy + static file server:
 * - In local mode: proxies /api/* to the local Uvicorn backend (127.0.0.1:<port>)
 * - In remote mode: proxies /api/* to the remote server URL
 * - Serves the frontend dist as static files (SPA fallback to index.html)
 *
 * This replaces both the Vite dev server (production) and the loadFile() approach.
 * The gateway runs directly inside the Electron main process (no child process needed).
 */

import http from 'http'
import { createServer, Server } from 'net'
import { createReadStream, existsSync, statSync, readdirSync } from 'fs'
import { join, extname } from 'path'
import { app } from 'electron'
import log from './log'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type GatewayMode = 'local' | 'remote'

export interface GatewayStatus {
  running: boolean
  port?: number
  host?: string
  mode?: GatewayMode
}

// Common MIME types for static file serving
const MIME_TYPES: Record<string, string> = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
  '.otf': 'font/otf',
  '.webp': 'image/webp',
  '.webm': 'video/webm',
  '.mp4': 'video/mp4',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
  '.pdf': 'application/pdf',
  '.txt': 'text/plain',
  '.xml': 'application/xml',
  '.map': 'application/json',
}

const DEFAULT_GATEWAY_PORT = 5173

// ---------------------------------------------------------------------------
// GatewayServer (Singleton)
// ---------------------------------------------------------------------------

export class GatewayServer {
  private static instance: GatewayServer | null = null
  private server: http.Server | null = null
  private currentPort: number | null = null
  private currentHost: string = '127.0.0.1'
  private currentMode: GatewayMode = 'local'
  private backendTarget: string = '' // e.g. "http://127.0.0.1:8000" or "http://192.168.1.100:8000"
  private frontendDistPath: string = ''
  private stopping = false
  /** Tracks whether the backend is currently being started (not yet ready) */
  private backendStarting = false

  private constructor() {}

  static getInstance(): GatewayServer {
    if (!GatewayServer.instance) {
      GatewayServer.instance = new GatewayServer()
    }
    return GatewayServer.instance
  }

  /**
   * Resolve the path to the frontend dist directory.
   */
  private resolveFrontendDistPath(): string {
    if (app.isPackaged) {
      return join(process.resourcesPath, 'frontend', 'dist')
    }
    // In dev, point to the built frontend dist
    // When using "npm run dev:electron", frontend may not be built yet;
    // but in production it always exists.
    return join(app.getAppPath(), '..', 'frontend', 'mambo', 'dist')
  }

  /**
   * Start the gateway server.
   *
   * @param host - Bind address ('0.0.0.0' or '127.0.0.1')
   * @param port - Port to listen on (auto-detected if not available)
   * @returns The actual port the gateway is listening on
   */
  async start(
    host: string,
    port: number = DEFAULT_GATEWAY_PORT
  ): Promise<number> {
    // Don't start if already running
    if (this.server && this.currentPort) {
      return this.currentPort
    }

    this.currentHost = host
    this.frontendDistPath = this.resolveFrontendDistPath()

    // Find an available port (try the requested one first, then scan nearby)
    const actualPort = await this.detectAvailablePort(host, port, port + 50)

    return new Promise<number>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Gateway failed to start within 10s`))
      }, 10_000)

      this.server = http.createServer((req, res) => {
        this.handleRequest(req, res)
      })

      // Handle HTTP parser errors (malformed requests) — these result in 400 responses.
      // Without this handler, Node.js sends a generic 400 with no logging.
      this.server.on('clientError', (err, socket) => {
        log.error(`[Gateway] Client error: ${err.message}`)
        if (socket.writable && !socket.destroyed) {
          socket.end('HTTP/1.1 400 Bad Request\r\n\r\n')
        }
      })

      this.server.on('error', (err: NodeJS.ErrnoException) => {
        clearTimeout(timeout)
        log.error(`[Gateway] Server error:`, err.message)
        this.server = null
        this.currentPort = null
        reject(err)
      })

      this.server.listen(actualPort, host, () => {
        clearTimeout(timeout)
        this.currentPort = actualPort
        log.info(`[Gateway] Listening on ${host}:${actualPort}`)
        resolve(actualPort)
      })
    })
  }

  /**
   * Stop the gateway server.
   */
  async stop(): Promise<void> {
    if (!this.server) return

    this.stopping = true
    const srv = this.server
    this.server = null
    this.currentPort = null

    await new Promise<void>((resolve) => {
      srv.close(() => {
        this.stopping = false
        log.info('[Gateway] Stopped')
        resolve()
      })
      // Force close after timeout
      setTimeout(resolve, 3000)
    })
  }

  /**
   * Update the backend proxy target (called when backend starts/stops/restarts).
   */
  setBackendTarget(target: string): void {
    this.backendTarget = target.replace(/\/+$/, '')
    this.backendStarting = false
    log.info(`[Gateway] Backend target set to: ${this.backendTarget}`)
  }

  /**
   * Mark that the backend is starting (not yet ready).
   * During this period, API requests will get a "starting" response instead of 502.
   */
  setBackendStarting(): void {
    this.backendStarting = true
    log.info('[Gateway] Backend is marked as starting...')
  }

  /**
   * Set the current mode (local/remote).
   */
  setMode(mode: GatewayMode): void {
    this.currentMode = mode
    log.info(`[Gateway] Mode set to: ${mode}`)
  }

  /**
   * Get current gateway status.
   */
  getStatus(): GatewayStatus {
    if (!this.server || !this.currentPort) {
      return { running: false }
    }
    return {
      running: true,
      port: this.currentPort,
      host: this.currentHost,
      mode: this.currentMode,
    }
  }

  /**
   * Get the gateway URL (for the main window to loadURL).
   */
  getUrl(): string | null {
    if (!this.currentPort) return null
    return `http://127.0.0.1:${this.currentPort}`
  }

  /**
   * Get the current gateway port.
   */
  getPort(): number | null {
    return this.currentPort
  }

  // ---------------------------------------------------------------------------
  // Request handling
  // ---------------------------------------------------------------------------

  private handleRequest(req: http.IncomingMessage, res: http.ServerResponse): void {
    const url = req.url || '/'

    // API requests → reverse proxy to backend
    if (url.startsWith('/api/') || url === '/api') {
      this.proxyRequest(req, res)
      return
    }

    // Everything else → serve static files
    this.serveStatic(req, res, url)
  }

  // ---------------------------------------------------------------------------
  // Static file serving (SPA with fallback to index.html)
  // ---------------------------------------------------------------------------

  private serveStatic(req: http.IncomingMessage, res: http.ServerResponse, urlPath: string): void {
    // Decode and sanitize the path
    let pathname: string
    try {
      pathname = decodeURIComponent(urlPath.split('?')[0])
    } catch {
      pathname = urlPath.split('?')[0]
    }

    // Security: prevent directory traversal
    const safePath = pathname.replace(/\.\./g, '').replace(/^\/+/, '')
    const filePath = join(this.frontendDistPath, safePath || 'index.html')

    if (!existsSync(filePath) || !statSync(filePath).isFile()) {
      // SPA fallback: serve index.html for any non-file path (Vue Router history mode)
      this.sendFile(res, join(this.frontendDistPath, 'index.html'))
      return
    }

    this.sendFile(res, filePath)
  }

  private sendFile(res: http.ServerResponse, filePath: string): void {
    if (!existsSync(filePath)) {
      res.writeHead(404, { 'Content-Type': 'text/plain' })
      res.end('Not Found')
      return
    }

    const ext = extname(filePath).toLowerCase()
    const contentType = MIME_TYPES[ext] || 'application/octet-stream'

    try {
      const stat = statSync(filePath)
      res.writeHead(200, {
        'Content-Type': contentType,
        'Content-Length': stat.size,
        'Cache-Control': this.isImmutableAsset(filePath) ? 'public, max-age=31536000, immutable' : 'no-cache',
      })
      createReadStream(filePath).pipe(res)
    } catch (err) {
      log.error(`[Gateway] Error serving file ${filePath}:`, err)
      res.writeHead(500, { 'Content-Type': 'text/plain' })
      res.end('Internal Server Error')
    }
  }

  /**
   * Check if a file is an immutable asset (content-hashed filename).
   */
  private isImmutableAsset(filePath: string): boolean {
    const name = filePath.split(/[\\/]/).pop() || ''
    // Files with content hashes in their name (e.g. index.abc123.js)
    return /\.\w{8}\.(js|css|woff2?|ttf|png|jpg|svg)$/.test(name)
  }

  // ---------------------------------------------------------------------------
  // Reverse proxy
  // ---------------------------------------------------------------------------

  private proxyRequest(req: http.IncomingMessage, res: http.ServerResponse): void {
    if (!this.backendTarget) {
      // Backend not configured or still starting — return actionable info
      const statusCode = this.backendStarting ? 503 : 502
      const detail = this.backendStarting
        ? 'Backend is starting up, please retry in a few seconds.'
        : 'Backend is not available. Please start the backend first.'
      res.writeHead(statusCode, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ detail, starting: this.backendStarting }))
      return
    }

    const targetUrl = this.backendTarget + req.url
    const parsedUrl = new URL(targetUrl)

    // Build clean headers: drop hop-by-hop headers, override host.
    // We keep 'connection' out of hopByHop so we can force Connection: close
    // on outbound requests (prevents Docker port forwarding connection pool issues).
    const headers: Record<string, string | string[] | undefined> = {}
    const hopByHop = new Set([
      'keep-alive', 'transfer-encoding',
      'te', 'trailer', 'upgrade', 'proxy-authorization',
      'proxy-authenticate',
    ])
    // SSE/stream endpoints need persistent connections — skip Connection: close
    const isSSE = req.url?.includes('/stream-response') || req.url?.includes('/notifications/subscribe')
    for (const [key, value] of Object.entries(req.headers)) {
      if (!hopByHop.has(key)) {
        headers[key] = value
      }
    }
    headers['host'] = parsedUrl.host
    if (!isSSE) {
      headers['connection'] = 'close'
    }

    const proxyReq = http.request(
      {
        hostname: parsedUrl.hostname,
        port: parsedUrl.port || (parsedUrl.protocol === 'https:' ? 443 : 80),
        path: parsedUrl.pathname + parsedUrl.search,
        method: req.method,
        headers,
      },
      (proxyRes) => {
        // Copy status and headers
        res.writeHead(proxyRes.statusCode || 502, proxyRes.headers)
        // Pipe response body
        proxyRes.pipe(res)
        // If the client disconnects while we're still piping the response,
        // destroy the backend connection to avoid wasting resources.
        res.on('close', () => {
          proxyRes.destroy()
        })
      }
    )

    proxyReq.on('error', (err) => {
      log.error(`[Gateway] Proxy error for ${req.url}:`, err.message)
      if (!res.headersSent) {
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ detail: 'Backend connection failed.' }))
      }
    })

    // Pipe request body to backend
    req.pipe(proxyReq)
  }

  // ---------------------------------------------------------------------------
  // Port detection
  // ---------------------------------------------------------------------------

  private detectAvailablePort(host: string, portStart: number, portEnd: number): Promise<number> {
    return new Promise((resolve, reject) => {
      let current = portStart

      const tryPort = (): void => {
        if (current > portEnd) {
          reject(
            new Error(
              `No available gateway port found in range ${portStart}-${portEnd}. ` +
              'Please close other applications and try again.'
            )
          )
          return
        }

        const probe = createServer()
        probe.once('error', () => {
          probe.close()
          current++
          tryPort()
        })

        probe.once('listening', () => {
          probe.close()
          resolve(current)
        })

        probe.listen(current, host)
      }

      tryPort()
    })
  }
}
