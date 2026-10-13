// frontend/mambo/src/api/groupChatService.ts

import apiClient from './index';
import type {
  GroupChatCreate,
  GroupCreatedResponse,
  GroupDetail,
  GroupMailList,
  GroupTaskList,
  GroupMessageSendRequest,
  GroupTaskAccepted,
  GroupSettingsUpdate,
  GroupControlResponse,
} from './types/groupChatTypes';

/** 原子创建群组会话 */
export const createGroupChat = (data: GroupChatCreate): Promise<GroupCreatedResponse> => {
  return apiClient.post('/group-chats', data);
};

/** 获取群组元信息与运行状态 */
export const getGroupDetail = (groupId: string): Promise<GroupDetail> => {
  return apiClient.get(`/group-chats/${groupId}`);
};

/** 修改群组设置（自动轮次上限等） */
export const updateGroupSettings = (
  groupId: string,
  data: GroupSettingsUpdate,
): Promise<GroupControlResponse> => {
  return apiClient.patch(`/group-chats/${groupId}/settings`, data);
};

/** 生命周期感知的整组删除 */
export const deleteGroupChat = (groupId: string): Promise<void> => {
  return apiClient.delete(`/group-chats/${groupId}`);
};

/** 群输入（空 recipientNames 表示广播） */
export const sendGroupMessage = (
  groupId: string,
  data: GroupMessageSendRequest,
): Promise<GroupTaskAccepted> => {
  return apiClient.post(`/group-chats/${groupId}/messages`, data);
};

/** 按期邮件游标分页 */
export const listGroupMails = (
  groupId: string,
  afterSequence?: number | null,
  limit = 50,
): Promise<GroupMailList> => {
  const params: Record<string, unknown> = { limit };
  if (afterSequence !== undefined && afterSequence !== null) {
    params.afterSequence = afterSequence;
  }
  return apiClient.get(`/group-chats/${groupId}/mails`, { params });
};

/** 任务列表 */
export const listGroupTasks = (groupId: string, limit = 100): Promise<GroupTaskList> => {
  return apiClient.get(`/group-chats/${groupId}/tasks`, { params: { limit } });
};

export const pauseGroup = (groupId: string): Promise<GroupControlResponse> => {
  return apiClient.post(`/group-chats/${groupId}/pause`);
};

export const resumeGroup = (groupId: string): Promise<GroupControlResponse> => {
  return apiClient.post(`/group-chats/${groupId}/resume`);
};

export const retryGroupTask = (groupId: string, taskId: string): Promise<GroupControlResponse> => {
  return apiClient.post(`/group-chats/${groupId}/tasks/${taskId}/retry`);
};

export const cancelGroupTask = (groupId: string, taskId: string): Promise<{ message: string }> => {
  return apiClient.post(`/group-chats/${groupId}/tasks/${taskId}/cancel`);
};

export const discardGroupTask = (groupId: string, taskId: string): Promise<GroupControlResponse> => {
  return apiClient.post(`/group-chats/${groupId}/tasks/${taskId}/discard`);
};

export const processMemberUnread = (
  groupId: string,
  memberChatId: string,
): Promise<GroupTaskAccepted> => {
  return apiClient.post(`/group-chats/${groupId}/members/${memberChatId}/process-unread`);
};
