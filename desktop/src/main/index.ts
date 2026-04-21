/**
 * MamboChat Desktop - Electron Main Process
 *
 * Manages the application lifecycle, backend process,
 * and renderer window.
 */

import { app, BrowserWindow, ipcMain, dialog, shell, Menu, globalShortcut, session } from 'electron'
import { join } from 'path'
import type { AppConfig } from './config'
import { AppConfigManager } from './config'
import { BackendProcessManager } from './backend'
import { openDesktopSettings, setupDesktopSettingsIpc } from './desktopSettings'

// Remove the default Electron application menu
Menu.setApplicationMenu(null)

let mainWindow: BrowserWindow | null = null

// --- Single instance lock ---
const gotTheLock = app.requestSingleInstanceLock()
if (!gotTheLock) {
  app.quit()
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

async function bootstrap(): Promise<void> {
  const configManager = AppConfigManager.getInstance()
  const config = configManager.load()

  // Force Connection: close on all non-SSE HTTP requests to prevent connection pool
  // exhaustion with Docker port forwarding (ERR_CONNECTION_RESET on Windows).
  // SSE streams (EventSource) must be excluded — they require persistent connections.
  session.defaultSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const url = details.url
    // Exclude SSE/stream endpoints — they need persistent connections
    if (url.includes('/stream-response') || url.includes('/notifications/subscribe')) {
      callback({ requestHeaders: details.requestHeaders })
      return
    }
    details.requestHeaders['Connection'] = 'close'
    callback({ requestHeaders: details.requestHeaders })
  })

  // Register IPC handlers BEFORE creating window,
  // so renderer can invoke them immediately after load
  setupIpcHandlers(configManager)

  // Create main window
  mainWindow = await createMainWindow()

  // Register global shortcut to open desktop settings (Ctrl+,)
  globalShortcut.register('CommandOrControl+,', () => {
    openDesktopSettings()
  })

  // Start local backend if configured (non-blocking for window display)
  if (config.mode === 'local') {
    startLocalBackground(config)
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
    mainWindow!.webContents.openDevTools()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // Load the Vue frontend app
  if (!app.isPackaged) {
    const frontendDevUrl = process.env['FRONTEND_DEV_URL'] || 'http://localhost:5173'
    console.log(`[Main] Loading frontend dev server: ${frontendDevUrl}`)
    await mainWindow.loadURL(frontendDevUrl)
  } else {
    const frontendDist = join(process.resourcesPath, 'frontend', 'dist', 'index.html')
    console.log(`[Main] Loading frontend dist: ${frontendDist}`)
    await mainWindow.loadFile(frontendDist)
  }

  return mainWindow
}

// ---------------------------------------------------------------------------
// Backend management
// ---------------------------------------------------------------------------

function startLocalBackground(config: AppConfig): void {
  const manager = BackendProcessManager.getInstance()

  manager.start(config).then((port) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend:status', {
        running: true,
        port,
        mode: 'local',
      })
    }
  }).catch((error) => {
    console.error('Failed to start local backend:', error)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('backend:status', {
        running: false,
        error: String(error),
        mode: 'local',
      })
    }
  })
}

// ---------------------------------------------------------------------------
// IPC Handlers
// ---------------------------------------------------------------------------

function setupIpcHandlers(configManager: AppConfigManager): void {
  ipcMain.handle('config:get', () => configManager.load())
  ipcMain.handle('config:update', (_event, newConfig: AppConfig) => {
    configManager.save(newConfig)
    return true
  })

  ipcMain.handle('backend:start', async () => {
    const config = configManager.load()
    if (config.mode !== 'local') {
      return { success: false, error: 'Backend control is only available in local mode' }
    }
    try {
      const port = await BackendProcessManager.getInstance().start(config)
      return { success: true, port }
    } catch (error) {
      return { success: false, error: String(error) }
    }
  })

  ipcMain.handle('backend:stop', async () => {
    BackendProcessManager.getInstance().stop()
    return { success: true }
  })

  ipcMain.handle('backend:restart', async () => {
    const config = configManager.load()
    if (config.mode !== 'local') {
      return { success: false, error: 'Backend control is only available in local mode' }
    }
    const manager = BackendProcessManager.getInstance()
    try {
      manager.stop()
      const port = await manager.start(config)
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
  BackendProcessManager.getInstance().stop()
  globalShortcut.unregisterAll()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('activate', async () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    mainWindow = await createMainWindow()
  }
})

app.on('before-quit', () => {
  BackendProcessManager.getInstance().stop()
  globalShortcut.unregisterAll()
})
