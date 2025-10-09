// frontend/mambo/src/api/types.ts

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  content: string;
  createdAt: string; // ISO 8601 date string
  role: MessageRole;
  chatId: string;
}

export interface AIModel {
  id: string;
  modelId: string;
  name: string;
  providerId: string;
}

export interface AIProvider {
  id: string;
  name: string;
  apiHost: string;
}

export interface AIProviderWithModels extends AIProvider {
  models: AIModel[];
}

export interface Chat {
  id: string;
  name: string;
  createdAt: string;
  systemPrompt: string | null;
  // --- 改动 1: 与后端 schema 同步，将类型从 string 改为对象 ---
  modelParameters: Record<string, any> | null;
  aiModelId: string | null;
}

export interface ChatCreate {
  name: string;
  systemPrompt?: string | null;
  // --- 改动 2: 与后端 schema 同步 ---
  modelParameters?: Record<string, any> | null;
  aiModelId?: string | null;
}

// --- 新增 1: 用于更新会话配置的类型 ---
export interface ChatUpdate {
  name?: string | null; // <--- 新增此行
  aiModelId?: string | null;
  systemPrompt?: string | null;
  modelParameters?: Record<string, any> | null;
}


export interface ChatWithMessages extends Chat {
  messages: Message[];
}
