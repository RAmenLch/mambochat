/**
 * Type declarations for Electron API in the renderer process.
 *
 * These types are available globally in the renderer via TypeScript
 * project references or direct inclusion.
 */

export interface ElectronAPI {
  config: {
    get: () => Promise<AppConfig>
    update: (config: AppConfig) => Promise<boolean>
    apply: (config: AppConfig) => Promise<boolean>
    getPath: () => Promise<string>
    onUpdated: (callback: (config: AppConfig) => void) => () => void
  }
  backend: {
    start: () => Promise<BackendStartResult>
    stop: () => Promise<{ success: boolean }>
    restart: () => Promise<BackendStartResult>
    status: () => Promise<BackendStatus>
    onStatusChange: (callback: (status: BackendStatus) => void) => () => void
  }
  app: {
    getVersion: () => Promise<string>
    getPlatform: () => Promise<string>
    openDesktopSettings: () => Promise<void>
  }
  testConnection: (url: string) => Promise<{ ok: boolean; status?: number; error?: string }>
  win: {
    minimize: () => Promise<void>
    maximize: () => Promise<void>
    unmaximize: () => Promise<void>
    toggleMaximize: () => Promise<void>
    close: () => Promise<void>
  }
}

export interface AppConfig {
  mode: 'local' | 'remote'
  local: {
    pythonPath: string
    host: string
    portStart: number
    portEnd: number
  }
  remote: {
    url: string
  }
}

export interface BackendStatus {
  running: boolean
  port?: number
  pid?: number
  error?: string
  mode?: string
}

export interface BackendStartResult {
  success: boolean
  port?: number
  error?: string
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}
