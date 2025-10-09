import apiClient from './index';
import type { Chat, ChatCreate, ChatWithMessages, ChatUpdate } from './types';

/**
 * 获取会话列表
 */
export const getChats = (): Promise<Chat[]> => {
  return apiClient.get('/chats/').then(res => res.data);
};

/**
 * 创建新会话
 */
export const createChat = (chatData: ChatCreate): Promise<Chat> => {
  return apiClient.post('/chats/', chatData).then(res => res.data);
};

/**
 * 获取单个会话及其所有消息
 */
export const getChatWithMessages = (chatId: string): Promise<ChatWithMessages> => {
  // --- 核心修复：将 API 路径从 /chats/{id} 修改为 /chats/{id}/messages ---
  return apiClient.get(`/chats/${chatId}/messages`).then(res => res.data);
};

/**
 * 更新会话设置
 * @param chatId 要更新的会话ID
 * @param settings 包含更新字段的对象
 */
export const updateChatSettings = (chatId: string, settings: ChatUpdate): Promise<Chat> => {
  return apiClient.put(`/chats/${chatId}`, settings).then(res => res.data);
};


/**
 * 删除会话
 */
export const deleteChat = (chatId: string): Promise<Chat> => {
  return apiClient.delete(`/chats/${chatId}`).then(res => res.data);
};

// 注意：流式 API (/generate) 的调用方式比较特殊，
// 我们会直接在 Pinia Store 或组件中使用 @microsoft/fetch-event-source 来处理，
// 而不是通过这里的 axios 实例。
