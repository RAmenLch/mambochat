// frontend/mambo/src/api/chatService.ts

import apiClient from './index';
import type { Chat, ChatCreate, ChatWithMessages, ChatUpdate, ChatReorderItem, Message, MessageUpdate } from './types';

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

/**
 * 更新单条消息的内容 (不支持重新发送生成)。
 * "保存并发送"的流式响应由 store 层直接处理。
 * @param messageId 消息ID
 * @param data 包含新内容的对象
 */
export const updateMessage = (messageId: string, data: MessageUpdate): Promise<Message> => {
  return apiClient.put(`/messages/${messageId}`, data).then(res => res.data);
};

/**
 * 删除单条消息
 * @param messageId 消息ID
 */
export const deleteMessage = (messageId: string): Promise<Message> => {
  return apiClient.delete(`/messages/${messageId}`).then(res => res.data);
};

/**
 * 生成AI回复 (非流式)
 * @param chatId 会话ID
 * @param content 用户输入内容
 */
export const generateResponseNonStream = (chatId: string, content: string): Promise<Message> => {
    return apiClient.post(`/chats/${chatId}/generate-non-stream`, { content }).then(res => res.data);
};

/**
 * 重新生成AI回复 (非流式)
 * @param chatId 会话ID
 * @param content 对应的用户输入内容
 */
export const regenerateResponseNonStream = (chatId: string, content: string): Promise<Message> => {
    return apiClient.post(`/chats/${chatId}/regenerate-non-stream`, { content }).then(res => res.data);
};
