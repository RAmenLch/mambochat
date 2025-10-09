import apiClient from './index';
import type { Chat, ChatCreate, ChatWithMessages, ChatUpdate, ChatReorderItem } from './types';

/**
 * 获取会话和文件夹列表
 */
export const getChats = (): Promise<Chat[]> => {
  return apiClient.get('/chats/').then(res => res.data);
};

/**
 * 创建新会话或文件夹
 */
export const createChat = (chatData: ChatCreate): Promise<Chat> => {
  return apiClient.post('/chats/', chatData).then(res => res.data);
};

/**
 * 获取单个会话及其所有消息
 */
export const getChatWithMessages = (chatId: string): Promise<ChatWithMessages> => {
  return apiClient.get(`/chats/${chatId}/messages`).then(res => res.data);
};

/**
 * 更新会话或文件夹设置
 * @param itemId 要更新的项目ID
 * @param settings 包含更新字段的对象
 */
export const updateChatSettings = (itemId: string, settings: ChatUpdate): Promise<Chat> => {
  return apiClient.put(`/chats/${itemId}`, settings).then(res => res.data);
};


/**
 * 删除会话或文件夹
 */
export const deleteChat = (itemId: string): Promise<Chat> => {
  return apiClient.delete(`/chats/${itemId}`).then(res => res.data);
};

/**
 * 批量更新会话和文件夹的排序与层级
 * @param updates 包含更新信息的项目数组
 */
export const reorderChats = (updates: ChatReorderItem[]): Promise<{ message: string }> => {
  return apiClient.post('/chats/reorder', updates).then(res => res.data);
}
