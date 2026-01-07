import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    AutoImport({
      imports: ['vue', 'vue-router', 'pinia'],
      resolvers: [ElementPlusResolver()],
      dts: 'src/auto-imports.d.ts',
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: 'src/components.d.ts',
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  },
  // ---- 新增构建配置开始 ----
  build: {
    rollupOptions: {
      output: {
        // manualChunks 强制将特定库拆分成独立 chunk
        manualChunks(id) {
          // 如果路径中包含 gpt-tokenizer，将其打包成名为 gpt-tokenizer-xxxx.js 的独立文件
          if (id.includes('node_modules/gpt-tokenizer')) {
            return 'gpt-tokenizer';
          }
        },
      },
    },
  },
  // ---- 新增构建配置结束 ----
})
