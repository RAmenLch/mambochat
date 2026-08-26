// frontend/mambo/src/api/types/chatTypes.ts

import type { FileResponse } from './common'

export type MessageRole = 'user' | 'assistant' | 'system'
export type ChatItemType = 'chat' | 'folder'
export type MessageStatus = 'generating' | 'completed' | 'failed' | 'pending_review' | 'waiting'
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
  | 'TaskSubStep'
  | 'SecurityReview'

export interface SubMessageConfig {
  is_collapsed: boolean
  is_minimal?: boolean
  context_participation_length?: number
  zip_enable?: boolean | null
  target_sub_msg_id?: string | null
  task_group_id?: string | null
  pending_file_path?: string | null
  pending_file_timeout?: number | null
  show_tool_mode?: string | null
  /** get_goal MCP_TOOL 轮次边界标志（GoalLoopMiddleware 注入），前端据此渲染轮次分隔线 */
  is_goal_loop_round?: boolean | null
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
  web_search_mode?: 'direct_read' | 'search_and_read' | 'disable' | null
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
  web_search_mode?: 'direct_read' | 'search_and_read' | 'disable' | null
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
  web_search_mode?: 'direct_read' | 'search_and_read' | 'disable' | null
  chatMode?: ChatMode
  agentId?: string | null
}

export interface ChatWithMessages extends Chat {
  messages: Message[]
}

// --- Chat Usage Stats Types ---

export interface UsageAggregate {
  total_tokens: number
  cache_hit_tokens: number
  cache_miss_tokens: number
  prompt_tokens: number
  completion_tokens: number
}

export interface ChatUsageStats {
  conversation: UsageAggregate
  active_path_main_agent: UsageAggregate
}

export interface ImportChatReport {
  chat_id: string
  name: string
  message_count: number
  file_count: number
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

export interface MultimodalMedia {
  /** 媒体类型：image / audio / video / file（与后端 backend_tools content_blocks 块 type 一致） */
  file_type: string
  mime_type: string
  file_id: string
  filename?: string | null
  size_bytes?: number | null
  /** 由消息组装层填充的下载路径（如 /api/files/download/...），供前端展示媒体 */
  url?: string | null
}

export interface McpToolContent {
  tool_call_id: string
  name: string
  arguments: string
  result: string | null
  is_error: boolean,
  input_schema?: Record<string, SchemaProperty>
  /** 多模态工具结果（例如 read 读取图片/音频/视频/文档），用于气泡与弹窗渲染媒体 */
  media?: MultimodalMedia[] | null
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

export interface SecurityReviewContent {
  tool_call_id: string
  tool_name: string
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  reason: string
  passed: boolean
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

// --- TaskSubStep Types ---

export interface TaskSubStepContent {
  tool_call_id: string
  subagent_type: string
  display_type: 'reasoning' | 'text' | 'tool_call' | 'tool_result'
  content: string
  tool_name?: string | null
  tool_args?: Record<string, unknown> | null
  step_order: number
  description?: string | null
  /** 子代理内部工具调用的 tool_call_id，用于绑定 AI 审核 / 中断审核事件 */
  sub_tool_call_id?: string | null
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
