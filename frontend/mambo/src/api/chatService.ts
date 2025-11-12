// frontend/mambo/src/api/chatService.ts

import apiClient from './index';
import type {
  Chat,
  ChatCreate,
  ChatWithMessages,
  ChatUpdate,
  ChatReorderItem,
  Message,
  MessageUpdate,
  SubMessage,
  SubMessageUpdate,
  GenerateRequest,
  PrepareGenerateResponse,
  FileResponse
} from './types';

/**
 * 获取会话和文件夹列表
 */
export const getChats = (): Promise<Chat[]> => {
  return apiClient.get('/chats/')
};

/**
 * 创建新会话或文件夹
 */
export const createChat = (chatData: ChatCreate): Promise<Chat> => {
  return apiClient.post('/chats/', chatData)
};

/**
 * 获取单个会话及其所有消息
 */
export const getChatWithMessages = (chatId: string): Promise<ChatWithMessages> => {
  return apiClient.get(`/chats/${chatId}/messages`)
};

/**
 * 更新会话或文件夹设置
 */
export const updateChatSettings = (itemId: string, settings: ChatUpdate): Promise<Chat> => {
  return apiClient.put(`/chats/${itemId}`, settings)
};

/**
 * 删除会话或文件夹
 */
export const deleteChat = (itemId: string): Promise<Chat> => {
  return apiClient.delete(`/chats/${itemId}`)
};

/**
 * 复制会话
 */
export const duplicateChat = (chatId: string): Promise<Chat> => {
  return apiClient.post(`/chats/${chatId}/duplicate`)
};

/**
 * 批量更新会话和文件夹的排序与层级
 */
export const reorderChats = (updates: ChatReorderItem[]): Promise<{ message: string }> => {
  return apiClient.post('/chats/reorder', updates)
}

/**
 * 更新整条消息（替换其所有子消息），并可选择触发重新生成。
 * @param messageId 消息ID
 * @param data 包含新的子消息列表和resend标志的对象
 */
export const updateMessageAndRegenerate = (messageId: string, data: MessageUpdate): Promise<Message> => {
  return apiClient.put(`/messages/${messageId}`, data)
};

/**
 * 更新单个消息分区的内容或配置，此操作不触发重新生成。
 * @param subMessageId 子消息ID
 * @param data 包含要更新的 content 或 config 的对象
 */
export const updateSubMessage = (subMessageId: string, data: SubMessageUpdate): Promise<SubMessage> => {
  return apiClient.put(`/sub-messages/${subMessageId}`, data)
};

/**
 * 删除单条消息
 */
export const deleteMessage = (messageId: string): Promise<Message> => {
  return apiClient.delete(`/messages/${messageId}`)
};

/**
 * 上传单个文件到服务器。
 * @param file 用户选择的 File 对象。
 * @returns 返回已上传文件的元数据。
 */
export const uploadFile = (file: File): Promise<FileResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  // 解决方案：在此处为本次请求单独覆盖 Content-Type
  // 这会覆盖 apiClient 实例的全局默认 'application/json' 设置
  return apiClient.post('/files/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

/**
 * 准备并开始生成AI回复。
 * @returns 返回包含新用户消息和AI助手占位符消息的对象。
 */
export const prepareGenerate = (chatId: string, data: GenerateRequest): Promise<PrepareGenerateResponse> => {
  return apiClient.post(`/chats/${chatId}/prepare-generate`, data)
};

/**
 * 准备并开始重新生成AI回复。
 * @returns 返回一个状态为 'generating' 的 assistant 消息对象作为占位符。
 */
export const prepareRegenerate = (chatId: string, fromMessageId: string): Promise<Message> => {
  return apiClient.post(`/chats/${chatId}/prepare-regenerate/${fromMessageId}`)
};

/**
 * 请求服务器停止指定消息的AI生成任务。
 */
export const stopGeneration = (messageId: string): Promise<{ message: string }> => {
  return apiClient.post(`/messages/${messageId}/stop`)
};

/**
 * 为指定的会话异步触发一个后台任务，以根据其内容自动生成标题。
 */
export const generateChatTitle = (chatId: string): Promise<{ message: string }> => {
  return apiClient.post(`/chats/${chatId}/generate-title`)
};
