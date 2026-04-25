/**
 * MamboChat Desktop - Electron Main Process
 *
 * Manages the application lifecycle, embedded gateway server,
 * backend process, and renderer window.
 */

import { app, BrowserWindow, ipcMain, dialog, shell, Menu, globalShortcut, Tray, nativeImage } from 'electron'
import { join } from 'path'
import type { AppConfig } from './config'
import { AppConfigManager } from './config'
import { BackendProcessManager } from './backend'
import { GatewayServer } from './gateway'
import { openDesktopSettings, setupDesktopSettingsIpc } from './desktopSettings'
import {DesktopLocale, getDesktopLocale, translate} from './i18n'
import log, { getLogPath } from './log'
import { setupDataDirectories } from './paths'

// Remove the default Electron application menu
Menu.setApplicationMenu(null)

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null
let isQuitting = false

// --- Single instance lock ---
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
}

// When a second instance is launched (e.g. double-clicking the shortcut),
// show the existing window instead of starting a new instance.
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  }
})

// ---------------------------------------------------------------------------
// Icon & Tray helpers
// ---------------------------------------------------------------------------

function resolveIconPath(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'frontend', 'dist', 'logo.ico')
  }
  return join(app.getAppPath(), '..', 'frontend', 'mambo', 'public', 'logo.ico')
}

function createSystemTray(iconPath: string, locale: DesktopLocale): void {
  const icon = nativeImage.createFromPath(iconPath)
  tray = new Tray(icon.resize({ width: 16, height: 16 }))
  tray.setToolTip('MamboChat')
  tray.setContextMenu(Menu.buildFromTemplate([
    {
      label: translate(locale, 'tray.show'),
      click: () => {
        if (mainWindow) {
          if (mainWindow.isMinimized()) mainWindow.restore()
          mainWindow.show()
          mainWindow.focus()
        }
      },
    },
    { type: 'separator' },
    {
      label: translate(locale, 'tray.quit'),
      click: () => {
        isQuitting = true
        app.quit()
      },
    },
  ]))
  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
    }
  })
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

async function bootstrap(): Promise<void> {
  const locale = getDesktopLocale()
  const configManager = AppConfigManager.getInstance()
  const config = configManager.load()
  const gateway = GatewayServer.getInstance()

  // Set up persistent data directories (junctions) before anything else.
  // This ensures DB/uploads survive uninstalls. No-op in dev mode.
  setupDataDirectories()

  // NOTE: Connection: close for Docker port forwarding is handled inside
  // the gateway's proxyRequest() — NOT here. Modifying request headers
  // via onBeforeSendHeaders causes "Parse Error" because Chromium
  // assembles the raw HTTP/1.1 request with its own Connection semantics.

  // Register IPC handlers BEFORE creating window,
  // so renderer can invoke them immediately after load
  setupIpcHandlers(configManager, locale)

  // Start the gateway server
  const gatewayHost = config.mode === 'local' && config.local.allowExternalAccess
    ? '0.0.0.0'
    : '127.0.0.1'
  const gatewayPort = config.local.gatewayPort || 5173

  try {
    const actualGatewayPort = await gateway.start(gatewayHost, gatewayPort)
    log.info(`[Main] Gateway started on port ${actualGatewayPort}`)
  } catch (error) {
    log.error('[Main] Failed to start gateway:', error)
  }

  // Configure gateway proxy target based on mode
  if (config.mode === 'remote') {
    gateway.setMode('remote')
    gateway.setBackendTarget(config.remote.url)
  } else {
    gateway.setMode('local')
    // Backend target will be set once backend starts
  }

  // Create main window
  mainWindow = await createMainWindow()

  // Set window icon and create system tray
  const iconPath = resolveIconPath()
  mainWindow.setIcon(nativeImage.createFromPath(iconPath))
  createSystemTray(iconPath, locale)

  // Register global shortcut to open desktop settings (Ctrl+,)
  globalShortcut.register('CommandOrControl+,', () => {
    openDesktopSettings()
  })

  // Start local backend if configured (non-blocking for window display)
  if (config.mode === 'local') {
    startLocalBackend(config)
  }

  // When the backend crashes unexpectedly, open the settings window so the user can see what happened
  BackendProcessManager.getInstance().onUnexpectedExit = () => {
    openDesktopSettings()
  }
}

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------

async function createMainWindow(): Promise<BrowserWindow> {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#f5f7fa',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // Show window once the DOM is ready (avoids white flash)
  mainWindow.webContents.once('did-finish-load', () => {
    mainWindow!.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // Minimize to system tray on close instead of quitting
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      mainWindow?.hide()
    }
  })

  // Load the frontend through the gateway server
  const gatewayUrl = GatewayServer.getInstance().getUrl()
  if (gatewayUrl) {
    log.info(`[Main] Loading frontend via gateway: ${gatewayUrl}`)
    await mainWindow.loadURL(gatewayUrl)
  } else {
    // Fallback: load from disk if gateway failed to start
    log.warn('[Main] Gateway not available, loading from disk')
    if (app.isPackaged) {
      const frontendDist = join(process.resourcesPath, 'frontend', 'dist', 'index.html')
      await mainWindow.loadFile(frontendDist)
    } else {
      // Dev fallback: try Vite dev server
      const frontendDevUrl = process.env['FRONTEND_DEV_URL'] || 'http://localhost:5173'
      await mainWindow.loadURL(frontendDevUrl)
    }
  }

  return mainWindow
}

// ---------------------------------------------------------------------------
// Backend management
// ---------------------------------------------------------------------------

function startLocalBackend(config: AppConfig): void {
  const manager = BackendProcessManager.getInstance()
  const gateway = GatewayServer.getInstance()

  // Tell the gateway that backend is starting so it can return 503 instead of 502
  gateway.setBackendStarting()

  manager.start(config).then((port) => {
    // Set gateway proxy target to local backend
    gateway.setBackendTarget(`http://127.0.0.1:${port}`)
  }).catch((error) => {
    log.error('Failed to start local backend:', error)
  })
}

// ---------------------------------------------------------------------------
// IPC Handlers
// ---------------------------------------------------------------------------

function setupIpcHandlers(configManager: AppConfigManager, locale: DesktopLocale): void {
  ipcMain.handle('config:get', () => configManager.load())
  ipcMain.handle('config:update', (_event, newConfig: AppConfig) => {
    configManager.save(newConfig)
    return true
  })

  ipcMain.handle('backend:start', async () => {
    const config = configManager.load()
    if (config.mode !== 'local') {
      return { success: false, error: translate(locale, 'error.backendControlLocalOnly') }
    }
    try {
      const port = await BackendProcessManager.getInstance().start(config)
      // Update gateway proxy target
      GatewayServer.getInstance().setBackendTarget(`http://127.0.0.1:${port}`)
      return { success: true, port }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('backend:stop', async () => {
    await BackendProcessManager.getInstance().stop()
    return { success: true }
  })

  ipcMain.handle('backend:restart', async () => {
    const config = configManager.load()
    if (config.mode !== 'local') {
      return { success: false, error: translate(locale, 'error.backendControlLocalOnly') }
    }
    const manager = BackendProcessManager.getInstance()
    try {
      await manager.stop()
      const port = await manager.start(config)
      // Update gateway proxy target
      GatewayServer.getInstance().setBackendTarget(`http://127.0.0.1:${port}`)
      return { success: true, port }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('backend:status', () => {
    return BackendProcessManager.getInstance().getStatus()
  })

  ipcMain.handle('app:getVersion', () => app.getVersion())
  ipcMain.handle('app:getPlatform', () => process.platform)
  ipcMain.handle('app:getLogPath', () => getLogPath())

  // Gateway control
  ipcMain.handle('gateway:status', () => {
    return GatewayServer.getInstance().getStatus()
  })

  ipcMain.handle('gateway:restart', async (_event, host: string, port: number) => {
    const gateway = GatewayServer.getInstance()
    const config = configManager.load()
    try {
      await gateway.stop()
      const actualPort = await gateway.start(host, port)

      // Re-configure proxy target based on current mode
      if (config.mode === 'remote') {
        gateway.setMode('remote')
        gateway.setBackendTarget(config.remote.url)
      } else {
        gateway.setMode('local')
        const backendPort = BackendProcessManager.getInstance().getPort()
        if (backendPort) {
          gateway.setBackendTarget(`http://127.0.0.1:${backendPort}`)
        }
      }

      // Reload main window to connect to new gateway
      if (mainWindow && !mainWindow.isDestroyed()) {
        const url = gateway.getUrl()
        if (url) {
          await mainWindow.loadURL(url)
        }
      }

      return { success: true, port: actualPort }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  // Window controls
  ipcMain.handle('win:minimize', () => {
    const win = BrowserWindow.getFocusedWindow()
    win?.minimize()
  })
  ipcMain.handle('win:maximize', () => {
    const win = BrowserWindow.getFocusedWindow()
    win?.maximize()
  })
  ipcMain.handle('win:unmaximize', () => {
    const win = BrowserWindow.getFocusedWindow()
    win?.unmaximize()
  })
  ipcMain.handle('win:toggleMaximize', () => {
    const win = BrowserWindow.getFocusedWindow()
    if (win?.isMaximized()) {
      win.unmaximize()
    } else {
      win?.maximize()
    }
  })
  ipcMain.handle('win:close', () => {
    const win = BrowserWindow.getFocusedWindow()
    win?.close()
  })

  setupDesktopSettingsIpc(configManager, () => mainWindow)
}

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------

app.whenReady().then(bootstrap)

app.on('window-all-closed', () => {
  // Keep running in system tray — don't quit
})

app.on('activate', async () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show()
    mainWindow.focus()
  } else {
    mainWindow = await createMainWindow()
    const iconPath = resolveIconPath()
    mainWindow.setIcon(nativeImage.createFromPath(iconPath))
    createSystemTray(iconPath, getDesktopLocale())
  }
})

app.on('before-quit', async () => {
  isQuitting = true
  await BackendProcessManager.getInstance().stop()
  GatewayServer.getInstance().stop()
  globalShortcut.unregisterAll()
})
