// frontend/mambo/src/api/types/groupChatTypes.ts

export type GroupStatus = 'ready' | 'paused' | 'deleting'

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

export type GroupMailState = 'staged' | 'sent' | 'discarded'

export interface GroupMemberCreate {
  agentId: string
  memberAlias: string
}

export interface GroupChatCreate {
  name: string
  parentId?: string | null
  autoRoundLimit?: number
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
}

export interface GroupDetail {
  groupId: string
  name: string
  parentId?: string | null
  status: GroupStatus
  pauseReason?: GroupPauseReason | null
  autoRoundLimit: number
  autoRoundCount: number
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
}

export interface GroupMailList {
  items: GroupMail[]
  nextAfterSequence?: number | null
  hasMore: boolean
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
