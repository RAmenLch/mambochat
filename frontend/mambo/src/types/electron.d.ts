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
  runtime: {
    onExtractionProgress: (callback: (progress: ExtractionProgress) => void) => () => void
    isExtractionReady: () => Promise<boolean>
  }
  gateway: {
    status: () => Promise<GatewayStatus>
    restart: (host: string, port: number) => Promise<{ success: boolean; port?: number; error?: string }>
  }
  data: {
    selectDir: () => Promise<string | null>
    getPath: () => Promise<string>
    chooseMigration: (to: string) => Promise<'migrate' | 'migrateAndDelete' | 'useTarget' | 'cancel'>
    migrate: (to: string, deleteOld: boolean) => Promise<{ success: boolean; from?: string; to?: string; copied?: number; error?: string }>
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
    allowExternalAccess?: boolean
    gatewayPort?: number
    dataDir?: string
  }
  remote: {
    url: string
  }
}

export interface BackendStatus {
  running: boolean
  starting?: boolean
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

export interface ExtractionProgress {
  phase: 'checking' | 'counting' | 'extracting' | 'done' | 'error'
  percent: number
  detail: string
}

export interface GatewayStatus {
  running: boolean
  port?: number
  host?: string
  mode?: string
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}
