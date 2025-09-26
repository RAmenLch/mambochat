import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// ---- 新增代码开始 ----
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
// ---- 新增代码结束 ----

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    vue(),

    // ---- 新增代码开始 ----
    // 配置 unplugin-auto-import 插件
    AutoImport({
      // 配置需要自动导入的库
      imports: ['vue', 'vue-router', 'pinia'],
      // 配置 Element Plus 的 API (如 ElMessage, ElNotification) 的自动导入
      resolvers: [ElementPlusResolver()],
      // 指定生成 d.ts 文件的位置，以便 TypeScript 能识别自动导入的类型
      dts: 'src/auto-imports.d.ts',
    }),

    // 配置 unplugin-vue-components 插件
    Components({
      // 配置 Element Plus 组件的按需自动导入
      resolvers: [ElementPlusResolver()],
      // 指定生成 d.ts 文件的位置
      dts: 'src/components.d.ts',
    }),
    // ---- 新增代码结束 ----
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  // ---- 新增一个 server 配置，用于代理后端 API ----
  server: {
    proxy: {
      // 将所有 /api 开头的请求代理到后端 FastAPI 服务
      '/api': {
        target: 'http://127.0.0.1:8000', // 这是您的 FastAPI 后端地址
        changeOrigin: true,
      }
    }
  }
})
