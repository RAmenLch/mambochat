// frontend/mambo/src/api/types.ts

export type MessageRole = 'user' | 'assistant' | 'system';
export type ChatItemType = 'chat' | 'folder';

export interface Message {
  id: string;
  content: string;
  createdAt: string; // ISO 8601 date string
  role: MessageRole;
  chatId: string;
  sortOrder: number;
}

export interface MessageUpdate {
  content: string;
  resend?: boolean;
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
  id:string;
  name: string;
  createdAt: string;
  systemPrompt: string | null;
  modelParameters: Record<string, string | number | boolean> | null;
  aiModelId: string | null;
  // --- 新增字段，用于支持文件夹、排序和最近会话 ---
  itemType: ChatItemType;
  parentId: string | null;
  sortOrder: number;
  lastOpenedAt: string | null; // ISO 8601 date string
}

export interface ChatCreate {
  name: string;
  systemPrompt?: string | null;
  modelParameters?: Record<string, string | number | boolean> | null;
  aiModelId?: string | null;
  // --- 新增字段 ---
  itemType?: ChatItemType;
  parentId?: string | null;
  sortOrder?: number;
}

export interface ChatUpdate {
  name?: string | null;
  aiModelId?: string | null;
  systemPrompt?: string | null;
  modelParameters?: Record<string, string | number | boolean> | null;
  // --- 新增字段 ---
  parentId?: string | null;
  sortOrder?: number;
}


export interface ChatWithMessages extends Chat {
  messages: Message[];
}

// --- 新增类型: 用于批量更新排序和层级关系 ---
export interface ChatReorderItem {
  id: string;
  parentId: string | null;
  sortOrder: number;
}
