// src/i18n/index.ts
import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import en from './locales/en'

const i18n = createI18n({
  legacy: false, // Composition API 模式
  globalInjection: true, // <--- 必须有这一行，模板里的 $t 才能用
  locale: 'zh-CN',
  fallbackLocale: 'en',
  messages: {
    'zh-CN': zhCN,
    en: en
  }
})

export default i18n
