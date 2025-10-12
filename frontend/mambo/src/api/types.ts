// frontend/mambo/src/api/types.ts

export type MessageRole = 'user' | 'assistant' | 'system';
export type ChatItemType = 'chat' | 'folder';
export type MessageStatus = 'generating' | 'completed' | 'failed';

export interface Message {
  id: string;
  content: string;
  createdAt: string; // ISO 8601 date string
  role: MessageRole;
  chatId: string;
  sortOrder: number;
  status: MessageStatus;
}

export interface MessageUpdate {
  content: string;
  resend?: boolean;
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
}
