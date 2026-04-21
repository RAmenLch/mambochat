/**
 * Electron environment detection and API adaptation.
 *
 * Non-blocking: reads config, sets initial API URL, and attempts
 * backend connection with a configurable timeout (default 15s).
 * Backend startup runs in the background; status updates arrive via IPC.
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

  ;(window as any)[ELECTRON_MODE_KEY] = true

  const api = window.electronAPI!
  let connected = false

  // Load config and set initial API URL
  let config: any = null
  try {
    config = await api.config.get()
    setInitialApiUrl(config)
  } catch {
    // Config might not be ready yet
  }

  // Attempt to verify backend connectivity
  connected = await waitForBackendConnection(api, config)

  // Subscribe to backend status changes (local mode port updates)
  api.backend.onStatusChange((status) => {
    if (status.running && status.port) {
      const baseUrl = `http://127.0.0.1:${status.port}`
      setApiBaseUrl(`${baseUrl}/api`)
      setBackendBaseUrl(baseUrl)
    }
  })

  // Subscribe to config changes from desktop settings window
  if (api.config.onUpdated) {
    api.config.onUpdated((newConfig) => {
      updateApiBaseUrl(newConfig)
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

function setInitialApiUrl(config: any): void {
  if (config.mode === 'remote') {
    const url = config.remote?.url?.replace(/\/+$/, '')
    if (url) {
      setApiBaseUrl(`${url}/api`)
      setBackendBaseUrl(url)
    }
  } else if (config.mode === 'local') {
    // Check if backend is already running
    window.electronAPI!.backend.status().then((status) => {
      if (status.running && status.port) {
        const baseUrl = `http://127.0.0.1:${status.port}`
        setApiBaseUrl(`${baseUrl}/api`)
        setBackendBaseUrl(baseUrl)
      }
    }).catch(() => {})
  }
}

function updateApiBaseUrl(config: any): void {
  if (config.mode === 'remote') {
    const url = config.remote?.url?.replace(/\/+$/, '')
    if (url) {
      setApiBaseUrl(`${url}/api`)
      setBackendBaseUrl(url)
    }
  }
}

function waitForBackendConnection(api: NonNullable<typeof window.electronAPI>, config: any): Promise<boolean> {
  return new Promise((resolve) => {
    if (!config || config.mode === 'remote') {
      // For remote mode, test via main process IPC (avoids Chromium connection issues)
      const url = config?.remote?.url
      if (!url) { resolve(false); return }
      if (api.testConnection) {
        api.testConnection(url).then((result) => {
          if (result.ok) {
            const cleanUrl = url.replace(/\/+$/, '')
            setApiBaseUrl(`${cleanUrl}/api`)
            setBackendBaseUrl(cleanUrl)
          }
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
          const baseUrl = `http://127.0.0.1:${status.port}`
          setApiBaseUrl(`${baseUrl}/api`)
          setBackendBaseUrl(baseUrl)
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
