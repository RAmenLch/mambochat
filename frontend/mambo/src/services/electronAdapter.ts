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
 * This adapter also manages the splash screen during first-launch runtime
 * extraction, providing locale-aware progress text before vue-i18n is ready.
 */

import { setApiBaseUrl } from '@/api'
import { setBackendBaseUrl } from './electronUrl'

const ELECTRON_MODE_KEY = '__mambochat_electron__'
/** Timeout for backend connectivity — only starts after extraction is done */
const CONNECTION_TIMEOUT_MS = 60_000

let isElectron = false
/** The detected app mode ('local' | 'remote'), available after initElectronAdapter() */
export let backendMode: string | null = null
/**
 * Background connectivity probe for remote mode (non-blocking).
 * Set during initElectronAdapter() when the app runs in remote mode with a
 * configured URL; resolves `true` if the remote server is reachable.
 * `null` when not in remote mode or the probe was never started.
 */
export let remoteReachability: Promise<boolean> | null = null

export function detectElectron(): boolean {
  return !!(window.electronAPI)
}

// ---------------------------------------------------------------------------
// Locale-aware splash texts (used before vue-i18n is ready)
// ---------------------------------------------------------------------------

const SPLASH_TEXTS = {
  zh: {
    extraction: '第一次启动 · 初始化运行环境',
    startingBackend: '正在启动后端服务...',
    connecting: '正在连接服务器...',
  },
  en: {
    extraction: 'First launch · Initializing runtime',
    startingBackend: 'Starting backend...',
    connecting: 'Connecting to server...',
  },
} as const

function getSplashLocale(): 'zh' | 'en' {
  const lang = navigator.language || 'zh-CN'
  return lang.startsWith('zh') ? 'zh' : 'en'
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

  // Subscribe to extraction progress BEFORE any async operations so we
  // don't miss early events ('checking', 'counting') from the main process.
  // This also handles updating the splash screen UI.
  const extractionDone = waitForExtractionDone(api)

  // Load config
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let config: any = null
  try {
    config = await api.config.get()
  } catch {
    // Config might not be ready yet
  }

  // Expose mode so main.ts can choose the right splash text
  backendMode = config?.mode || null

  // In Electron with gateway, all API requests go through the gateway via relative paths.
  // The gateway handles proxying to the actual backend (local or remote).
  // So we keep the default relative baseURL '/api'.
  setApiBaseUrl('/api')
  setBackendBaseUrl('')

  // Wait for runtime extraction to complete before starting the connection timeout.
  // The extraction progress is shown in the splash screen; we only start timing
  // the backend connection once extraction is done.
  //
  // Remote mode never starts the local backend, so runtime extraction can never
  // happen — the 2s safety timeout inside waitForExtractionDone() would always
  // fire on every start/refresh, adding a fixed delay. Skip the wait entirely
  // in remote mode.
  //
  // Local mode: the main process answers authoritatively whether the python
  // runtime is already extracted (stamp file). On start/refresh after the
  // first launch it is — and no extraction events are ever broadcast, so the
  // 2s safety timeout would otherwise fire for nothing. Only wait when the
  // runtime is NOT yet extracted (very first launch, extraction in progress).
  if (backendMode !== 'remote') {
    const extractionReady = await api.runtime.isExtractionReady?.().catch(() => false) ?? false
    if (!extractionReady) {
      await extractionDone
    }
  }

  // Attempt to verify backend connectivity through the gateway
  const connected = await waitForBackendConnection(api, config)

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

/**
 * Wait for the runtime extraction phase to complete (if applicable).
 * Also manages the splash screen UI with locale-aware text.
 *
 * Returns immediately if there is no extraction in progress or already done.
 *
 * If we never receive any progress event at all, we assume extraction is not
 * happening (e.g. dev mode, or already extracted) and resolve after a short
 * delay.  But once we receive at least one event, we wait until 'done' or
 * 'error' — there is no fixed timeout because extraction can take minutes.
 */
function waitForExtractionDone(api: NonNullable<typeof window.electronAPI>): Promise<void> {
  return new Promise((resolve) => {
    // If no runtime API, nothing to wait for
    if (!api.runtime?.onExtractionProgress) {
      resolve()
      return
    }

    let settled = false
    let receivedAnyEvent = false
    const texts = SPLASH_TEXTS[getSplashLocale()]

    const textEl = document.getElementById('splash-text')
    const progressEl = document.getElementById('splash-progress')
    const progressBar = document.getElementById('splash-progress-bar')

    // Safety timeout: only fires if NO progress events were ever received.
    // Once extraction events start arriving, we clear this and wait indefinitely
    // for the actual done/error phase.
    const safetyTimer = setTimeout(() => {
      if (!settled && !receivedAnyEvent) {
        settled = true
        unsubscribe()
        resolve()
      }
    }, 2_000)

    const unsubscribe = api.runtime.onExtractionProgress((progress) => {
      receivedAnyEvent = true

      // Once we know extraction is in progress, cancel the safety timeout
      // so we don't prematurely resolve while files are still being extracted.
      if (!settled) {
        clearTimeout(safetyTimer)
      }

      // Update splash UI with locale-aware text
      switch (progress.phase) {
        case 'checking':
        case 'counting':
          if (textEl) textEl.textContent = texts.extraction + '...'
          break
        case 'extracting':
          if (textEl) {
            textEl.textContent = progress.percent > 0
              ? `${texts.extraction} ${progress.percent}%`
              : texts.extraction + '...'
          }
          if (progressEl) progressEl.classList.add('visible')
          if (progressBar) progressBar.style.width = progress.percent + '%'
          break
        case 'done':
          // Transition to backend-starting text (vue-i18n will refine later)
          if (textEl) textEl.textContent = texts.startingBackend
          if (progressEl) progressEl.classList.remove('visible')
          break
        case 'error':
          if (textEl) textEl.textContent = String(progress.detail)
          if (progressEl) progressEl.classList.remove('visible')
          break
      }

      if (progress.phase === 'done' || progress.phase === 'error') {
        if (!settled) {
          settled = true
          unsubscribe()
          resolve()
        }
      }
    })
  })
}

function waitForBackendConnection(
  api: NonNullable<typeof window.electronAPI>,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config: any
): Promise<boolean> {
  return new Promise((resolve) => {
    if (!config || config.mode === 'remote') {
      // Remote mode: don't block app mount on a connectivity pre-check —
      // the gateway proxies every /api/* request and surfaces failures as
      // HTTP errors anyway. Resolve immediately and run the probe in the
      // background so an unreachable server can still open the settings window.
      const url = config?.remote?.url
      if (!url) { resolve(false); return }
      if (api.testConnection) {
        remoteReachability = api.testConnection(url)
          .then((result) => result.ok)
          .catch(() => false)
      } else {
        remoteReachability = Promise.resolve(false)
      }
      resolve(true)
      return
    }

    // Local mode: poll backend status
    // Use a generous timeout to accommodate first-launch runtime extraction
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
      setTimeout(poll, 300)
    }
    poll()
  })
}
