/**
 * Electron environment detection and API adaptation.
 *
 * When running inside Electron with the embedded gateway, all /api/* requests
 * are proxied by the gateway server. This means the frontend can use relative
 * paths (/api/*) for axios and SSE connections — no need to construct full URLs.
 *
 * For remote mode, the gateway proxies /api/* to the remote server URL.
 * For local mode, the gateway proxies /api/* to the local Uvicorn backend.
 *
 * This adapter simply detects the Electron environment and sets a flag.
 */

import { setApiBaseUrl } from '@/api'
import { setBackendBaseUrl } from './electronUrl'

const ELECTRON_MODE_KEY = '__mambochat_electron__'
const CONNECTION_TIMEOUT_MS = 15_000

let isElectron = false

export function detectElectron(): boolean {
  return !!(window.electronAPI)
}

/**
 * Initialize the Electron adapter.
 *
 * Returns `true` if the backend was reachable within the timeout,
 * `false` if it timed out. The caller decides what to do on timeout
 * (e.g. open desktop settings).
 */
export async function initElectronAdapter(): Promise<boolean> {
  isElectron = detectElectron()
  if (!isElectron) return true

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any)[ELECTRON_MODE_KEY] = true

  const api = window.electronAPI!
  let connected = false

  // Load config
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let config: any = null
  try {
    config = await api.config.get()
  } catch {
    // Config might not be ready yet
  }

  // In Electron with gateway, all API requests go through the gateway via relative paths.
  // The gateway handles proxying to the actual backend (local or remote).
  // So we keep the default relative baseURL '/api'.
  setApiBaseUrl('/api')
  setBackendBaseUrl('')

  // Attempt to verify backend connectivity through the gateway
  connected = await waitForBackendConnection(api, config)

  // Subscribe to config changes from desktop settings window
  // When config changes, the gateway proxy target is updated by the main process.
  // We don't need to change the baseURL since relative paths work through the gateway.
  if (api.config.onUpdated) {
    api.config.onUpdated((_newConfig) => {
      // No action needed — the gateway handles the proxy target update
    })
  }

  return connected
}

export function isElectronMode(): boolean {
  return isElectron
}

// ---------------------------------------------------------------------------
// Internal
// ---------------------------------------------------------------------------

function waitForBackendConnection(
  api: NonNullable<typeof window.electronAPI>,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config: any
): Promise<boolean> {
  return new Promise((resolve) => {
    if (!config || config.mode === 'remote') {
      // For remote mode, test via main process IPC (avoids Chromium connection issues)
      const url = config?.remote?.url
      if (!url) { resolve(false); return }
      if (api.testConnection) {
        api.testConnection(url).then((result) => {
          resolve(result.ok)
        }).catch(() => resolve(false))
      } else {
        resolve(false)
      }
      return
    }

    // Local mode: poll backend status
    const startTime = Date.now()
    const poll = async () => {
      if (Date.now() - startTime > CONNECTION_TIMEOUT_MS) {
        resolve(false)
        return
      }
      try {
        const status = await api.backend.status()
        if (status.running && status.port) {
          resolve(true)
          return
        }
      } catch {
        // ignore
      }
      setTimeout(poll, 1000)
    }
    poll()
  })
}
