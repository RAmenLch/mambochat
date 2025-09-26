// ---- 服务商与模型相关类型 ----

export interface AIProvider {
  id: string;
  name: string;
  apiHost: string;
}

export interface AIModel {
  id: string;
  modelId: string;
  name: string;
  providerId: string;
}

export interface AIProviderWithModels extends AIProvider {
  models: AIModel[];
}

// 用于创建服务商的请求体
export interface AIProviderCreate {
  id?: string | null;
  name: string;
  apiHost: string;
  apiKey: string;
}

// 用于创建模型的请求体
export interface AIModelCreate {
  modelId: string;
  name: string;
  providerId: string;
}


// ---- 会话与消息相关类型 ----

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  chatId: string;
  role: MessageRole;
  content: string;
  createdAt: string; // ISO 8601 date string
}

export interface Chat {
  id: string;
  name: string;
  systemPrompt?: string | null;
  modelParameters?: string | null;
  aiModelId?: string | null;
  createdAt: string; // ISO 8601 date string
}

export interface ChatWithMessages extends Chat {
  messages: Message[];
}

// 用于创建会话的请求体
export interface ChatCreate {
  name: string;
  aiModelId?: string | null;
}

// 用于发送消息的请求体 (用于流式/非流式生成)
export interface GenerateRequest {
  content: string;
}
