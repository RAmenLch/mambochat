/**
 * MamboChat Desktop - Preload Script
 *
 * Exposes a safe, context-bridged API to the renderer process
 * for communicating with the main process.
 */

import { contextBridge, ipcRenderer } from 'electron'

export interface ElectronAPI {
  // Config
  config: {
    get: () => Promise<any>
    update: (config: any) => Promise<boolean>
    apply: (config: any) => Promise<boolean>
    getPath: () => Promise<string>
    onUpdated: (callback: (config: any) => void) => () => void
  }
  // Backend
  backend: {
    start: () => Promise<{ success: boolean; port?: number; error?: string }>
    stop: () => Promise<{ success: boolean }>
    restart: () => Promise<{ success: boolean; port?: number; error?: string }>
    status: () => Promise<{ running: boolean; port?: number; pid?: number; error?: string }>
    onStatusChange: (callback: (status: any) => void) => () => void
  }
  // Gateway
  gateway: {
    status: () => Promise<{ running: boolean; port?: number; host?: string; mode?: string }>
    restart: (host: string, port: number) => Promise<{ success: boolean; port?: number; error?: string }>
  }
  // App
  app: {
    getVersion: () => Promise<string>
    getPlatform: () => Promise<string>
    openDesktopSettings: () => Promise<void>
  }
  // Network
  testConnection: (url: string) => Promise<{ ok: boolean; status?: number; error?: string }>
  getNetworkAddresses: () => Promise<string[]>
  // Window
  win: {
    minimize: () => Promise<void>
    maximize: () => Promise<void>
    unmaximize: () => Promise<void>
    toggleMaximize: () => Promise<void>
    close: () => Promise<void>
  }
}

const electronAPI: ElectronAPI = {
  config: {
    get: () => ipcRenderer.invoke('config:get'),
    update: (config) => ipcRenderer.invoke('config:update', config),
    apply: (config) => ipcRenderer.invoke('config:apply', config),
    getPath: () => ipcRenderer.invoke('config:getPath'),
    onUpdated: (callback) => {
      const handler = (_event: any, config: any) => callback(config)
      ipcRenderer.on('config:updated', handler)
      return () => ipcRenderer.removeListener('config:updated', handler)
    },
  },

  backend: {
    start: () => ipcRenderer.invoke('backend:start'),
    stop: () => ipcRenderer.invoke('backend:stop'),
    restart: () => ipcRenderer.invoke('backend:restart'),
    status: () => ipcRenderer.invoke('backend:status'),
    onStatusChange: (callback) => {
      const handler = (_event: any, status: any) => callback(status)
      ipcRenderer.on('backend:status', handler)
      return () => ipcRenderer.removeListener('backend:status', handler)
    },
  },

  gateway: {
    status: () => ipcRenderer.invoke('gateway:status'),
    restart: (host, port) => ipcRenderer.invoke('gateway:restart', host, port),
  },

  app: {
    getVersion: () => ipcRenderer.invoke('app:getVersion'),
    getPlatform: () => ipcRenderer.invoke('app:getPlatform'),
    openDesktopSettings: () => ipcRenderer.invoke('desktop-settings:open'),
  },

  testConnection: (url) => ipcRenderer.invoke('test-remote-connection', url),

  getNetworkAddresses: () => ipcRenderer.invoke('get-network-addresses'),

  win: {
    minimize: () => ipcRenderer.invoke('win:minimize'),
    maximize: () => ipcRenderer.invoke('win:maximize'),
    unmaximize: () => ipcRenderer.invoke('win:unmaximize'),
    toggleMaximize: () => ipcRenderer.invoke('win:toggleMaximize'),
    close: () => ipcRenderer.invoke('win:close'),
  },
}

contextBridge.exposeInMainWorld('electronAPI', electronAPI)
