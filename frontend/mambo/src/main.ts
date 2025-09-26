import './assets/base.css'

// ---- 新增代码开始 ----
// 引入 Element Plus 的完整样式文件
import 'element-plus/dist/index.css'
// ---- 新增代码结束 ----

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
