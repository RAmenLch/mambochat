// frontend/mambo/src/api/types/chatTypes.ts

import type { FileResponse } from './common'

export type MessageRole = 'user' | 'assistant' | 'system'
export type ChatItemType = 'chat' | 'folder'
export type MessageStatus = 'generating' | 'completed' | 'failed' | 'pending_review'
export type ChatMode = 'normal' | 'agent'

// --- SubMessage Types ---

export type SubMessageType =
  | 'Normal'
  | 'Reasoning'
  | 'File'
  | 'Usage'
  | 'ZipHistory'
  | 'McpTool'
  | 'Suggest'
  | 'ReviewTool'
  | 'AskUser'
  | 'Error'

export interface SubMessageConfig {
  is_collapsed: boolean
  is_minimal?: boolean
  context_participation_length?: number
  zip_enable?: boolean | null
  target_sub_msg_id?: string | null
}

export interface SubMessage {
  id: string
  content: string
  createdAt: string
  messageId: string
  sortOrder: number
  type: SubMessageType
  config: SubMessageConfig
  status: MessageStatus
  file_info?: FileResponse
}

export interface SubMessageCreate {
  content: string
  sortOrder: number
  type?: SubMessageType
  config?: SubMessageConfig
  status?: MessageStatus
}

export interface SubMessageUpdate {
  content?: string
  config?: SubMessageConfig
  status?: MessageStatus
}

// --- Message Types ---

export interface Message {
  id: string
  createdAt: string
  role: MessageRole
  chatId: string
  sortOrder: number
  sub_messages: SubMessage[]
  status: MessageStatus
  parentId: string | null
  lastActiveAt: string
  sibling_ids: string[]
  sibling_index: number
}

export interface MessageUpdate {
  sub_messages: SubMessageCreate[]
  resend?: boolean
}

export interface UpdateMessageResponse {
  user_message: Message
  assistant_message: Message | null
}

export interface GenerateRequest {
  sub_messages: SubMessageCreate[]
  attachedSubmessageResourceIds?: string[]
}

export interface PrepareGenerateResponse {
  user_message: Message
  assistant_message: Message
}

// --- Chat Types ---

export interface Chat {
  id: string
  name: string
  createdAt: string
  systemPrompt: string | null
  modelParameters: Record<string, any> | null
  aiModelId: string | null
  itemType: ChatItemType
  parentId: string | null
  sortOrder: number
  lastOpenedAt: string | null
  isLoaded?: boolean
  resource_prompt_list?: string[] | null
  enabled_mcp_ids?: string[] | null
  chatMode?: ChatMode
  agentId?: string | null
}

export type ChatNode = Chat & { children?: ChatNode[] }

export interface ChatCreate {
  name: string
  systemPrompt?: string | null
  modelParameters?: Record<string, any> | null
  aiModelId?: string | null
  itemType?: ChatItemType
  parentId?: string | null
  sortOrder?: number
  enabled_mcp_ids?: string[] | null
  chatMode?: ChatMode
  agentId?: string | null
}

export interface ChatUpdate {
  name?: string | null
  aiModelId?: string | null
  systemPrompt?: string | null
  modelParameters?: Record<string, any> | null
  parentId?: string | null
  sortOrder?: number
  resource_prompt_list?: string[] | null
  enabled_mcp_ids?: string[] | null
  chatMode?: ChatMode
  agentId?: string | null
}

export interface ChatWithMessages extends Chat {
  messages: Message[]
}

export interface ChatReorderItem {
  id: string
  parentId: string | null
  sortOrder: number
}


// --- Schema Property Type ---
export interface SchemaProperty {
  type: string;
  title?: string;
  description?: string;
  default?: unknown;
  [key: string]: unknown;
}

// --- Mcp Types ---

export interface McpService {
  id: string
  name: string
  description: string
  is_active: boolean
}

export interface McpToolContent {
  tool_call_id: string
  name: string
  arguments: string
  result: string | null
  is_error: boolean,
  input_schema?: Record<string, SchemaProperty>
}

export interface ReviewToolContent {
  tool_call_id: string
  name: string
  arguments: Record<string, unknown>
  description: string | null
  interrupt_index: number
  batch_id: string
  decision: ToolDecision | null
  input_schema?: Record<string, SchemaProperty>
}

export interface ToolDecision {
  type: 'approve' | 'edit' | 'reject'
  edited_action?: { name: string; args: Record<string, unknown> } | null
  message?: string | null
}

export interface ReviewToolRequest {
  sub_message_id: string
  decision: ToolDecision
}

export interface ErrorContent {
  message: string
  stack_trace: string
}

// --- AskUser Types ---

export interface AskUserQuestion {
  question: string
  type: 'text' | 'multiple_choice'
  choices?: Array<{ value: string }>
  required?: boolean
}

export interface AskUserContent {
  tool_call_id: string
  questions: AskUserQuestion[]
  answers?: string[] | null
  interrupt_index: number
  batch_id: string
  ask_status?: 'answered' | 'cancelled' | null
}

export interface AskUserAnswerRequest {
  sub_message_id: string
  answers: string[]
  ask_status: string
}

// --- Search Types (Chat) ---

export interface SearchRequest {
  keyword: string
  root_id?: string | null
  enable_regex?: boolean
  page_num?: number
  page_size?: number
}

export interface SearchResponse {
  total: number
  items: SearchResultItem[]
}

export interface SearchResultItem {
  chat_id: string
  chat_name: string
  chat_path: string
  match_type: 'content' | 'title' | 'system_prompt'
  context_text: string
  sub_message_id: string | null
  created_at: string
}

// --- Notification Types ---

export interface ChatUpdateNotificationPayload {
  id: string
  name: string
}

export interface TitleGenerationErrorContext {
  chat_id: string
}

export interface ZipHistoryUpdateNotificationPayload {
  chat_id: string
  message_id: string
  sub_message: SubMessage
}
