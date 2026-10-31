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
  /** 待生成文件的失败原因：timeout / task_failed / no_backend / download_failed */
  pending_failed_reason?: string | null
  show_tool_mode?: string | null
  /** get_goal MCP_TOOL 轮次边界标志（GoalLoopMiddleware 注入），前端据此渲染轮次分隔线 */
  is_goal_loop_round?: boolean | null
  /**
   * 尾部工具汇总标志：该子消息承载"一轮末尾工具调用"的结果，
   * 不参与正文 / 时间线渲染，仅在助手消息底部以折叠面板展示
   */
  is_tail_tool?: boolean | null
  /** 本次生成 run 的标识：LLM 调用=该工具 tool_call_id，平台重跑=新生成的 uuid */
  image_run_id?: string | null
  /** 所属"插槽"标识（同一位置的第 1/2/3 次生成共享）；为空表示自成一插槽 */
  image_slot_id?: string | null
  /** 本次生成下发的参数快照 */
  image_run_args?: Record<string, any> | null
  /** 用户当前置顶的 run（只写在插槽内最早的一条 File 子消息上） */
  image_pinned_run_id?: string | null
  /** 是否为"图片重跑生成记录"子消息（McpTool 类型，不参与上下文，只在图片区域展示） */
  is_image_run_record?: boolean | null
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

/** 图片重跑请求：留空的字段沿用该插槽上一次生成的取值 */
export interface ImageRunRerunRequest {
  prompt?: string
  negative_prompt?: string | null
  resolution?: string
  count?: number
  mode?: string
  extra?: Record<string, any>
  path?: string
  timeout?: number
}

/** 图片重跑结果：record 为本次生成记录，files 为本次生成入库的图片子消息 */
export interface ImageRunRerunResponse {
  run_id: string
  slot_id: string
  status: 'completed' | 'failed'
  record: SubMessage
  files: SubMessage[]
  error: string | null
}

/** 手动获取待生成文件的结果 */
export interface PendingFileFetchResponse {
  /** completed=已入库；running=任务仍在生成；failed=任务失败或下载失败 */
  status: 'completed' | 'running' | 'failed'
  file_id?: string | null
  file_info?: FileResponse | null
  error?: string | null
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
  /** 群组父节点为 'group'；普通节点为 null。itemType 必须为 'folder' 时才有意义 */
  folderType?: 'group' | null
  /** 群成员的邮箱地址/别名；非成员为空 */
  memberAlias?: string | null
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
  folderType?: 'group' | null
  memberAlias?: string | null
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

export interface WebSearchDisplayItem {
  title: string
  url: string
  /** 100~200 字符短摘要，专供列表展示 */
  snippet: string
  site_name?: string | null
  site_icon?: string | null
  /** RFC3339（UTC），前端格式化为 YYYY-MM-DD */
  date?: string | null
  rerank_score?: number | null
  /** 权威度 0~4，-1 表示未知 */
  authority?: number | null
}

/** 后端下发的搜索结果展示快照（仅前端展示，不进入 LLM 上下文） */
export interface WebSearchDisplay {
  kind: 'web_search'
  provider?: string
  query?: string
  count?: number
  items?: WebSearchDisplayItem[]
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
  /** 搜索结果展示快照；老消息可能缺失，前端回退解析 result */
  display?: WebSearchDisplay | null
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

// --- Chat Status Types ---

/** 会话列表徽标状态 */
export interface ChatStatusFlags {
  generating: boolean
  pendingReview: boolean
  unread: boolean
}

export interface ChatStatusNotificationPayload extends Partial<ChatStatusFlags> {
  chat_id: string
  status: 'generating' | 'review' | 'unread' | 'idle'
}

export interface ChatStatusResponse {
  statuses: Record<string, ChatStatusFlags>
}
