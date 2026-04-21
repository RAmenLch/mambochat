// src/main.ts
import './assets/base.css'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { initElectronAdapter, isElectronMode } from './services/electronAdapter'

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
    if (splashText) splashText.textContent = 'Connection timed out'
    // Small delay so the user sees the timeout message before settings open
    await new Promise(r => setTimeout(r, 600))
    window.electronAPI?.app?.openDesktopSettings()
  }

  const app = createApp(App)
  app.use(createPinia())
  app.use(i18n)
  app.use(router)
  app.mount('#app')

  // Dismiss splash screen
  dismissSplash()
}

bootstrap()
