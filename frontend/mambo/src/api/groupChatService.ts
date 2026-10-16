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
  GroupMailReview,
  GroupMailDecision,
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

/** 复制群组到指定邮件为止（粒度=该邮件所属整轮），返回新群详情 */
export const duplicateGroupChat = (
  groupId: string,
  upToMailId: string,
): Promise<GroupCreatedResponse> => {
  return apiClient.post(`/group-chats/${groupId}/duplicate`, { upToMailId });
};

/** 邮件筛选条件：发信人 / 收信人均为成员别名（收信人含 Master=用户），空数组表示不筛选 */
export interface GroupMailFilters {
  sender?: string[]
  recipient?: string[]
}

/** 按期邮件游标分页（可按发信人 / 收信人过滤；别名为逗号安全集，故用逗号拼接） */
export const listGroupMails = (
  groupId: string,
  afterSequence?: number | null,
  limit = 50,
  filters?: GroupMailFilters,
): Promise<GroupMailList> => {
  const params: Record<string, unknown> = { limit };
  if (afterSequence !== undefined && afterSequence !== null) {
    params.afterSequence = afterSequence;
  }
  if (filters?.sender?.length) params.sender = filters.sender.join(',');
  if (filters?.recipient?.length) params.recipient = filters.recipient.join(',');
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

/** 审核模式：待审核邮件 + 已决策邮件（被拒 / 已同意待投递） */
export const listMailReviews = (groupId: string): Promise<GroupMailReview> => {
  return apiClient.get(`/group-chats/${groupId}/mail-reviews`);
};

/** 审核模式：同意投递该邮件 */
export const approveMail = (groupId: string, mailId: string): Promise<GroupMailDecision> => {
  return apiClient.post(`/group-chats/${groupId}/mails/${mailId}/approve`);
};

/** 审核模式：拒绝投递该邮件（拒绝原因必填） */
export const rejectMail = (
  groupId: string,
  mailId: string,
  reason: string,
): Promise<GroupMailDecision> => {
  return apiClient.post(`/group-chats/${groupId}/mails/${mailId}/reject`, { reason });
};
