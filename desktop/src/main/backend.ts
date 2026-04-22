/**
 * Backend process manager for local mode.
 *
 * Manages the lifecycle of the Python backend process:
 * - Port detection and allocation
 * - Process spawning with correct environment
 * - Health check polling until ready
 * - Graceful shutdown
 */

import { spawn, ChildProcess, execSync } from 'child_process'
import { createServer, createConnection } from 'net'
import { app, BrowserWindow } from 'electron'
import { join, isAbsolute } from 'path'
import type { AppConfig } from './config'
import log from './log'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BackendStatus {
  running: boolean
  port?: number
  pid?: number
  error?: string
}

// ---------------------------------------------------------------------------
// BackendProcessManager (Singleton)
// ---------------------------------------------------------------------------

export class BackendProcessManager {
  private static instance: BackendProcessManager | null = null
  private process: ChildProcess | null = null
  private currentPort: number | null = null
  private stopping = false

  /** Callback invoked when the backend process exits unexpectedly (not via stop()). */
  onUnexpectedExit: (() => void) | null = null

  private constructor() {}

  static getInstance(): BackendProcessManager {
    if (!BackendProcessManager.instance) {
      BackendProcessManager.instance = new BackendProcessManager()
    }
    return BackendProcessManager.instance
  }

  /**
   * Start the local backend process.
   *
   * @returns The port the backend is listening on
   */
  async start(config: AppConfig): Promise<number> {
    // Don't start if already running
    if (this.process && this.currentPort) {
      return this.currentPort
    }

    const { pythonPath, portStart, portEnd } = config.local

    // 1. Resolve Python executable path
    const exePath = this.resolvePythonPath(pythonPath)

    // Backend always binds to 127.0.0.1 — external access is controlled via the frontend dev server
    const bindHost = '127.0.0.1'

    // 2. Detect an available port
    const port = await this.detectAvailablePort(bindHost, portStart, portEnd)

    // 3. Determine working directory (project root)
    const appDir = this.resolveAppDirectory()

    // 4. Build environment
    const env = this.buildEnvironment(appDir)

    // 5. Spawn the backend process
    log.info(`[Backend] Starting on port ${port}...`)
    log.info(`[Backend] Python: ${exePath}`)
    log.info(`[Backend] WorkDir: ${appDir}`)

    this.process = spawn(
      exePath,
      ['-m', 'uvicorn', 'backend.main:app', '--host', bindHost, '--port', String(port)],
      {
        cwd: appDir,
        env: { ...process.env, ...env },
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: false,
      }
    )

    // Pipe stdout/stderr for debugging
    this.process.stdout?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      if (msg) log.info(`[Backend:OUT] ${msg}`)
    })

    this.process.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      if (msg) log.warn(`[Backend:ERR] ${msg}`)
    })

    this.process.on('error', (err) => {
      log.error('[Backend] Process error:', err.message)
      this.process = null
      this.currentPort = null
    })

    this.process.on('exit', (code, signal) => {
      log.info(`[Backend] Process exited (code=${code}, signal=${signal})`)
      const pid = this.process?.pid
      this.process = null
      this.currentPort = null

      // If we didn't initiate the stop, notify all windows and trigger callback
      if (!this.stopping) {
        log.warn('[Backend] Unexpected exit — notifying renderer windows')
        const status = { running: false, mode: 'local' as const }
        BrowserWindow.getAllWindows().forEach(win => {
          if (!win.isDestroyed()) {
            win.webContents.send('backend:status', status)
          }
        })
        this.onUnexpectedExit?.()
      }
    })

    // 6. Wait for backend to become ready
    await this.waitForReady(bindHost === '0.0.0.0' ? '127.0.0.1' : bindHost, port, 30_000)

    this.currentPort = port
    log.info(`[Backend] Ready on port ${port}`)
    return port
  }

  /**
   * Stop the backend process gracefully.
   * Returns a promise that resolves when the process has fully exited.
   */
  async stop(timeoutMs = 5000): Promise<void> {
    if (!this.process) return

    const pid = this.process.pid
    log.info(`[Backend] Stopping (PID: ${pid})...`)
    this.stopping = true

    // Wrap exit in a promise
    const exitPromise = new Promise<void>((resolve) => {
      const proc = this.process
      if (!proc || proc.killed) {
        resolve()
        return
      }
      const onExit = () => {
        proc.off('exit', onExit)
        resolve()
      }
      proc.on('exit', onExit)
    })

    // Try SIGTERM first
    try {
      this.process.kill('SIGTERM')
    } catch {
      // Already dead
    }

    // On Windows, use taskkill to ensure the entire process tree is killed
    if (process.platform === 'win32' && pid) {
      try {
        execSync(`taskkill /T /F /PID ${pid}`, { stdio: 'ignore' })
      } catch {
        // Process may have already exited
      }
    }

    // Wait for the exit event, but enforce a timeout
    const timeoutPromise = new Promise<void>(resolve => setTimeout(resolve, timeoutMs))
    await Promise.race([exitPromise, timeoutPromise])

    // Force kill if still alive (Linux/macOS fallback)
    if (this.process && !this.process.killed && pid) {
      try {
        process.kill(pid, 'SIGKILL')
      } catch {
        // Already dead
      }
    }

    this.process = null
    this.currentPort = null
    this.stopping = false
  }

  /**
   * Get current backend status.
   */
  getStatus(): BackendStatus {
    if (!this.process || !this.currentPort) {
      return { running: false }
    }
    return {
      running: true,
      port: this.currentPort,
      pid: this.process.pid,
    }
  }

  /**
   * Get the current backend port.
   */
  getPort(): number | null {
    return this.currentPort
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  /**
   * Resolve the Python executable path.
   * Supports both relative paths (from app resources) and absolute paths.
   */
  private resolvePythonPath(configuredPath: string): string {
    if (isAbsolute(configuredPath)) {
      return configuredPath
    }

    // In development: relative to project root
    // In production: relative to resources directory
    if (app.isPackaged) {
      return join(process.resourcesPath, configuredPath)
    }
    return join(app.getAppPath(), '..', configuredPath)
  }

  /**
   * Resolve the application (project root) directory.
   */
  private resolveAppDirectory(): string {
    if (app.isPackaged) {
      // In production, backend code is in resources/backend/
      // We need to set the cwd so that "backend.main" is importable
      return process.resourcesPath
    }
    // In development, the project root is one level up from desktop/
    return join(app.getAppPath(), '..')
  }

  /**
   * Build environment variables for the backend process.
   */
  private buildEnvironment(appDir: string): Record<string, string> {
    return {
      PYTHONPATH: appDir,
      TZ: 'Asia/Shanghai',
      PYTHONIOENCODING: 'utf-8',
    }
  }

  /**
   * Detect an available port in the given range.
   */
  private detectAvailablePort(
    host: string,
    portStart: number,
    portEnd: number
  ): Promise<number> {
    return new Promise((resolve, reject) => {
      let current = portStart

      const tryPort = (): void => {
        if (current > portEnd) {
          reject(
            new Error(
              `No available port found in range ${portStart}-${portEnd}. ` +
              'Please close other applications and try again.'
            )
          )
          return
        }

        const server = createServer()
        server.once('error', () => {
          server.close()
          current++
          tryPort()
        })

        server.once('listening', () => {
          server.close()
          resolve(current)
        })

        server.listen(current, host)
      }

      tryPort()
    })
  }

  /**
   * Poll the backend health endpoint until it responds.
   */
  private waitForReady(
    host: string,
    port: number,
    timeout: number
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const startTime = Date.now()
      const url = `http://${host}:${port}/`

      const poll = (): void => {
        if (Date.now() - startTime > timeout) {
          reject(
            new Error(
              `Backend did not become ready within ${timeout / 1000}s. ` +
              'Check if Python dependencies are installed correctly.'
            )
          )
          return
        }

        const http = require('http')
        http
          .get(url, { timeout: 2000 }, (res: any) => {
            res.resume()
            resolve()
          })
          .on('error', () => {
            setTimeout(poll, 1000)
          })
          .on('timeout', () => {
            setTimeout(poll, 1000)
          })
      }

      // Start polling after a short delay to let the process initialize
      setTimeout(poll, 1000)
    })
  }
}
