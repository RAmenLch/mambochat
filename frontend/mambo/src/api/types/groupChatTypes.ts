// frontend/mambo/src/api/types/groupChatTypes.ts

export type GroupStatus = 'ready' | 'paused' | 'deleting'

/** 保留成员别名：Master 代表「用户本人」，无 Agent、不参与生成，也不作为普通子会话出现 */
export const MASTER_MEMBER_ALIAS = 'Master'

export type GroupPauseReason =
  | 'manual'
  | 'review'
  | 'ask_user'
  | 'failure'
  | 'cancelled'
  | 'restart'
  | 'round_limit'

export type GroupTaskKind = 'user_message' | 'mail_notice' | 'regenerate' | 'edit_regenerate'

export type GroupTaskState =
  | 'queued'
  | 'running'
  | 'waiting_review'
  | 'waiting_user'
  | 'ready_to_commit'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'interrupted'
  | 'skipped'

export type GroupMailState =
  | 'staged'
  | 'reviewing'
  | 'deferred'
  | 'sent'
  | 'rejected'
  | 'discarded'

/** 邮件投递模式：auto=生成完毕自动投递；review=需用户逐封审核 */
export type GroupMailMode = 'auto' | 'review'

export interface GroupMemberCreate {
  agentId: string
  memberAlias: string
}

export interface GroupChatCreate {
  name: string
  parentId?: string | null
  autoRoundLimit?: number
  mailMode?: GroupMailMode
  members: GroupMemberCreate[]
}

export interface GroupMember {
  chatId: string
  memberAlias: string
  agentId?: string | null
  agentName?: string | null
  name: string
  sortOrder: number
  unreadCount: number
  pendingCount: number
  /** 是否为保留的「用户本人」成员（Master）：无 Agent、不参与生成调度 */
  isUser?: boolean
}

export interface GroupDetail {
  groupId: string
  name: string
  parentId?: string | null
  status: GroupStatus
  pauseReason?: GroupPauseReason | null
  autoRoundLimit: number
  autoRoundCount: number
  /** 邮件投递模式：auto=生成完毕即投递；review=需用户逐封审核后投递 */
  mailMode?: GroupMailMode
  /** 群累计实际启动过的自动邮件轮次（跨额度周期，仅用于展示） */
  totalAutoRoundCount?: number
  version: number
  activeTaskId?: string | null
  members: GroupMember[]
  unreadCount: number
  queuedCount: number
}

export type GroupCreatedResponse = GroupDetail

export interface GroupMailRecipient {
  memberChatId: string
  memberName: string
}

export interface GroupMail {
  id: string
  groupId: string
  sourceTaskId: string
  senderChatId: string
  senderAliasSnapshot: string
  recipientSnapshot: GroupMailRecipient[]
  title?: string | null
  content: string
  state: GroupMailState
  sequence?: number | null
  createdAt: string
  sentAt?: string | null
  /** 审核模式：用户审核时间与拒绝原因 */
  reviewedAt?: string | null
  rejectReason?: string | null
}

export interface GroupMailList {
  items: GroupMail[]
  nextAfterSequence?: number | null
  hasMore: boolean
}

/** 审核模式的邮件审批视图 */
export interface GroupMailReview {
  pending: GroupMail[]
  decided: GroupMail[]
}

export interface GroupMailDecision {
  groupId: string
  mailId: string
  state: GroupMailState
  pendingCount: number
  finalized: boolean
  version: number
}

export interface GroupTask {
  id: string
  groupId: string
  memberChatId: string
  sequence: number
  kind: GroupTaskKind
  state: GroupTaskState
  requestId?: string | null
  userMessageId?: string | null
  assistantMessageId?: string | null
  attemptCount: number
  startedAt?: string | null
  finishedAt?: string | null
  createdAt: string
  errorCode?: string | null
  errorMessage?: string | null
}

export interface GroupTaskList {
  items: GroupTask[]
  total: number
}

export interface GroupMessageSendRequest {
  requestId?: string | null
  content: string
  recipientNames: string[]
}

export interface GroupTaskAccepted {
  kind: 'group_task'
  groupId: string
  taskIds: string[]
  state: GroupTaskState
}

export interface GroupSettingsUpdate {
  autoRoundLimit?: number
  resetAutoRoundCount?: boolean
  /** 切换邮件投递模式：只对之后的轮次生效 */
  mailMode?: GroupMailMode
}

export interface GroupControlResponse {
  groupId: string
  status: GroupStatus
  version: number
}

// --- 全局通知上下文（group_* 类别） ---

export interface GroupNotificationContext {
  groupId: string
  version?: number
  status?: GroupStatus
  pauseReason?: GroupPauseReason | null
  taskId?: string
  memberChatId?: string
  mailId?: string
  sequence?: number | null
  state?: GroupTaskState
  assistantMessageId?: string | null
}
