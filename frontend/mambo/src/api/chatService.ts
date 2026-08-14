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
  AskUserAnswerRequest,
  ChatDuplicateRequest,
  ChatArchiveRequest,
  ImportChatReport,
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
 * 导出会话为 JSON（mambochat.chat-export 可导入格式，由后端生成）
 */
export const exportChatJson = (chatId: string): Promise<Blob> => {
  return apiClient.get(`/chats/${chatId}/export`, { responseType: 'blob' });
};

/**
 * 导入会话 JSON 文件，创建为新会话（放入根目录）
 */
export const importChat = (file: File): Promise<ImportChatReport> => {
  const formData = new FormData();
  formData.append('file', file);
  // 必须显式声明 multipart：apiClient 全局默认 Content-Type 为 application/json，
  // axios 会把 FormData 序列化为 JSON 导致后端收不到 file 字段（422）
  return apiClient.post('/chats/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
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
 * 获取消息下的 TaskSubStep 子代理追踪步骤（按需加载，可按 task_group_id 过滤）。
 */
export const getMessageTaskSubSteps = (
  messageId: string,
  taskGroupId?: string,
): Promise<SubMessage[]> => {
  return apiClient.get(`/messages/${messageId}/task-substeps`, {
    params: taskGroupId ? { task_group_id: taskGroupId } : undefined,
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
 * @param chatId - 会话ID
 * @param fromMessageId - 重新生成的起点消息ID
 * @param versionRollback - 可选，版本回滚配置
 * @returns 返回一个状态为 'generating' 的 assistant 消息对象作为占位符。
 */
export const prepareRegenerate = (
  chatId: string,
  fromMessageId: string,
  versionRollback?: { files: string[] },
): Promise<Message> => {
  return apiClient.post(`/chats/${chatId}/prepare-regenerate/${fromMessageId}`, versionRollback ? { version_rollback: versionRollback } : {})
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
 * 提交 ask_user 问题回答
 * @param messageId 主消息ID
 * @param data 回答数据
 */
export const submitAskUserAnswer = (messageId: string, data: AskUserAnswerRequest): Promise<Message> => {
  return apiClient.post(`/messages/${messageId}/answer-ask-user`, data);
};

/**
 * 激活指定消息分支
 * @param chatId 会话ID
 * @param messageId 目标消息ID
 */
export const activateMessageBranch = (chatId: string, messageId: string): Promise<Message[]> => {
  return apiClient.put(`/chats/${chatId}/messages/${messageId}/activate`);
};

/**
 * 重试失败的生成任务（从 LangGraph checkpoint 恢复）
 * @param messageId 失败的 assistant 消息ID
 */
export const retryFailedGeneration = (messageId: string): Promise<Message> => {
  return apiClient.post(`/messages/${messageId}/retry`);
};

/**
 * 批量查询后台任务状态
 */
export const checkTasksStatus = (taskIds: string[]): Promise<{ running_tasks: string[] }> => {
  return apiClient.post('/tasks/status', { task_ids: taskIds });
};
