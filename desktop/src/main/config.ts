/**
 * Application configuration management.
 *
 * Handles loading, saving, and validating the app config
 * stored as JSON in the user data directory.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { app } from 'electron'
import log from './log'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AppMode = 'local' | 'remote'

export interface LocalModeConfig {
  /** Path to the embedded Python executable (relative to resources or absolute) */
  pythonPath: string
  /** Host to bind the backend server */
  host: string
  /** Port range start for auto-detection */
  portStart: number
  /** Port range end for auto-detection */
  portEnd: number
  /** Whether to allow external network access */
  allowExternalAccess: boolean
  /** Port for the embedded gateway server */
  gatewayPort: number
}

export interface ApiClientConfig {
  /** Backend ID from the remote server (persisted after first registration) */
  backendId: string
  /** API key from the remote server */
  apiKey: string
  /** Local directory to expose to the remote server */
  rootDir: string
  /** Whether to auto-connect when switching to remote mode */
  autoStart: boolean
}

export interface RemoteModeConfig {
  /** Full base URL of the remote backend, e.g. "http://192.168.1.100:8000" */
  url: string
  /** API client settings for registering this PC as a remote backend */
  apiClient: ApiClientConfig
}

export interface AppConfig {
  /** Connection mode */
  mode: AppMode
  /** Local mode settings */
  local: LocalModeConfig
  /** Remote mode settings */
  remote: RemoteModeConfig
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: AppConfig = {
  mode: 'local',
  local: {
    pythonPath: 'runtime/python/python.exe',
    host: '127.0.0.1',
    portStart: 8000,
    portEnd: 8010,
    allowExternalAccess: false,
    gatewayPort: 5173,
  },
  remote: {
    url: 'http://127.0.0.1:8000',
    apiClient: {
      backendId: '',
      apiKey: '',
      rootDir: '',
      autoStart: false,
    },
  },
}

// ---------------------------------------------------------------------------
// ConfigManager
// ---------------------------------------------------------------------------

export class AppConfigManager {
  private static instance: AppConfigManager | null = null
  private configPath: string

  private constructor() {
    const userDataPath = app.getPath('userData')
    const configDir = join(userDataPath)

    if (!existsSync(configDir)) {
      mkdirSync(configDir, { recursive: true })
    }

    this.configPath = join(configDir, 'config.json')
  }

  static getInstance(): AppConfigManager {
    if (!AppConfigManager.instance) {
      AppConfigManager.instance = new AppConfigManager()
    }
    return AppConfigManager.instance
  }

  /**
   * Load configuration from disk, falling back to defaults.
   */
  load(): AppConfig {
    if (!existsSync(this.configPath)) {
      this.save(DEFAULT_CONFIG)
      return { ...DEFAULT_CONFIG }
    }

    try {
      const raw = readFileSync(this.configPath, 'utf-8')
      const parsed = JSON.parse(raw) as Partial<AppConfig>
      return this.mergeWithDefaults(parsed)
    } catch {
      log.warn('Failed to parse config file, using defaults')
      return { ...DEFAULT_CONFIG }
    }
  }

  /**
   * Save configuration to disk.
   */
  save(config: AppConfig): void {
    try {
      const dir = dirname(this.configPath)
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true })
      }
      writeFileSync(this.configPath, JSON.stringify(config, null, 2), 'utf-8')
    } catch (error) {
      log.error('Failed to save config:', error)
      throw error
    }
  }

  /**
   * Get the config file path.
   */
  getConfigPath(): string {
    return this.configPath
  }

  /**
   * Check if the config file exists on disk.
   */
  configFileExists(): boolean {
    return existsSync(this.configPath)
  }

  /**
   * Merge a partial config with defaults to ensure all fields exist.
   * Also migrates outdated paths to their current values.
   */
  private mergeWithDefaults(partial: Partial<AppConfig>): AppConfig {
    // Migrate old .venv Python path to new runtime/python structure
    let pythonPath = partial.local?.pythonPath ?? DEFAULT_CONFIG.local.pythonPath
    if (pythonPath === 'runtime/.venv/Scripts/python.exe') {
      pythonPath = DEFAULT_CONFIG.local.pythonPath
      log.info('[Config] Migrated pythonPath: runtime/.venv/Scripts/python.exe -> runtime/python/python.exe')
    }

    return {
      mode: partial.mode ?? DEFAULT_CONFIG.mode,
      local: {
        pythonPath,
        host: partial.local?.host ?? DEFAULT_CONFIG.local.host,
        portStart: partial.local?.portStart ?? DEFAULT_CONFIG.local.portStart,
        portEnd: partial.local?.portEnd ?? DEFAULT_CONFIG.local.portEnd,
        allowExternalAccess: partial.local?.allowExternalAccess ?? DEFAULT_CONFIG.local.allowExternalAccess,
        gatewayPort: partial.local?.gatewayPort ?? DEFAULT_CONFIG.local.gatewayPort,
      },
      remote: {
        url: partial.remote?.url ?? DEFAULT_CONFIG.remote.url,
        apiClient: {
          backendId: partial.remote?.apiClient?.backendId ?? DEFAULT_CONFIG.remote.apiClient.backendId,
          apiKey: partial.remote?.apiClient?.apiKey ?? DEFAULT_CONFIG.remote.apiClient.apiKey,
          rootDir: partial.remote?.apiClient?.rootDir ?? DEFAULT_CONFIG.remote.apiClient.rootDir,
          autoStart: partial.remote?.apiClient?.autoStart ?? DEFAULT_CONFIG.remote.apiClient.autoStart,
        },
      },
    }
  }
}
