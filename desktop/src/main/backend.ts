/**
 * Backend process manager for local mode.
 *
 * Manages the lifecycle of the Python backend process:
 * - Port detection and allocation
 * - Process spawning with correct environment
 * - Health check polling until ready
 * - Graceful shutdown
 */

import { spawn, ChildProcess } from 'child_process'
import { createServer, createConnection } from 'net'
import { app } from 'electron'
import { join, isAbsolute } from 'path'
import type { AppConfig } from './config'

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
    console.log(`[Backend] Starting on port ${port}...`)
    console.log(`[Backend] Python: ${exePath}`)
    console.log(`[Backend] WorkDir: ${appDir}`)

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
      if (msg) console.log(`[Backend:OUT] ${msg}`)
    })

    this.process.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString().trim()
      if (msg) console.warn(`[Backend:ERR] ${msg}`)
    })

    this.process.on('error', (err) => {
      console.error('[Backend] Process error:', err.message)
      this.process = null
      this.currentPort = null
    })

    this.process.on('exit', (code, signal) => {
      console.log(`[Backend] Process exited (code=${code}, signal=${signal})`)
      this.process = null
      this.currentPort = null
    })

    // 6. Wait for backend to become ready
    await this.waitForReady(bindHost === '0.0.0.0' ? '127.0.0.1' : bindHost, port, 30_000)

    this.currentPort = port
    console.log(`[Backend] Ready on port ${port}`)
    return port
  }

  /**
   * Stop the backend process gracefully.
   */
  stop(): void {
    if (this.process) {
      console.log(`[Backend] Stopping (PID: ${this.process.pid})...`)
      this.process.kill('SIGTERM')

      // Force kill after timeout
      const pid = this.process.pid
      setTimeout(() => {
        try {
          process.kill(pid!, 'SIGKILL')
        } catch {
          // Process already dead
        }
      }, 5000)

      this.process = null
      this.currentPort = null
    }
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
