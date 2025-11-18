// frontend/mambo/src/api/types.ts

export type MessageRole = 'user' | 'assistant' | 'system';
export type ChatItemType = 'chat' | 'folder';
export type MessageStatus = 'generating' | 'completed' | 'failed';

// --- SubMessage Types ---

/**
 * 定义了子消息的所有可能类型。
 * - Normal: 普通的Markdown文本内容。
 * - Reasoning: AI的思考过程或元数据。
 * - File: 引用一个已上传的文件。
 * - Usage: 包含本次生成的Token用量信息。
 * - ZipHistory: 对话历史的压缩摘要。
 */
export type SubMessageType = 'Normal' | 'Reasoning' | 'File' | 'Usage' | 'ZipHistory';

export interface SubMessageConfig {
  is_collapsed: boolean;
  context_participation_length?: number;
  zip_enable?: boolean | null; // 压缩历史是否启用
}

export interface SubMessage {
  id: string;
  content: string;
  createdAt: string; // ISO 8601 date string
  messageId: string;
  sortOrder: number;
  type: SubMessageType;
  config: SubMessageConfig;
  status: MessageStatus;
  file_info?: FileResponse; // 用于承载文件类型消息的完整文件元数据
}

export interface SubMessageCreate {
  content: string;
  sortOrder: number;
  type?: SubMessageType;
  config?: SubMessageConfig;
  status?: MessageStatus;
}

export interface SubMessageUpdate {
  content?: string;
  config?: SubMessageConfig;
  status?: MessageStatus;
}


// --- Message Types ---

export interface Message {
  id: string;
  createdAt: string; // ISO 8601 date string
  role: MessageRole;
  chatId: string;
  sortOrder: number;
  sub_messages: SubMessage[];
  status: MessageStatus;
}

export interface MessageUpdate {
  sub_messages: SubMessageCreate[];
  resend?: boolean;
}

export interface GenerateRequest {
  sub_messages: SubMessageCreate[];
  attachedSubmessageResourceIds?: string[];
}

/**
 * The response object from the prepare-generate endpoint.
 * Contains both the newly created user message and the AI assistant's placeholder.
 */
export interface PrepareGenerateResponse {
  user_message: Message;
  assistant_message: Message;
}


// --- AI & Provider Types ---

/**
 * 存储模型的元配置信息
 */
export interface AIModelMetaConfig {
  context_length?: number | null;
  max_output_tokens?: number | null;
  tokenizer?: string | null;
  input_modalities?: string[] | null;
  output_modalities?: string[] | null;
  supported_parameters?: string[] | null;
}

export interface AIModelBase {
  modelId: string;
  name: string;
  meta_config?: AIModelMetaConfig | null;
}

export interface AIModel extends AIModelBase {
  id: string;
  providerId: string;
}

export interface AIModelCreate extends AIModelBase {
  providerId: string;
}

export interface AIModelUpdate {
  name?: string;
  meta_config?: AIModelMetaConfig | null;
}

export interface AIProvider {
  id: string;
  name: string;
  apiHost: string;
  use_proxy: boolean;
}

export interface AIProviderWithModels extends AIProvider {
  models: AIModel[];
}

export interface AIProviderCreate {
  id?: string | null;
  name: string;
  apiHost: string;
  apiKey: string;
  use_proxy: boolean;
}

export interface AIProviderUpdate {
  name?: string;
  apiHost?: string;
  apiKey?: string;
  use_proxy?: boolean;
}

export interface ProviderWithModelsCreate extends AIProviderCreate {
  models: AIModelBase[];
}

export interface ConnectionRequest {
  apiHost: string;
  apiKey: string;
}

export interface ConnectionTestResponse {
  status: string;
  message: string;
}

// --- Chat Types ---

export interface Chat {
  id:string;
  name: string;
  createdAt: string;
  systemPrompt: string | null;
  modelParameters: Record<string, any> | null;
  aiModelId: string | null;
  itemType: ChatItemType;
  parentId: string | null;
  sortOrder: number;
  lastOpenedAt: string | null;
}

/**
 * 前端专用的、带有子节点层级的会话树节点类型。
 */
export type ChatNode = Chat & { children?: ChatNode[] };

export interface ChatCreate {
  name: string;
  systemPrompt?: string | null;
  modelParameters?: Record<string, any> | null;
  aiModelId?: string | null;
  itemType?: ChatItemType;
  parentId?: string | null;
  sortOrder?: number;
}

export interface ChatUpdate {
  name?: string | null;
  aiModelId?: string | null;
  systemPrompt?: string | null;
  modelParameters?: Record<string, any> | null;
  parentId?: string | null;
  sortOrder?: number;
}

export interface ChatWithMessages extends Chat {
  messages: Message[];
}

export interface ChatReorderItem {
  id: string;
  parentId: string | null;
  sortOrder: number;
}

// --- Global Settings Types ---

export interface GlobalSettingsUpdate {
  default_model_id: string | null;
  title_generation_model_id: string | null;
  last_selected_provider_id: string | null;
  default_max_context_messages: number | null;
  default_temperature: number | null;
  default_top_p: number | null;
  default_stream: boolean | null;
  proxy_enabled: boolean | null;
  proxy_url: string | null;
  user_avatar_url: string | null;
  ai_avatar_url: string | null;
  zip_history_system_prompt?: string | null; // 生成压缩历史的System Prompt
}

// --- File Management Types ---

export interface FileResponse {
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  created_at: string; // ISO 8601 date string
  url: string;
}

// --- Proxy Test Types ---

export interface ProxyTestRequest {
  proxy_url: string;
  test_url: string;
}

// --- Notification Types ---

/**
 * `chat_update` 事件的载荷，通常用于标题更新。
 */
export interface ChatUpdateNotificationPayload {
  id: string;
  name: string;
}

/**
 * `zip_history_update` 事件的载荷，在历史压缩完成后触发。
 */
export interface ZipHistoryUpdateNotificationPayload {
  chat_id: string;
  message_id: string;
  sub_message: SubMessage;
}

/**
 * 定义所有可能的全局通知类型，使用可辨识联合类型。
 */
export type GlobalNotification =
  | {
      type: 'chat_update';
      payload: ChatUpdateNotificationPayload;
    }
  | {
      type: 'zip_history_update';
      payload: ZipHistoryUpdateNotificationPayload;
    };

// --- Resource Center Types ---

export type ResourceItemType = 'resource' | 'folder';
/**
 * 定义资源的具体品类。
 */
export type ResourceType = 'system_prompt' | 'submessage_template' | string;

/**
 * 代表一个资源版本快照。
 */
export interface ResourceVersion {
  id: string;
  resourceId: string;
  name: string;
  commitMessage: string | null;
  content: string | null;
  attributes: Record<string, any> | null;
  sortOrder: number;
  createdAt: string; // ISO 8601 date string
  updatedAt: string; // ISO 8601 date string
}

/**
 * 代表一个资源或文件夹的目录项。
 */
export interface Resource {
  id: string;
  name: string;
  description: string | null;
  itemType: ResourceItemType;
  resourceType: ResourceType | null;
  parentId: string | null;
  sortOrder: number;
  createdAt: string; // ISO 8601 date string
  updatedAt: string; // ISO 8601 date string
  latest_version: ResourceVersion | null;
}

/**
 * 前端专用的、带有子节点层级的资源树节点类型。
 */
export type ResourceNode = Resource & { children?: ResourceNode[] };

/**
 * 代表一个包含其所有版本列表的资源详情。
 */
export interface ResourceWithVersions extends Resource {
  versions: ResourceVersion[];
}

/**
 * 用于创建新资源或文件夹的请求体。
 */
export interface ResourceCreate {
  name: string;
  description?: string | null;
  itemType: ResourceItemType;
  resourceType?: ResourceType | null;
  parentId?: string | null;
  sortOrder: number;
  initial_content?: string | null;
  initial_attributes?: Record<string, any> | null;
}

/**
 * 用于更新资源基本信息的请求体。
 */
export interface ResourceUpdate {
  name?: string;
  description?: string | null;
  parentId?: string | null;
}

/**
 * 用于批量更新资源排序和层级的请求体。
 */
export interface ResourceReorderItem {
  id: string;
  parentId: string | null;
  sortOrder: number;
}

/**
 * 用于创建新资源版本的请求体。
 */
export interface ResourceVersionCreate {
  name: string;
  commitMessage?: string | null;
  content?: string | null;
  attributes?: Record<string, any> | null;
}

/**
 * 用于更新已存在资源版本的请求体。
 */
export interface ResourceVersionUpdate {
  name?: string;
  commitMessage?: string | null;
  content?: string | null;
  attributes?: Record<string, any> | null;
}
