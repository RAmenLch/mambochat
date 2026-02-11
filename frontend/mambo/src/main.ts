// src/main.ts
import './assets/base.css'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import i18n from './i18n'

const app = createApp(App)

app.use(createPinia())
app.use(i18n)   // <--- 调整到 router 之前
app.use(router)

app.mount('#app')
