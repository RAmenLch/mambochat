// frontend/mambo/src/api/types.ts

// --- Common / Tree Types ---
export type MoveAction = 'before' | 'after' | 'inside'

export interface MoveRequest {
  item_ids: string[]
  reference_id: string
  action: MoveAction
}

/**
 * 定义树形结构数据的基本接口。
 * 任何需要使用通用树组件 (ExplorerTree) 的数据模型都应满足此结构。
 */
export interface BaseTreeItem {
  id: string
  name: string
  parentId: string | null
  sortOrder: number
  itemType: string
}

/**
 * 定义树节点拖拽排序事件的数据载荷。
 */
export interface TreeReorderEvent {
  id: string
  parentId: string | null
  sortOrder: number
}

export type MessageRole = 'user' | 'assistant' | 'system'
export type ChatItemType = 'chat' | 'folder'
export type MessageStatus = 'generating' | 'completed' | 'failed'

// --- SubMessage Types ---

/**
 * 定义了子消息的所有可能类型。
 * - Normal: 普通的Markdown文本内容。
 * - Reasoning: AI的思考过程或元数据。
 * - File: 引用一个已上传的文件。
 * - Usage: 包含本次生成的Token用量信息。
 * - ZipHistory: 对话历史的压缩摘要。
 */
export type SubMessageType = 'Normal' | 'Reasoning' | 'File' | 'Usage' | 'ZipHistory' | 'McpTool'

export interface SubMessageConfig {
  is_collapsed: boolean
  is_minimal?: boolean
  context_participation_length?: number
  zip_enable?: boolean | null // 压缩历史是否启用
}

export interface SubMessage {
  id: string
  content: string
  createdAt: string // ISO 8601 date string
  messageId: string
  sortOrder: number
  type: SubMessageType
  config: SubMessageConfig
  status: MessageStatus
  file_info?: FileResponse // 用于承载文件类型消息的完整文件元数据
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
  createdAt: string // ISO 8601 date string
  role: MessageRole
  chatId: string
  sortOrder: number
  sub_messages: SubMessage[]
  status: MessageStatus
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

/**
 * The response object from the prepare-generate endpoint.
 * Contains both the newly created user message and the AI assistant's placeholder.
 */
export interface PrepareGenerateResponse {
  user_message: Message
  assistant_message: Message
}

// --- AI & Provider Types ---
export type ProviderWorkerType = 'openai' | 'google' | 'deepseek'
export type ModelType = 'chat' | 'embedding'
/**
 * 存储模型的元配置信息
 */
export interface AIModelMetaConfig {
  context_length?: number | null
  max_output_tokens?: number | null
  embedding_dimension?: number | null
  tokenizer?: string | null
  input_modalities?: string[] | null
  output_modalities?: string[] | null
  supported_parameters?: string[] | null
}

export interface AIModelBase {
  modelId: string
  name: string
  model_type: ModelType
  meta_config?: AIModelMetaConfig | null
}

export interface AIModel extends AIModelBase {
  id: string
  providerId: string
}

export interface AIModelCreate extends AIModelBase {
  providerId: string
}

export interface AIModelUpdate {
  name?: string
  model_type?: ModelType
  meta_config?: AIModelMetaConfig | null
}

export interface AIProvider {
  id: string
  name: string
  apiHost: string
  worker_type: ProviderWorkerType
  use_proxy: boolean
}

export interface AIProviderWithModels extends AIProvider {
  models: AIModel[]
}

export interface AIProviderCreate {
  id?: string | null
  name: string
  apiHost: string
  apiKey: string
  worker_type: ProviderWorkerType
  use_proxy: boolean
}

export interface AIProviderUpdate {
  name?: string
  apiHost?: string
  apiKey?: string
  worker_type?: ProviderWorkerType
  use_proxy?: boolean
}

export interface ProviderWithModelsCreate extends AIProviderCreate {
  models: AIModelBase[]
}

export interface ConnectionRequest {
  apiHost: string
  apiKey: string
}

export interface ConnectionTestResponse {
  status: string
  message: string
}
// --- System Config Types ---

/**
 * 定义一个LLM参数的完整结构，用于API响应，供前端UI生成和校验。
 */
export interface LLMParameterDefinition {
  key: string
  label: string
  path: string[]
  description: string
  type: 'integer' | 'number' | 'string' | 'boolean'
  limit?: Array<any> | { min?: number; max?: number }
  default_value: any
  default_activate: boolean
}

/**
 * 定义预设服务商的基本信息，用于API响应。
 */
export interface DefaultProviderInfo {
  name: string
  apiHost: string
  worker_type: ProviderWorkerType
}

/**
 * GET /api/system-config 接口的响应模型。
 */
export interface SystemConfigResponse {
  llm_parameters: LLMParameterDefinition[]
  default_providers: DefaultProviderInfo[]
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
  isLoaded?: boolean // 标记该节点的子节点是否已加载
}

/**
 * 前端专用的、带有子节点层级的会话树节点类型。
 */
export type ChatNode = Chat & { children?: ChatNode[] }

export interface ChatCreate {
  name: string
  systemPrompt?: string | null
  modelParameters?: Record<string, any> | null
  aiModelId?: string | null
  itemType?: ChatItemType
  parentId?: string | null
  sortOrder?: number
}

export interface ChatUpdate {
  name?: string | null
  aiModelId?: string | null
  systemPrompt?: string | null
  modelParameters?: Record<string, any> | null
  parentId?: string | null
  sortOrder?: number
}

export interface ChatWithMessages extends Chat {
  messages: Message[]
}

export interface ChatReorderItem {
  id: string
  parentId: string | null
  sortOrder: number
}

// --- Global Settings Types ---

export interface GlobalSettingsUpdate {
  default_model_id: string | null
  title_generation_model_id: string | null
  last_selected_provider_id: string | null
  default_max_context_messages: number | null
  default_temperature: number | null
  default_top_p: number | null
  default_stream: boolean | null
  proxy_enabled: boolean | null
  proxy_url: string | null
  user_avatar_url: string | null
  ai_avatar_url: string | null
  zip_history_system_prompt?: string | null // 生成压缩历史的System Prompt
}

// --- File Management Types ---

export interface FileResponse {
  id: string
  filename: string
  mime_type: string
  size: number
  created_at: string // ISO 8601 date string
  url: string
}

// --- Proxy Test Types ---

export interface ProxyTestRequest {
  proxy_url: string
  test_url: string
}

// --- Notification Types ---

/**
 * `chat_update` 事件的载荷，通常用于标题更新。
 */
export interface ChatUpdateNotificationPayload {
  id: string
  name: string
}

/**
 * 标题生成错误通知的上下文数据
 */
export interface TitleGenerationErrorContext {
  chat_id: string
}

/**
 * `zip_history_update` 事件的载荷，在历史压缩完成后触发。
 */
export interface ZipHistoryUpdateNotificationPayload {
  chat_id: string
  message_id: string
  sub_message: SubMessage
}

/**
 * 定义所有可能的全局通知类型，使用可辨识联合类型。
 */
export type GlobalNotification =
  | {
      type: 'chat_update'
      payload: ChatUpdateNotificationPayload
    }
  | {
      type: 'zip_history_update'
      payload: ZipHistoryUpdateNotificationPayload
    }
  | {
      type: 'notification'
      category: 'title_generation_error'
      context: TitleGenerationErrorContext
      level: string
      message: string
    }

// --- Resource Center Types ---

export type ResourceItemType = 'resource' | 'folder' | 'stub'
/**
 * 定义资源的具体品类。
 */
export type ResourceType = 'system_prompt' | 'submessage_template' | 'knowledge_base' | 'knowledge_base_chunk' | 'kb_file' | string

/**
 * 知识库文件属性结构
 */
export interface KBFileAttributes {
  splitter_config?: KBSplitterConfig
  last_ingest_config?: KBSplitterConfig
  [key: string]: any
}

/**
 * 代表一个资源版本快照。
 */
export interface ResourceVersion {
  id: string
  resourceId: string
  name: string
  commitMessage: string | null
  content: string | null
  attributes: KBFileAttributes | Record<string, any> | null
  sortOrder: number
  createdAt: string // ISO 8601 date string
  updatedAt: string // ISO 8601 date string
}

/**
 * 代表一个资源或文件夹的目录项。
 */
export interface Resource {
  id: string
  name: string
  description: string | null
  itemType: ResourceItemType
  resourceType: ResourceType | null
  parentId: string | null
  sortOrder: number
  createdAt: string // ISO 8601 date string
  updatedAt: string // ISO 8601 date string
  latest_version: ResourceVersion | null
  isLoaded?: boolean // 标记该节点的子节点是否已加载
}

/**
 * 前端专用的、带有子节点层级的资源树节点类型。
 */
export type ResourceNode = Resource & { children?: ResourceNode[] }

/**
 * 代表一个包含其所有版本列表的资源详情。
 */
export interface ResourceWithVersions extends Resource {
  versions: ResourceVersion[]
}

/**
 * 用于创建新资源或文件夹的请求体。
 */
export interface ResourceCreate {
  name: string
  description?: string | null
  itemType: ResourceItemType
  resourceType?: ResourceType | null
  parentId?: string | null
  sortOrder?: number
  initial_content?: string | null
  initial_attributes?: Record<string, any> | null
}

/**
 * 用于更新资源基本信息的请求体。
 */
export interface ResourceUpdate {
  name?: string
  description?: string | null
  parentId?: string | null
}

/**
 * 用于批量更新资源排序和层级的请求体。
 */
export interface ResourceReorderItem {
  id: string
  parentId: string | null
  sortOrder: number
}

/**
 * 用于创建新资源版本的请求体。
 */
export interface ResourceVersionCreate {
  name: string
  commitMessage?: string | null
  content?: string | null
  attributes?: Record<string, any> | null
}

/**
 * 用于更新已存在资源版本的请求体。
 */
export interface ResourceVersionUpdate {
  name?: string
  commitMessage?: string | null
  content?: string | null
  attributes?: Record<string, any> | null
}

export interface McpService {
  id: string
  name: string
  description: string
  is_active: boolean
}

/**
 * McpTool 类型 SubMessage 的 content 字段解析后的结构。
 */
export interface McpToolContent {
  tool_call_id: string
  name: string
  arguments: string
  result: string | null
  is_error: boolean
}

// --- Search Types (Chat) ---

/**
 * 会话搜索请求参数
 */
export interface SearchRequest {
  keyword: string
  root_id?: string | null
  enable_regex?: boolean
  page_num?: number
  page_size?: number
}

/**
 * 会话搜索响应结果
 */
export interface SearchResponse {
  total: number
  items: SearchResultItem[]
}

/**
 * 会话搜索结果项
 */
export interface SearchResultItem {
  chat_id: string
  chat_name: string
  chat_path: string
  match_type: 'content' | 'title' | 'system_prompt'
  context_text: string
  sub_message_id: string | null
  created_at: string
}

// --- Search Types (Resource) ---

/**
 * 资源搜索请求参数
 */
export interface ResourceSearchRequest {
  keyword: string
  root_id?: string | null
  enable_regex?: boolean
  page_num?: number
  page_size?: number
}

/**
 * 资源搜索结果匹配类型
 */
export type ResourceMatchType = 'name' | 'description' | 'content'

/**
 * 资源搜索结果项
 */
export interface ResourceSearchResultItem {
  resource_id: string
  resource_name: string
  resource_path: string
  match_type: ResourceMatchType
  context_text: string
  version_id: string | null
  updated_at: string
}

/**
 * 资源搜索响应结果
 */
export interface ResourceSearchResponse {
  total: number
  items: ResourceSearchResultItem[]
}
/**
 * 知识库文件处理状态
 */
export type KBFileStatus =   | 'INITIAL'
  | 'CLEANING'
  | 'READING'
  | 'SPLITTING'
  | 'EMBEDDING'
  | 'COMPLETED'
  | 'FAILED'
  | 'STOPPED'
/**
 * 知识库创建请求参数
 */
export interface KnowledgeBaseCreate {
  name: string
  description?: string | null
  parent_id?: string | null
  embedding_model_id?: string | null
  embedding_rate_limit?: number
}

/**
 * 知识库文件切片状态详情
 */
export interface KBChunkStatus {
  resource_id: string
  total_chunks: number
  pending_chunks: number
  completed_chunks: number
  failed_chunks: number
  stopped_chunks: number
  file_status: KBFileStatus
  message?: string
}

/**
 * 实时进度事件 (对应 SSE 的 Stream Event)
 * 用于描述当前步骤（如 EMBEDDING）的具体进度
 */
export interface KBTaskStreamEvent {
  status: KBFileStatus
  message: string
  processed: number
  total: number
}

/**
 * 向量检索请求参数
 */
export interface KBSearchRequest {
  query_text: string
  kb_id?: string | null
  top_k?: number
}
/**
 * 向量检索结果项
 */
export interface KBSearchResultItem {
  chunk_id: string
  chunk_content: string
  score: number
  resource_id: string
  resource_name: string
  kb_id: string
  kb_name: string
}
/**
 * 向量检索响应
 */
export interface KBSearchResponse {
  total: number
  items: KBSearchResultItem[]
}

/**
 * 文本切分方式
 */
export type SplitterType = 'simple' | 'separator'

/**
 * 知识库任务动作
 */
export type KBTaskAction = 'start' | 'resume' | 'stop'

/**
 * 切分参数配置
 */
export interface KBSplitterConfig {
  splitter_type: SplitterType
  chunk_size: number
  chunk_overlap: number
  separator?: string | null // 仅当 splitter_type 为 'separator' 时有效
}

/**
 * 更新知识库文件配置的请求体
 */
export interface KBUpdateConfigRequest {
  splitter_config: KBSplitterConfig
}

/**
 * 启动/控制知识库任务的请求体
 * 注意：Start 任务不再接收配置参数，请先调用更新配置接口
 */
export interface KBRunTaskRequest {
  action: KBTaskAction
}

/**
 * 知识库文件处理进度的 SSE 事件载荷
 */
export type KBTaskProgressPayload = KBChunkStatus | KBTaskStreamEvent
/**
 * Resume 任务冲突时的错误详情结构 (409 Conflict)
 */
export interface KBResumeConflictErrorDetail {
  message: string
  current_config: KBSplitterConfig
  last_ingest_config: KBSplitterConfig
}

