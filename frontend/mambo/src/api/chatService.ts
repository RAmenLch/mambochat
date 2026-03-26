// frontend/mambo/src/api/chatService.ts

import apiClient from './index';
import type {
  Chat,
  ChatCreate,
  ChatWithMessages,
  ChatUpdate,
  Message,
  MoveRequest,
  MessageUpdate,
  SubMessage,
  SubMessageUpdate,
  GenerateRequest,
  PrepareGenerateResponse,
  UpdateMessageResponse,
  SearchRequest,
  SearchResponse,
  ReviewToolRequest,
  ChatDuplicateRequest,
  ChatArchiveRequest,
} from './types';

/**
 * 懒加载获取会话/文件夹子节点
 * @param parentIds 父节点ID列表，传 "root" 获取根目录
 */
export const getChatChildren = (parentIds: string[]): Promise<Chat[]> => {
  const params = new URLSearchParams();
  parentIds.forEach(id => params.append('parentIds', id));
  return apiClient.get('/chats/children', { params });
};

/**
 * 移动会话/文件夹节点
 */
export const moveChat = (data: MoveRequest): Promise<void> => {
  return apiClient.post('/chats/move', data);
};

/**
 * 获取会话链路 (用于深层链接回溯)
 */
export const getChatLineage = (chatId: string): Promise<Chat[]> => {
  return apiClient.get(`/chats/${chatId}/lineage`);
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
 * 复制会话 (支持截断复制)
 */
export const duplicateChat = (chatId: string, payload?: ChatDuplicateRequest): Promise<Chat> => {
  return apiClient.post(`/${chatId}/duplicate`, payload || {});
};

/**
 * 批量归档会话到新文件夹
 */
export const archiveChats = (data: ChatArchiveRequest): Promise<Chat> => {
  return apiClient.post('/archive', data);
};


/**
 * 更新整条消息（替换其所有子消息），并可选择触发重新生成。
 * @param messageId 消息ID
 * @param data 包含新的子消息列表和resend标志的对象
 */
export const updateMessageAndRegenerate = (messageId: string, data: MessageUpdate): Promise<UpdateMessageResponse> => {
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
 * 针对指定消息发起一个后台对话历史压缩任务。
 * @param messageId - 必须是 assistant 角色的消息ID。
 */
export const initiateHistoryCompression = (messageId: string): Promise<{ message: string }> => {
  return apiClient.post(`/messages/${messageId}/compress-history`);
};

/**
 * 为指定的会话异步触发一个后台任务，以根据其内容自动生成标题。
 */
export const generateChatTitle = (chatId: string): Promise<{ message: string }> => {
  return apiClient.post(`/chats/${chatId}/generate-title`)
};

/**
 * 全局搜索会话和消息内容
 * @param data 搜索请求参数
 * @returns 返回搜索结果
 */
export const searchChats = (data: SearchRequest): Promise<SearchResponse> => {
  return apiClient.post('/chats/search', data);
};

/**
 * 提交工具调用审核决策
 * @param messageId 主消息ID
 * @param data 审核决策数据
 */
export const submitToolReview = (messageId: string, data: ReviewToolRequest): Promise<Message> => {
  return apiClient.post(`/messages/${messageId}/review-tool`, data);
};

/**
 * 激活指定消息分支
 * @param chatId 会话ID
 * @param messageId 目标消息ID
 */
export const activateMessageBranch = (chatId: string, messageId: string): Promise<Message[]> => {
  return apiClient.put(`/chats/${chatId}/messages/${messageId}/activate`);
};
