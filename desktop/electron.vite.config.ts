import { fileURLToPath, URL } from 'node:url'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin({ exclude: ['electron-log'] })],
    build: {
      outDir: 'dist/main',
      rollupOptions: {
        input: {
          index: fileURLToPath(new URL('src/main/index.ts', import.meta.url)),
        },
      },
    },
    resolve: {
      alias: {
        '@main': fileURLToPath(new URL('src/main', import.meta.url)),
      },
    },
  },

  preload: {
    plugins: [externalizeDepsPlugin({ exclude: ['electron-log'] })],
    build: {
      outDir: 'dist/preload',
      rollupOptions: {
        input: {
          index: fileURLToPath(new URL('src/preload/index.ts', import.meta.url)),
        },
      },
    },
    resolve: {
      alias: {
        '@preload': fileURLToPath(new URL('src/preload', import.meta.url)),
      },
    },
  },

  /**
   * Minimal renderer stub — electron-vite requires it, but we don't use it.
   * The actual Vue app is loaded directly from the frontend dev server (dev)
   * or from the frontend build output (prod).
   */
  renderer: {
    root: fileURLToPath(new URL('src/renderer', import.meta.url)),
    build: {
      outDir: fileURLToPath(new URL('dist/renderer', import.meta.url)),
    },
  },
})
