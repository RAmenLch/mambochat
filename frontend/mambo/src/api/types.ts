// frontend/mambochat/src/api/types.ts

export type MessageRole = 'user' | 'assistant' | 'system';
export type ChatItemType = 'chat' | 'folder';
export type MessageStatus = 'generating' | 'completed' | 'failed';

// --- SubMessage Types ---

export interface SubMessageConfig {
  is_collapsed: boolean;
}

export interface SubMessage {
  id: string;
  content: string;
  createdAt: string; // ISO 8601 date string
  messageId: string;
  sortOrder: number;
  type: string;
  config: SubMessageConfig;
  status: MessageStatus;
}

export interface SubMessageCreate {
  content: string;
  sortOrder: number;
  type?: string;
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
}

export interface MessageUpdate {
  sub_messages: SubMessageCreate[];
  resend?: boolean;
}

export interface GenerateRequest {
  sub_messages: SubMessageCreate[];
}


// --- AI & Provider Types ---

export interface AIModelBase {
  modelId: string;
  name: string;
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
}

export interface AIProvider {
  id: string;
  name: string;
  apiHost: string;
}

export interface AIProviderWithModels extends AIProvider {
  models: AIModel[];
}

export interface AIProviderCreate {
  id?: string | null;
  name: string;
  apiHost: string;
  apiKey: string;
}

export interface AIProviderUpdate {
  name?: string;
  apiHost?: string;
  apiKey?: string;
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
  last_selected_provider_id: string | null;
  default_max_context_messages: number | null;
  default_temperature: number | null;
  default_top_p: number | null;
  default_stream: boolean | null;
}
