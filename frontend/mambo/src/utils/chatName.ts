// frontend/mambo/src/utils/chatName.ts
// 会话默认标题占位 Key：新建会话时 name 存该 Key，
// 前端展示时按 Key 渲染 i18n 文本（chat.sidebar.initChatName），
// 后端据此判断会话是否尚未生成标题。

export const DEFAULT_CHAT_TITLE_KEY = '__DEFAULT_CHAT_TITLE__'

export function isDefaultChatName(name?: string | null): boolean {
  return name === DEFAULT_CHAT_TITLE_KEY
}
