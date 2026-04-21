/**
 * Frontend Vite dev server manager.
 *
 * In development mode, Electron spawns and manages the Vite dev server
 * so that the "Allow external network access" toggle can control
 * whether the frontend binds to 0.0.0.0 or 127.0.0.1.
 */

import { spawn, ChildProcess } from 'child_process'
import { createServer } from 'net'
import { app } from 'electron'
import { join } from 'path'
import http from 'http'

const FRONTEND_PORT = 5173

export class FrontendDevServerManager {
  private static instance: FrontendDevServerManager | null = null
  private process: ChildProcess | null = null
  private currentHost: string = '127.0.0.1'

  private constructor() {}

  static getInstance(): FrontendDevServerManager {
    if (!FrontendDevServerManager.instance) {
      FrontendDevServerManager.instance = new FrontendDevServerManager()
    }
    return FrontendDevServerManager.instance
  }

  /**
   * Start the Vite dev server.
   * If the port is already in use (e.g. user started frontend manually), reuses it.
   */
  async start(host: string): Promise<number> {
    // Check if port is already in use (user may have started frontend manually)
    if (await this.isPortInUse(FRONTEND_PORT)) {
      console.log(`[Frontend] Port ${FRONTEND_PORT} already in use, reusing existing server`)
      this.currentHost = host
      return FRONTEND_PORT
    }

    this.currentHost = host
    const frontendDir = this.resolveFrontendDir()

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Frontend dev server start timed out'))
      }, 30_000)

      this.process = spawn(
        'npx',
        ['vite', '--host', host, '--port', String(FRONTEND_PORT)],
        {
          cwd: frontendDir,
          stdio: ['pipe', 'pipe', 'pipe'],
          shell: true,
          env: { ...process.env },
        }
      )

      this.process.stdout?.on('data', (data: Buffer) => {
        const msg = data.toString().trim()
        if (msg) console.log(`[Frontend:OUT] ${msg}`)
      })

      this.process.stderr?.on('data', (data: Buffer) => {
        const msg = data.toString().trim()
        if (msg) console.warn(`[Frontend:ERR] ${msg}`)
      })

      this.process.on('error', (err) => {
        clearTimeout(timeout)
        console.error('[Frontend] Process error:', err.message)
        this.process = null
        reject(err)
      })

      this.process.on('exit', (code, signal) => {
        console.log(`[Frontend] Process exited (code=${code}, signal=${signal})`)
        this.process = null
      })

      // Wait for Vite to be ready
      this.waitForReady(host, FRONTEND_PORT, 30_000)
        .then(() => {
          clearTimeout(timeout)
          resolve(FRONTEND_PORT)
        })
        .catch((err) => {
          clearTimeout(timeout)
          reject(err)
        })
    })
  }

  /**
   * Stop the Vite dev server.
   */
  stop(): void {
    if (this.process) {
      console.log('[Frontend] Stopping...')
      this.process.kill('SIGTERM')
      const pid = this.process.pid
      setTimeout(() => {
        try {
          process.kill(pid!, 'SIGKILL')
        } catch {
          // already dead
        }
      }, 5000)
      this.process = null
    }
  }

  /**
   * Restart the Vite dev server with a (possibly new) host.
   */
  async restart(host: string): Promise<number> {
    this.stop()
    // Wait for the port to be released
    await new Promise((resolve) => setTimeout(resolve, 1000))
    return this.start(host)
  }

  /**
   * Get current frontend dev server status.
   */
  getStatus(): { running: boolean; host?: string; port?: number } {
    return {
      running: this.process !== null,
      host: this.currentHost,
      port: FRONTEND_PORT,
    }
  }

  // ---------------------------------------------------------------------------
  // Private helpers
  // ---------------------------------------------------------------------------

  private resolveFrontendDir(): string {
    return join(app.getAppPath(), '..', 'frontend', 'mambo')
  }

  private isPortInUse(port: number): Promise<boolean> {
    return new Promise((resolve) => {
      const server = createServer()
      server.once('error', () => {
        server.close()
        resolve(true)
      })
      server.once('listening', () => {
        server.close()
        resolve(false)
      })
      server.listen(port, '127.0.0.1')
    })
  }

  private waitForReady(host: string, port: number, timeout: number): Promise<void> {
    return new Promise((resolve, reject) => {
      const startTime = Date.now()
      const testHost = host === '0.0.0.0' ? '127.0.0.1' : host

      const poll = (): void => {
        if (Date.now() - startTime > timeout) {
          reject(new Error(`Frontend dev server did not become ready within ${timeout / 1000}s`))
          return
        }
        http
          .get(`http://${testHost}:${port}/`, { timeout: 2000 }, (res: any) => {
            res.resume()
            resolve()
          })
          .on('error', () => setTimeout(poll, 1000))
          .on('timeout', () => setTimeout(poll, 1000))
      }

      setTimeout(poll, 1000)
    })
  }
}
