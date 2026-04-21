/**
 * Type declarations for the Electron API exposed via preload script.
 * This file is imported in the renderer process.
 */

export interface ElectronAPI {
  config: {
    get: () => Promise<import('../main/config').AppConfig>
    update: (config: import('../main/config').AppConfig) => Promise<boolean>
    apply: (config: import('../main/config').AppConfig) => Promise<boolean>
    getPath: () => Promise<string>
    onUpdated: (callback: (config: import('../main/config').AppConfig) => void) => () => void
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
  win: {
    minimize: () => Promise<void>
    maximize: () => Promise<void>
    unmaximize: () => Promise<void>
    toggleMaximize: () => Promise<void>
    close: () => Promise<void>
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
