import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router'

// Use hash history in Electron (file:// protocol) for proper SPA routing
// window.electronAPI is injected by preload before any renderer module executes
const isElectron = !!window.electronAPI
const history = isElectron ? createWebHashHistory() : createWebHistory(import.meta.env.BASE_URL)

const router = createRouter({
  history,
  routes: [
    {
      // 1. 根路径重定向
      // 当用户访问网站根目录 (例如 http://localhost:5173/) 时，
      // 自动跳转到聊天界面。
      path: '/',
      redirect: '/chat'
    },
    {
      // 2. 聊天页面路由
      // 使用了动态参数 ':chatId?'，这使得此路由可以匹配两种路径：
      // - /chat (当用户还未选择任何会话时)
      // - /chat/some-chat-id (当用户点击并进入某个特定会话时)
      path: '/chat/:chatId?',
      name: 'chat',
      // 使用动态导入 (lazy-loading) 来加载视图组件。
      // 这意味着 ChatView.vue 的代码只会在用户访问 /chat 路径时才被下载，
      // 有助于提升应用的初始加载速度。
      component: () => import('@/views/ChatView.vue'),
      // `props: true` 是一个非常有用的配置，它会将路由参数 (如 chatId)
      // 直接作为 props 传递给 ChatView.vue 组件。
      props: true
    },
    {
      // 3. 设置页面路由
      // 一个简单的路由，用于访问我们的AI服务商和模型管理页面。
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue')
    },
    {
      // 4. 桌面端连接配置路由 (仅 Electron 环境使用)
      path: '/connection',
      name: 'connection',
      component: () => import('@/views/SettingsView.vue'),
      props: { defaultTab: 'connection' }
    }
  ]
})

export default router
