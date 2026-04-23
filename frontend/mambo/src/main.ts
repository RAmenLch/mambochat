// src/main.ts
import './assets/base.css'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { initElectronAdapter, isElectronMode, backendMode } from './services/electronAdapter'

/**
 * Apply i18n translations to the Electron custom titlebar buttons and splash text.
 * Called after vue-i18n initializes so the correct user language is used.
 */
function applyTitlebarI18n(): void {
  const tb = document.getElementById('electron-titlebar')
  if (!tb) return
  const t = i18n.global.t
  const setAttr = (id: string, attr: string, key: string) => {
    const el = document.getElementById(id)
    if (el) el.setAttribute(attr, t(key))
  }
  const setText = (id: string, key: string) => {
    const el = document.getElementById(id)
    if (el) el.textContent = t(key)
  }
  setAttr('titlebar-reload', 'title', 'common.titlebar.reload')
  setAttr('titlebar-settings', 'title', 'common.titlebar.settings')
  setAttr('titlebar-minimize', 'title', 'common.titlebar.minimize')
  setAttr('titlebar-maximize', 'title', 'common.titlebar.maximize')
  setAttr('titlebar-close', 'title', 'common.titlebar.close')
  setText('splash-text', backendMode === 'local' ? 'common.titlebar.startingBackend' : 'common.titlebar.connecting')
  setText('splash-settings-btn', 'common.titlebar.openSettings')
}

/**
 * Dismiss the splash screen overlay with a fade-out transition.
 */
function dismissSplash(): void {
  const splash = document.getElementById('mambochat-splash')
  if (splash && splash.classList.contains('visible')) {
    splash.classList.add('fade-out')
    setTimeout(() => splash.remove(), 500)
  }
}

const bootstrap = async (): Promise<void> => {
  // Initialize Electron adapter (non-blocking with 15s timeout)
  const connected = await initElectronAdapter()

  // If connection timed out, open desktop settings so user can reconfigure
  if (isElectronMode() && !connected) {
    const splashText = document.getElementById('splash-text')
    if (splashText) {
      const baseKey = backendMode === 'local' ? 'common.titlebar.startingBackend' : 'common.titlebar.connecting'
      splashText.textContent = i18n.global.t(baseKey) + ' — timed out'
    }
    // Small delay so the user sees the timeout message before settings open
    await new Promise(r => setTimeout(r, 600))
    window.electronAPI?.app?.openDesktopSettings()
  }

  const app = createApp(App)
  app.use(createPinia())
  app.use(i18n)
  app.use(router)
  app.mount('#app')

  // Apply i18n to Electron titlebar after vue-i18n is ready
  if (isElectronMode()) applyTitlebarI18n()

  // Dismiss splash screen
  dismissSplash()
}

bootstrap()
